/* Frame grid: selection, autosave, sizing, the full-size viewer, and the
 * extraction progress bar.
 *
 * Selections autosave on a short debounce so closing the tab never loses work.
 * The one hazard that creates is downloading while a save is still in flight --
 * the server would zip the previous selection. `flush()` is awaited before the
 * download navigates, which closes that window.
 *
 * Listeners are delegated rather than per-cell: a 20-minute clip is 600 cells,
 * and 1200 individual listeners is a cost paid on every page load for nothing.
 */
(function () {
  "use strict";

  var SIZE_KEY = "dataset-builder.cell-size";
  var SIZES = ["320", "440", "640"];
  /* 440 by default because it is the measured floor, not a taste: a traffic
   * sign is about 70px of a 2304px-wide frame, so a 440px cell renders it
   * around 13px, which is the point where you can see that something is there. */
  var DEFAULT_SIZE = "440";

  wireRowLinks();

  var job = document.getElementById("job");
  if (job && job.dataset.poll) pollJob(job);

  var toolbar = document.getElementById("toolbar");
  if (toolbar) wireGrid(toolbar);

  /* Homepage rows navigate on click. Delegated so a filename containing a
   * quote cannot break the handler, and so middle-click still opens a tab. */
  function wireRowLinks() {
    document.addEventListener("click", function (ev) {
      var row = ev.target.closest ? ev.target.closest("tr[data-href]") : null;
      if (!row) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) {
        window.open(row.dataset.href, "_blank");
      } else {
        window.location.href = row.dataset.href;
      }
    });
  }

  function pollJob(box) {
    var url = box.dataset.statusUrl,
        fill = document.getElementById("job-fill"),
        text = document.getElementById("job-text");

    (function tick() {
      fetch(url, { cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (s) {
          if (s.status === "running") {
            box.classList.remove("hidden");
            var pct = s.total ? Math.round((100 * s.done) / s.total) : 0;
            fill.style.width = (s.total ? pct : 100) + "%";
            text.textContent = s.total
              ? "extracting " + s.done + " / " + s.total + " frames (" + pct + "%)"
              : "extracting " + s.done + " frames…";
            setTimeout(tick, 700);
          } else if (s.status === "done") {
            text.textContent = "done, reloading";
            location.reload();
          } else if (s.status === "error") {
            box.classList.remove("hidden");
            fill.style.width = "100%";
            fill.style.background = "var(--danger)";
            text.textContent = "extraction failed: " + s.error;
          }
        })
        .catch(function () { setTimeout(tick, 2000); });
    })();
  }

  function wireGrid(bar) {
    var grid = document.getElementById("grid"),
        cells = Array.prototype.slice.call(grid.querySelectorAll(".cell")),
        countEl = document.getElementById("count"),
        savedEl = document.getElementById("saved"),
        download = document.getElementById("download"),
        saveUrl = bar.dataset.saveUrl,
        chosen = new Set(JSON.parse(bar.dataset.selected || "[]")),
        anchor = null,
        timer = null,
        inflight = Promise.resolve();

    cells.forEach(function (cell, i) {
      cell.dataset.i = i;
      if (chosen.has(Number(cell.dataset.frame))) mark(cell, true);
    });

    wireSizer();
    wireRuler();
    var viewer = wireViewer();
    refresh();

    /* One click listener for the whole sheet. Which button was hit decides
     * whether this is a pick or a request for a closer look. */
    grid.addEventListener("click", function (ev) {
      var zoom = ev.target.closest(".zoom");
      if (zoom) { viewer.open(Number(zoom.parentNode.dataset.i)); return; }

      var pick = ev.target.closest(".pick");
      if (!pick) return;
      var cell = pick.parentNode, i = Number(cell.dataset.i);
      var want = !cell.classList.contains("on");
      if (ev.shiftKey && anchor !== null) {
        var lo = Math.min(anchor, i), hi = Math.max(anchor, i);
        for (var k = lo; k <= hi; k++) apply(cells[k], want);
      } else {
        apply(cell, want);
      }
      anchor = i;
      refresh();
      schedule();
    });

    /* A button fires click on Enter as well as Space, so Enter would otherwise
     * just pick the frame twice over. Claim it for the viewer instead. */
    grid.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter") return;
      var pick = ev.target.closest(".pick");
      if (!pick) return;
      ev.preventDefault();
      viewer.open(Number(pick.parentNode.dataset.i));
    });

    bar.querySelectorAll("[data-act]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var act = btn.dataset.act;
        cells.forEach(function (c) {
          apply(c, act === "all" ? true
                 : act === "none" ? false
                 : !c.classList.contains("on"));
        });
        anchor = null;
        refresh();
        schedule();
      });
    });

    download.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (!chosen.size) return;
      var href = download.href;
      flush().then(function () { window.location.href = href; });
    });

    function mark(cell, on) {
      cell.classList.toggle("on", on);
      cell.querySelector(".pick").setAttribute("aria-pressed", on ? "true" : "false");
    }

    function apply(cell, on) {
      mark(cell, on);
      var frame = Number(cell.dataset.frame);
      if (on) chosen.add(frame); else chosen.delete(frame);
    }

    function refresh() {
      countEl.textContent = chosen.size;
      download.setAttribute("aria-disabled", chosen.size === 0 ? "true" : "false");
    }

    function schedule() {
      savedEl.textContent = "saving…";
      clearTimeout(timer);
      timer = setTimeout(flush, 400);
    }

    function flush() {
      clearTimeout(timer);
      var body = JSON.stringify({ selected: Array.from(chosen) });
      inflight = inflight.then(function () {
        return fetch(saveUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
        })
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
          })
          .then(function (d) {
            savedEl.textContent = "saved · " + d.total_selected + " / " + d.target + " total";
          })
          .catch(function (e) { savedEl.textContent = "SAVE FAILED: " + e.message; });
      });
      return inflight;
    }

    /* Cell size. Remembered per browser, because the right size depends on the
     * screen you happen to be sitting at, and this user moves between two. */
    function wireSizer() {
      var seg = document.getElementById("sizer");
      if (!seg) return;
      var stored = null;
      try { stored = localStorage.getItem(SIZE_KEY); } catch (e) { /* private mode */ }
      set(SIZES.indexOf(stored) >= 0 ? stored : DEFAULT_SIZE);

      seg.addEventListener("click", function (ev) {
        var btn = ev.target.closest("button[data-size]");
        if (btn) set(btn.dataset.size);
      });

      function set(size) {
        grid.style.setProperty("--cell", size + "px");
        seg.querySelectorAll("button[data-size]").forEach(function (b) {
          b.setAttribute("aria-pressed", b.dataset.size === size ? "true" : "false");
        });
        try { localStorage.setItem(SIZE_KEY, size); } catch (e) { /* private mode */ }
      }
    }

    /* Full-size viewer. One frame at true source resolution, because a 440px
     * cell still renders that 70px sign at only about 13px, and some frames
     * genuinely need the other 50. */
    function wireViewer() {
      var box = document.getElementById("viewer");
      if (!box) return { open: function () {} };

      var img = document.getElementById("v-img"),
          stage = document.getElementById("v-stage"),
          timeEl = document.getElementById("v-time"),
          frameEl = document.getElementById("v-frame"),
          posEl = document.getElementById("v-pos"),
          pickBtn = document.getElementById("v-pick"),
          at = 0;

      document.getElementById("v-close").addEventListener("click", close);
      document.getElementById("v-prev").addEventListener("click", function () { go(-1); });
      document.getElementById("v-next").addEventListener("click", function () { go(1); });
      pickBtn.addEventListener("click", toggle);

      /* Clicking the frame picks it, exactly as in the sheet. Clicking the
       * space around it leaves, which is what every viewer does. */
      stage.addEventListener("click", function (ev) {
        if (ev.target === img) toggle(); else close();
      });

      document.addEventListener("keydown", function (ev) {
        if (box.classList.contains("hidden")) return;
        if (ev.key === "Escape") { ev.preventDefault(); close(); }
        else if (ev.key === "ArrowLeft") { ev.preventDefault(); go(-1); }
        else if (ev.key === "ArrowRight") { ev.preventDefault(); go(1); }
        else if (ev.key === " ") { ev.preventDefault(); toggle(); }
      });

      return { open: open };

      function open(i) {
        at = i;
        box.classList.remove("hidden");
        document.body.classList.add("locked");
        show();
        pickBtn.focus();
      }

      /* Focus lands on the frame you were LOOKING at, not the one you came in
       * from. Arrow through six frames and leave, and the sheet should have
       * followed you there. */
      function close() {
        box.classList.add("hidden");
        document.body.classList.remove("locked");
        var cell = cells[at];
        if (!cell) return;
        cell.scrollIntoView({ block: "nearest" });
        cell.querySelector(".pick").focus();
      }

      function go(step) {
        var next = at + step;
        if (next < 0 || next >= cells.length) return;
        at = next;
        show();
      }

      function toggle() {
        var cell = cells[at];
        apply(cell, !cell.classList.contains("on"));
        anchor = Number(cell.dataset.i);
        refresh();
        schedule();
        paintPick();
      }

      function show() {
        var cell = cells[at];
        img.src = cell.dataset.full;
        img.alt = "Frame " + cell.dataset.frame + " at full resolution";
        timeEl.textContent = clock(Number(cell.dataset.t));
        frameEl.textContent = "f" + cell.dataset.frame;
        posEl.textContent = at + 1;
        paintPick();
        // Full frames are ~700 KB, so warm only the immediate neighbours.
        [at - 1, at + 1].forEach(function (i) {
          if (cells[i]) new Image().src = cells[i].dataset.full;
        });
      }

      function paintPick() {
        var on = cells[at].classList.contains("on");
        box.classList.toggle("picked", on);
        pickBtn.classList.toggle("on", on);
        pickBtn.setAttribute("aria-pressed", on ? "true" : "false");
        pickBtn.textContent = on ? "Picked" : "Pick";
      }
    }

    function wireRuler() {
      var ruler = document.getElementById("ruler");
      if (!ruler || !cells.length) return;
      var last = Number(cells[cells.length - 1].dataset.t) || 0;
      for (var s = 0; s <= 10; s++) {
        (function (mark) {
          var b = document.createElement("button");
          b.type = "button";
          b.textContent = clock(mark);
          b.addEventListener("click", function () {
            var best = cells[0], gap = Infinity;
            cells.forEach(function (c) {
              var d = Math.abs(Number(c.dataset.t) - mark);
              if (d < gap) { gap = d; best = c; }
            });
            best.scrollIntoView({ behavior: "smooth", block: "center" });
          });
          ruler.appendChild(b);
        })((last * s) / 10);
      }
    }
  }

  function clock(sec) {
    sec = Math.round(sec || 0);
    return String(Math.floor(sec / 60)).padStart(2, "0") + ":" +
           String(sec % 60).padStart(2, "0");
  }
})();
