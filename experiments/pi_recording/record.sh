#!/usr/bin/env bash
# Dashcam: Pi Camera Module 3 -> 1080p30 H.264 -> ~/footage/drive0001_0000.ts, _0001.ts, ... (1 min each)
#
# Power-cut safe by design:
#   - MPEG-TS, not MP4: a cut file still plays up to the cut (an MP4 is unplayable without the index
#     it writes at the very end)
#   - 1-minute segments: everything except the open minute is a closed file
#   - drives are numbered, not timestamped: with no network or RTC battery the clock is wrong after
#     boot, and time-based names could overwrite older footage
#   - loop recording: the oldest segment is deleted while free space < MIN_FREE_MB, so the OS never fills up
# A cut still loses up to the last ~30 s: Linux holds writes in RAM that long before they reach the card.
#
# Install (once):  chmod +x record.sh && sudo cp dashcam.service /etc/systemd/system/ \
#                  && sudo systemctl enable --now dashcam
# Watch:           journalctl -u dashcam -f
# Free the camera (e.g. for the mac_sender.py TCP stream):  sudo systemctl stop dashcam
# One drive as an MP4 (on the Mac; setts fixes the odd frame whose pts the encoder garbles, which
# otherwise stops the MP4 muxer; "Packet corrupt" at each minute boundary is just the cat join):
#   cat drive0007_*.ts > d7.ts && ffmpeg -i d7.ts -c copy -bsf:v "setts=pts=if(gt(PTS-DTS\,1/TB)\,DTS\,PTS)" d7.mp4
set -euo pipefail

DIR=$HOME/footage
MIN_FREE_MB=2000
mkdir -p "$DIR"

# next drive number = highest on disk + 1
last=$(ls "$DIR" | sed -n 's/^drive\([0-9]*\)_.*/\1/p' | sort -n | tail -1)
drive=$(printf 'drive%04d' $((10#${last:-0} + 1)))
echo "recording to $DIR/${drive}_*.ts"

# loop recording: zero-padded names sort oldest first; never delete the newest (still being written)
while sleep 30; do
    while (( $(df --output=avail -m "$DIR" | tail -1) < MIN_FREE_MB )); do
        files=("$DIR"/drive*.ts)
        (( ${#files[@]} > 1 )) || break
        rm -f -- "${files[0]}"
        echo "disk low, deleted ${files[0]##*/}"
    done
done &
cleaner=$!
trap 'kill $cleaner' EXIT

# --mode 2304:1296    full field of view (the smaller sensor modes crop the centre)
# --lens-position 0   focus locked at infinity, or autofocus hunts between windshield and road
# --codec libav       Pi 5 has no hardware encoder: software x264, muxed as MPEG-TS to stdout
# ffmpeg -c copy      no re-encode, only cuts the stream at keyframes into 1-minute files
rpicam-vid -t 0 -n --mode 2304:1296 --width 1920 --height 1080 --framerate 30 \
    --autofocus-mode manual --lens-position 0 --bitrate 10000000 \
    --codec libav --libav-format mpegts -o - \
  | ffmpeg -hide_banner -loglevel warning -f mpegts -i - \
      -c copy -f segment -segment_time 60 -segment_format mpegts "$DIR/${drive}_%04d.ts"
