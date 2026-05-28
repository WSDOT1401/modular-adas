/**
 * W124 CarPlay sidecar server
 *
 * Bridges the CPC200-CCPA USB dongle to a local TCP socket that Qt reads via
 * a GStreamer pipeline.
 *
 * Video pipeline (Pi):
 *   node-carplay  →  this server  →  TCP :9001  →  Qt GStreamer pipeline
 *
 * Audio pipeline (Pi):
 *   node-carplay  →  this server  →  pacat / aplay  →  speakers
 *
 * Touch events (Pi → iPhone):
 *   Qt  →  TCP :9002  →  this server  →  node-carplay  →  dongle  →  iPhone
 *
 * States reported to Qt over TCP :9003 (newline-delimited JSON):
 *   {"status":"waiting"}   — no dongle plugged in
 *   {"status":"connecting"} — dongle found, handshaking with iPhone
 *   {"status":"active"}    — streaming
 *   {"status":"error","message":"..."} — something went wrong
 */

import net from 'net'
import { spawn } from 'child_process'

// ── Config ────────────────────────────────────────────────────────────────
const VIDEO_PORT  = 9001   // Qt reads H264 stream from here
const TOUCH_PORT  = 9002   // Qt sends touch events here
const STATUS_PORT = 9003   // Qt reads status JSON from here
const AUDIO_SINK  = 'default'  // PipeWire/PulseAudio sink name

// CarPlay session config — match your display resolution
const CARPLAY_CONFIG = {
  width:    800,
  height:   480,
  fps:      30,
  dpi:      160,
  nightMode: false,
  hand:     0,      // 0 = left-hand drive
  boxName:  'W124',
  format:   5,      // H264 baseline
}

// ── State ─────────────────────────────────────────────────────────────────
let carplay        = null
let videoClients   = new Set()
let statusClients  = new Set()
let audioProc      = null
let currentStatus  = 'waiting'

function broadcastStatus(status, extra = {}) {
  currentStatus = status
  const msg = JSON.stringify({ status, ...extra }) + '\n'
  for (const client of statusClients) {
    try { client.write(msg) } catch (_) { statusClients.delete(client) }
  }
  console.log('[carplay]', msg.trim())
}

// ── Video TCP server — Qt connects here to receive H264 ───────────────────
const videoServer = net.createServer(socket => {
  console.log('[video] Qt connected')
  videoClients.add(socket)
  socket.on('close', () => videoClients.delete(socket))
  socket.on('error', () => videoClients.delete(socket))
})
videoServer.listen(VIDEO_PORT, '127.0.0.1', () =>
  console.log(`[video] TCP server on :${VIDEO_PORT}`))

// ── Status TCP server — Qt polls connection state ─────────────────────────
const statusServer = net.createServer(socket => {
  // Send current status immediately on connect
  socket.write(JSON.stringify({ status: currentStatus }) + '\n')
  statusClients.add(socket)
  socket.on('close', () => statusClients.delete(socket))
  socket.on('error', () => statusClients.delete(socket))
})
statusServer.listen(STATUS_PORT, '127.0.0.1', () =>
  console.log(`[status] TCP server on :${STATUS_PORT}`))

// ── Touch TCP server — Qt sends touch events here ─────────────────────────
const touchServer = net.createServer(socket => {
  console.log('[touch] Qt connected')
  let buf = ''
  socket.on('data', data => {
    buf += data.toString()
    const lines = buf.split('\n')
    buf = lines.pop()   // keep incomplete last line
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const { action, x, y } = JSON.parse(line)
        if (carplay) carplay.sendTouch(action, x, y)
      } catch (_) { /* ignore malformed */ }
    }
  })
  socket.on('error', () => {})
})
touchServer.listen(TOUCH_PORT, '127.0.0.1', () =>
  console.log(`[touch] TCP server on :${TOUCH_PORT}`))

// ── Audio helper — pipe PCM to PulseAudio/PipeWire ────────────────────────
function startAudio(sampleRate = 44100, channels = 2) {
  stopAudio()
  try {
    audioProc = spawn('pacat', [
      '--playback',
      `--rate=${sampleRate}`,
      `--channels=${channels}`,
      '--format=s16le',
      `--sink=${AUDIO_SINK}`,
    ], { stdio: ['pipe', 'inherit', 'inherit'] })
    audioProc.on('error', err => console.warn('[audio] pacat error:', err.message))
  } catch (e) {
    console.warn('[audio] Could not start pacat:', e.message)
  }
}

function stopAudio() {
  if (audioProc) {
    audioProc.kill()
    audioProc = null
  }
}

// ── CarPlay session ───────────────────────────────────────────────────────
async function startCarPlay() {
  // Dynamically import so the file still loads cleanly when node-carplay
  // is not yet installed (npm install not yet run).
  let CarplayNode
  try {
    const mod = await import('node-carplay/node')
    CarplayNode = mod.default ?? mod.CarplayNode ?? mod
  } catch (e) {
    console.error('[carplay] node-carplay not installed. Run: npm install')
    broadcastStatus('error', { message: 'node-carplay not installed' })
    return
  }

  carplay = new CarplayNode(CARPLAY_CONFIG)

  carplay.on('plugged', () => {
    console.log('[carplay] Dongle plugged in')
    broadcastStatus('connecting')
  })

  carplay.on('unplugged', () => {
    console.log('[carplay] Dongle unplugged')
    stopAudio()
    broadcastStatus('waiting')
  })

  carplay.on('connected', () => {
    console.log('[carplay] iPhone connected')
    broadcastStatus('active')
  })

  carplay.on('disconnected', () => {
    console.log('[carplay] iPhone disconnected')
    stopAudio()
    broadcastStatus('connecting')
  })

  carplay.on('video', (data) => {
    // Forward raw H264 NAL unit to all Qt video clients
    for (const client of videoClients) {
      try { client.write(data) } catch (_) { videoClients.delete(client) }
    }
  })

  carplay.on('audio', (data) => {
    if (audioProc?.stdin?.writable) {
      audioProc.stdin.write(data.data)
    }
  })

  carplay.on('audioFormat', (format) => {
    startAudio(format.frequency, format.channel)
  })

  carplay.on('error', (err) => {
    console.error('[carplay] Error:', err)
    broadcastStatus('error', { message: String(err) })
  })

  try {
    await carplay.start()
    console.log('[carplay] Scanning for dongle...')
  } catch (e) {
    console.error('[carplay] Failed to start:', e.message)
    broadcastStatus('error', { message: e.message })
  }
}

// ── Startup ───────────────────────────────────────────────────────────────
broadcastStatus('waiting')
startCarPlay()

process.on('SIGINT',  () => { stopAudio(); process.exit(0) })
process.on('SIGTERM', () => { stopAudio(); process.exit(0) })
