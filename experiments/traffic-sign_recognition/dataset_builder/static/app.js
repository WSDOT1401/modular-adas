/* Frame grid: selection, autosave, time ruler, extraction progress.
 *
 * Selections autosave on a short debounce so closing the tab never loses work.
 * The one hazard that creates is downloading while a save is still in flight --
 * the server would zip the previous selection. `flush()` is awaited before the
 * download navigates, which closes that window.
 */
(function () {
  "use strict";

  var job = document.getElementById("job");
  if (job) pollJob(job);

  var toolbar = document.getElementById("toolbar");
  if (toolbar) wireGrid(toolbar);

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
            text.textContent = "done — reloading";
            location.reload();
          } else if (s.status === "error") {
            box.classList.remove("hidden");
            fill.style.width = "100%";
            fill.style.background = "#b42318";
            text.textContent = "extraction failed — " + s.error;
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
      if (chosen.has(Number(cell.dataset.frame))) cell.classList.add("on");
      cell.addEventListener("click", function (ev) {
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

    buildRuler();
    refresh();

    download.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (!chosen.size) return;
      var href = download.href;
      flush().then(function () { window.location.href = href; });
    });

    function apply(cell, on) {
      cell.classList.toggle("on", on);
      var frame = Number(cell.dataset.frame);
      if (on) chosen.add(frame); else chosen.delete(frame);
    }

    function refresh() {
      countEl.textContent = chosen.size;
      download.classList.toggle("disabled", chosen.size === 0);
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
          .catch(function (e) { savedEl.textContent = "SAVE FAILED — " + e.message; });
      });
      return inflight;
    }

    function buildRuler() {
      var ruler = document.getElementById("ruler");
      if (!cells.length) return;
      var last = Number(cells[cells.length - 1].dataset.t) || 0;
      for (var s = 0; s <= 10; s++) {
        (function (at) {
          var b = document.createElement("button");
          b.type = "button";
          b.textContent = clock(at);
          b.addEventListener("click", function () {
            var best = cells[0], gap = Infinity;
            cells.forEach(function (c) {
              var d = Math.abs(Number(c.dataset.t) - at);
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
