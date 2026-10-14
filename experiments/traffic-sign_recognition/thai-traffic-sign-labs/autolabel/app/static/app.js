// Homepage: extract / score run off-thread on the server, so poll for progress.
document.addEventListener('click', async (e) => {
  const b = e.target.closest('button.job');
  if (!b) return;
  const prog = b.parentElement.querySelector('.prog');
  const body = new FormData();
  if (b.dataset.interval !== undefined) {
    body.append('interval', document.getElementById('interval')?.value || '2');
  }
  b.disabled = true;
  prog.textContent = ' starting…';
  const r = await fetch(b.dataset.url, { method: 'POST', body });
  if (!r.ok) { prog.textContent = ' ' + (await r.text()).slice(0, 80); b.disabled = false; return; }
  const { job } = await r.json();
  const tick = setInterval(async () => {
    const s = await (await fetch('/job/' + job)).json();
    if (s.state === 'queued') {
      // Jobs run one at a time on purpose; tell the truth about the wait
      // rather than showing a progress bar that is not moving.
      prog.textContent = s.ahead ? ` queued (${s.ahead} ahead)` : ' queued';
    } else if (s.state === 'running') {
      // total stays 0 while the detector loads -- several seconds of real work
      // that used to render as a meaningless "0/?".
      prog.textContent = s.total ? ` ${s.done}/${s.total}` : ' loading model…';
    } else {
      clearInterval(tick);
      prog.textContent = s.state === 'done' ? ' done' : ' ' + s.error;
      if (s.state !== 'done') { b.disabled = false; return; }
      if (!document.querySelector('.prog:not(:empty)')) return;
      const pending = [...document.querySelectorAll('.prog')]
        .some(x => /queued|loading|\d+\/\d+/.test(x.textContent));
      if (!pending) location.reload();
    }
  }, 700);
});

function startSheet(clip) {
  const grid = document.getElementById('grid');
  const cells = [...grid.querySelectorAll('.cell')];
  const tally = document.getElementById('tally');
  let filter = 'all', last = null, timer = null;

  // The detector proposes; a flip overrules it. We store the flip, not the
  // answer, so both opinions survive into the batch.
  const isSign = (c) => (+c.dataset.boxes > 0) !== (c.dataset.flipped === '1');

  function paint() {
    let sign = 0, empty = 0;
    for (const c of cells) {
      const s = isSign(c);
      c.dataset.sign = s ? '1' : '0';
      c.querySelector('.badge').textContent =
        c.dataset.flipped === '1' ? (s ? 'sign' : 'none') : (c.dataset.boxes || '–');
      c.classList.toggle('hide', filter !== 'all' && (filter === 'sign') !== s);
      if (c.classList.contains('picked')) s ? sign++ : empty++;
    }
    const n = sign + empty;
    const pct = n ? Math.round(100 * empty / n) : 0;
    const good = pct >= 35 && pct <= 45;
    tally.innerHTML = n
      ? `picked ${n} — ${sign} sign / ${empty} empty ` +
        `<b class="${good ? 'ok' : 'off'}">(${pct}% empty${good ? ' ✓' : ''})</b>`
      : 'nothing picked yet';
  }

  function save() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      fetch(`/clip/${encodeURIComponent(clip)}/selection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected: cells.filter(c => c.classList.contains('picked')).map(c => c.dataset.id),
          flipped: cells.filter(c => c.dataset.flipped === '1').map(c => c.dataset.id),
        }),
      });
    }, 400);
  }

  grid.addEventListener('click', (e) => {
    const cell = e.target.closest('.cell');
    if (!cell) return;
    if (e.target.closest('.badge')) {
      cell.dataset.flipped = cell.dataset.flipped === '1' ? '0' : '1';
      paint(); save();
      return;
    }
    const i = cells.indexOf(cell);
    if (e.shiftKey && last !== null) {
      const want = cell.classList.contains('picked');
      for (let k = Math.min(i, last); k <= Math.max(i, last); k++) {
        if (!cells[k].classList.contains('hide')) cells[k].classList.toggle('picked', !want);
      }
    } else {
      cell.classList.toggle('picked');
    }
    last = i;
    paint(); save();
  });

  document.querySelectorAll('button.f').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('button.f').forEach(x => x.classList.toggle('on', x === b));
    filter = b.dataset.f;
    paint();
  }));

  const setZ = (px) => document.documentElement.style.setProperty('--cell', px + 'px');
  document.querySelectorAll('button.z').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('button.z').forEach(x => x.classList.toggle('on', x === b));
    setZ(b.dataset.z);
    try { localStorage.setItem('cell', b.dataset.z); } catch {}
  }));
  try {
    const z = localStorage.getItem('cell');
    if (z) document.querySelector(`button.z[data-z="${z}"]`)?.click();
  } catch {}

  paint();
}


// Homepage: tick-all, plus a live total so you know the batch size BEFORE
// creating it -- the whole point of a batch is that its size is known up front.
(() => {
  const all = document.getElementById('all');
  const chosen = document.getElementById('chosen');
  if (!all || !chosen) return;
  const boxes = [...document.querySelectorAll('input[name="clip"]:not([disabled])')];

  function total() {
    const on = boxes.filter(b => b.checked);
    const n = on.reduce((a, b) => a + +b.dataset.n, 0);
    const e = on.reduce((a, b) => a + +b.dataset.empty, 0);
    const pct = n ? Math.round(100 * e / n) : 0;
    const good = pct >= 35 && pct <= 45;
    chosen.innerHTML = n
      ? `— ${n} frames from ${on.length} clips, ${n - e} sign / ${e} empty ` +
        `<b class="${good ? 'ok' : 'off'}">(${pct}% empty)</b>`
      : '';
    all.checked = on.length === boxes.length && boxes.length > 0;
    all.indeterminate = on.length > 0 && on.length < boxes.length;
  }

  all.addEventListener('change', () => {
    boxes.forEach(b => { b.checked = all.checked; });
    total();
  });
  boxes.forEach(b => b.addEventListener('change', total));
  total();
})();
