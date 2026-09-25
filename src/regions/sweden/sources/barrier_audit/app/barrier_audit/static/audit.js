// The audit: one barrier per task; the reviewer pans the photo until the
// overlay lies on the wall and submits the offset, or says why they can't.
// Rules and answer fields: docs/data/sweden/barrier_audit/README.md.
(function () {
  "use strict";

  var C = window.AuditCommon, G = window.AuditGeometry;
  var NUDGE_M = 0.25, NUDGE_SHIFT_M = 2, MIN_SIDE_OFFSET_M = 2;
  var MIN_ZOOM = 14, MAX_ZOOM = 21;
  var EMPTY = { type: "FeatureCollection", features: [] };

  var tasks = [], answers = {}, index = -1, task = null;
  var phase = "loading";  // loading | start | task | unsure | note | confirm | feedback | done
  var shownAt = 0, current = { d: 0, along: 0 }, pendingReason = null, streetViewOpens = 0;
  var map = null, answersFile = "", sending = false;

  function el(id) { return document.getElementById(id); }
  function show(id, on) { el(id).hidden = !on; }
  function fmt(v, digits) { return (Math.round(v * Math.pow(10, digits)) / Math.pow(10, digits)).toFixed(digits); }

  function arrow(d) {
    if (Math.abs(d) < 0.005) return "0.00 m";
    return (d > 0 ? "↑ " : "↓ ") + fmt(Math.abs(d), 2) + " m";
  }

  function setPhase(p) {
    phase = p;
    ["start", "unsure", "confirm", "feedback", "done"].forEach(function (id) {
      show(id, p === id || (id === "unsure" && p === "note"));
    });
    show("note-wrap", p === "note");
    var working = p === "task";
    el("btn-submit").disabled = !working;
    el("btn-unsure").disabled = !working;
    el("btn-both").disabled = !working;
    el("btn-streetview").disabled = !(p === "task" || p === "unsure");
    if (p === "note") el("note").focus();
    else if (document.activeElement && document.activeElement.id === "note") document.activeElement.blur();
  }

  function error(msg) {
    el("error").textContent = msg || "";
    show("error", !!msg);
  }

  // -- map ---------------------------------------------------------------

  function lineFeature(coords) {
    return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } };
  }

  function buildMap() {
    map = new maplibregl.Map({
      container: "map",
      center: tasks[0].center,
      zoom: 17,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      maxPitch: 0,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      renderWorldCopies: false,
      fadeDuration: 0,
      attributionControl: { compact: false },
      style: {
        version: 8,
        sources: {
          ortho: { type: "raster", tiles: [C.WMS_TILES], tileSize: 256, maxzoom: C.WMS_MAXZOOM, attribution: "© Lantmäteriet" },
          ghost: { type: "geojson", data: EMPTY },
          others: { type: "geojson", data: EMPTY },
          overlay: { type: "geojson", data: EMPTY },
          wall: { type: "geojson", data: EMPTY }
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#d9d9d4" } },
          { id: "ortho", type: "raster", source: "ortho" },
          { id: "ghost", type: "line", source: "ghost",
            paint: { "line-color": "#ffffff", "line-opacity": 0.75, "line-width": 1.5, "line-dasharray": [3, 3] } },
          { id: "others", type: "line", source: "others",
            paint: { "line-color": "#ffa31a", "line-opacity": 0.9, "line-width": 2 } },
          { id: "wall", type: "line", source: "wall", paint: { "line-color": "#2bff7a", "line-width": 3 } },
          { id: "overlay", type: "line", source: "overlay", paint: { "line-color": "#ff2bd6", "line-width": 2.5 } }
        ]
      }
    });
    // Zoom around the centre only, so zooming never moves the overlay; no
    // drag inertia, so a quick drag doesn't fling the map away.
    map.scrollZoom.enable({ around: "center" });
    map.touchZoomRotate.enable({ around: "center" });
    map.touchZoomRotate.disableRotation();
    map.dragPan.enable({ maxSpeed: 0 });
    map.on("move", onMove);
    return new Promise(function (resolve) { map.on("load", resolve); });
  }

  function onMove() {
    if (!task) return;
    var c = map.getCenter();
    current = G.decompose(task, c.lng, c.lat);
    map.getSource("overlay").setData(lineFeature(G.overlayLonLat(task, current.d)));
    el("offset").textContent = "offset " + arrow(current.d);
  }

  function startView(t) {
    var width = el("map").clientWidth || 1000;
    var zoom = Math.max(MIN_ZOOM, Math.min(20, G.zoomFor(t.center[1], width, t.view_m)));
    return { center: t.center, zoom: zoom, bearing: t.bearing, pitch: 0 };
  }

  // -- tasks -------------------------------------------------------------

  function metaText(t) {
    var parts = [t.kind];
    if (t.material) parts.push(t.material);
    if (t.height_m) parts.push(fmt(t.height_m, 1) + " m high");
    if (t.length_m) parts.push(t.length_m + " m long");
    return parts.join(" · ");
  }

  function answerText(a) {
    if (!a) return "";
    if (a.status === "both_sides") return "your answer: both sides";
    return "your answer: " + (a.status === "aligned" ? arrow(a.lateral_m) : "unsure (" + a.reason.replace("_", " ") + ")");
  }

  function linesFeature(lines) {
    return { type: "FeatureCollection", features: (lines || []).map(lineFeature) };
  }

  function areaText(t) {
    if (!t.area) return "";
    return "area " + t.area.number + " of " + t.area.count + (t.area.size > 1 ? " · " + t.area.position + " of " + t.area.size + " here" : "");
  }

  function nAnswered() { return tasks.filter(function (t) { return answers[t.task_id]; }).length; }

  function showTask(i) {
    index = i;
    task = tasks[i];
    error("");
    el("progress").textContent = (i + 1) + " / " + tasks.length;
    el("meta").textContent = metaText(task);
    show("badge", !!task.practice);
    el("area").textContent = areaText(task);
    show("others-legend", !!(task.others_lonlat && task.others_lonlat.length));
    map.getSource("others").setData(linesFeature(task.others_lonlat));
    el("previous").textContent = answerText(answers[task.task_id]);
    map.getSource("ghost").setData(lineFeature(task.line_lonlat));
    map.getSource("wall").setData(EMPTY);
    map.jumpTo(startView(task));
    onMove();
    show("btn-streetview", hasStreetView());
    show("streetview-hint", hasStreetView());
    streetViewOpens = 0;
    shownAt = performance.now();
    setPhase("task");
  }

  // Street View is offered for road barriers only: panoramas are taken from
  // roads, so a rail wall is rarely in view.
  function hasStreetView() { return !!task && task.kind === "road"; }

  function openStreetView() {
    if (!hasStreetView()) return;
    streetViewOpens += 1;
    // One named tab, reused on every press, so tabs don't pile up.
    var tab = window.open(G.streetViewUrl(G.streetView(task, current.along)), "barrier_streetview");
    if (tab) tab.focus();
    else error("The browser blocked the Street View tab. Allow pop-ups for this page and press G again.");
  }

  function nextIndex(from) {
    for (var k = 1; k <= tasks.length; k++) {
      var i = (from + k) % tasks.length;
      if (!answers[tasks[i].task_id]) return i;
    }
    return -1;
  }

  function goNext() {
    var i = nextIndex(index);
    if (i < 0) {
      task = null;
      el("progress").textContent = tasks.length + " / " + tasks.length;
      el("done-file").textContent = answersFile;
      setPhase("done");
    } else {
      showTask(i);
    }
  }

  function send(status, reason, note) {
    if (sending) return;
    sending = true;
    var record = {
      task_id: task.task_id,
      status: status,
      reason: reason,
      note: note || null,
      lateral_m: current.d,
      along_residual_m: current.along,
      zoom: map.getZoom(),
      seconds_on_task: (performance.now() - shownAt) / 1000,
      answered_at: new Date().toISOString(),
      streetview_opens: streetViewOpens
    };
    fetch("/api/answer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(record) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "HTTP " + r.status); return j; }); })
      .then(function () {
        answers[task.task_id] = record;
        if (task.practice && task.practice_answer) showFeedback(record);
        else goNext();
      })
      .catch(function (e) {
        setPhase("task");
        error("The answer was not saved (" + e.message + "). Is the black window still open? Try again.");
      })
      .then(function () { sending = false; });
  }

  function submit() {
    if (Math.abs(current.d) < MIN_SIDE_OFFSET_M && phase === "task") {
      setPhase("confirm");
      return;
    }
    send("aligned", null, null);
  }

  function chooseReason(reason) {
    if (reason === "other") {
      pendingReason = reason;
      el("note").value = "";
      setPhase("note");
      return;
    }
    send("unsure", reason, null);
  }

  function saveNote() {
    var note = el("note").value.trim();
    if (!note) { el("note").focus(); return; }
    send("unsure", pendingReason, note);
  }

  function showFeedback(record) {
    var truth = task.practice_answer.lateral_m;
    map.getSource("wall").setData(lineFeature(task.practice_answer.wall_lonlat));
    var title, text;
    if (record.status === "both_sides") {
      title = "Practice: both sides";
      text = "OpenStreetMap has one wall here, at " + arrow(truth) + " (green line). If you can see a second wall " +
        "on the other side too, your answer may still be right: OpenStreetMap is not complete.";
    } else if (record.status === "aligned" && Math.abs(record.lateral_m) < MIN_SIDE_OFFSET_M) {
      title = "Not quite";
      text = "You left the line on the road centre; the wall is at " + arrow(truth) + ". Drag the photo until the line lies on the green line's wall.";
    } else if (record.status === "aligned") {
      var sameSide = Math.abs(record.lateral_m) >= MIN_SIDE_OFFSET_M && (record.lateral_m > 0) === (truth > 0);
      var off = Math.abs(record.lateral_m - truth);
      title = sameSide ? (off <= 2 ? "Well done" : "Right side") : "Not quite";
      text = "You moved the line " + arrow(record.lateral_m) + "; the wall is at " + arrow(truth) + ". " +
        (sameSide ? (off <= 2 ? "That matches." : "Right side, " + fmt(off, 1) + " m off. Try matching the wall's foot.")
          : "The wall is on the other side of the road. Compare the green line with the photo.");
    } else {
      title = "Practice: unsure";
      text = "The wall is at " + arrow(truth) + " (green line). Look at how it appears in the photo.";
    }
    el("feedback-title").textContent = title;
    el("feedback-text").textContent = text;
    setPhase("feedback");
  }

  function nudge(step) {
    // Keeps the along-road position the reviewer panned to.
    map.jumpTo({ center: G.centerAt(task, current.d + step, current.along) });
  }

  function reset() {
    map.jumpTo(startView(task));
  }

  function previous() {
    if (index > 0) showTask(index - 1);
    else if (phase === "done" && tasks.length) showTask(tasks.length - 1);
  }

  // -- keys --------------------------------------------------------------

  document.addEventListener("keydown", function (e) {
    var typing = e.target && e.target.tagName === "TEXTAREA";
    if (phase === "note") {
      if (e.key === "Escape") { e.preventDefault(); setPhase("unsure"); }
      else if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveNote(); }
      return;
    }
    if (typing) return;
    if (phase === "start") {
      if (e.key === "Enter" && !el("btn-start").disabled) { e.preventDefault(); begin(); }
      return;
    }
    if (phase === "unsure") {
      var reasons = { "1": "occluded", "2": "not_visible", "3": "other" };
      if (reasons[e.key]) { e.preventDefault(); chooseReason(reasons[e.key]); }
      else if (e.key === "g" || e.key === "G") { e.preventDefault(); openStreetView(); }
      else if (e.key === "Escape") { e.preventDefault(); setPhase("task"); }
      return;
    }
    if (phase === "confirm") {
      if (e.key === "Enter") { e.preventDefault(); send("aligned", null, null); }
      else if (e.key === "Escape") { e.preventDefault(); setPhase("task"); }
      return;
    }
    if (phase === "feedback") {
      if (e.key === "Enter") { e.preventDefault(); goNext(); }
      return;
    }
    if (phase === "done") {
      if (e.key === "Backspace") { e.preventDefault(); previous(); }
      return;
    }
    if (phase !== "task") return;
    switch (e.key) {
      case "ArrowUp": e.preventDefault(); nudge(e.shiftKey ? NUDGE_SHIFT_M : NUDGE_M); break;
      case "ArrowDown": e.preventDefault(); nudge(-(e.shiftKey ? NUDGE_SHIFT_M : NUDGE_M)); break;
      case "Enter": e.preventDefault(); submit(); break;
      case "u": case "U": e.preventDefault(); setPhase("unsure"); break;
      case "b": case "B": e.preventDefault(); send("both_sides", null, null); break;
      case "g": case "G": e.preventDefault(); openStreetView(); break;
      case "r": case "R": e.preventDefault(); reset(); break;
      case "Backspace": e.preventDefault(); previous(); break;
      case " ":
        e.preventDefault();
        if (!e.repeat) map.setLayoutProperty("overlay", "visibility", "none");
        break;
    }
  });
  document.addEventListener("keyup", function (e) {
    if (e.key === " " && map) map.setLayoutProperty("overlay", "visibility", "visible");
  });

  // Buttons never keep focus, so Space/Enter only ever reach the handler above.
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("button")) document.activeElement.blur();
  }, true);
  el("btn-submit").addEventListener("click", submit);
  el("btn-unsure").addEventListener("click", function () { setPhase("unsure"); });
  el("btn-both").addEventListener("click", function () { if (phase === "task") send("both_sides", null, null); });
  el("btn-streetview").addEventListener("click", function () { if (phase === "task" || phase === "unsure") openStreetView(); });
  el("btn-start").addEventListener("click", begin);
  el("btn-note").addEventListener("click", saveNote);
  el("btn-continue").addEventListener("click", goNext);
  Array.prototype.forEach.call(document.querySelectorAll("#unsure [data-reason]"), function (b) {
    b.addEventListener("click", function () { chooseReason(b.getAttribute("data-reason")); });
  });

  // -- start -------------------------------------------------------------

  function check(label, status, detail) {
    var li = document.createElement("li");
    li.className = status;
    li.innerHTML = '<span class="mark"></span><span class="label"></span><span class="detail"></span>';
    li.querySelector(".mark").textContent = { ok: "✓", warn: "!", fail: "✗", pending: "…" }[status];
    li.querySelector(".label").textContent = label;
    li.querySelector(".detail").textContent = detail || "";
    el("start-checks").appendChild(li);
    return li;
  }

  function begin() {
    var i = nextIndex(-1);
    if (i < 0) { index = tasks.length - 1; goNext(); } else showTask(i);
  }

  function init() {
    setPhase("start");
    fetch("/api/info", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (info) {
        if (info.tasks_error) throw new Error("tasks.json could not be read: " + info.tasks_error);
        check("Answers folder writable", info.answers_writable ? "ok" : "fail", info.answers_writable ? "" : info.answers_error);
        if (!info.answers_writable) throw new Error("Answers cannot be saved.");
        return fetch("/api/tasks", { cache: "no-store" }).then(function (r) { return r.json(); });
      })
      .then(function (data) {
        tasks = data.tasks;
        answers = data.answers || {};
        answersFile = data.answers_file;
        el("start-summary").textContent = "Batch " + data.batch + ": " + tasks.length + " tasks, " + nAnswered() +
          " answered so far. Answers are saved after every task, so you can stop and continue at any time.";
        if (data.skipped_lines) check("Answers file", "warn", data.skipped_lines + " unreadable line(s) ignored");
        var gl = C.webglInfo();
        check("WebGL", gl.webgl2 || gl.webgl1 ? "ok" : "fail", gl.renderer || "not available");
        if (!(gl.webgl2 || gl.webgl1)) throw new Error("The map needs WebGL.");
        var imagery = check("Aerial imagery", "pending", "loading…");
        var first = tasks[Math.max(0, nextIndex(-1))];
        return Promise.all([buildMap(), C.checkTile(first.center[0], first.center[1])]).then(function (res) {
          var r = res[1];
          imagery.remove();
          check("Aerial imagery", r.ok ? (r.warn ? "warn" : "ok") : "fail", r.detail);
          el("btn-start").disabled = false;
        });
      })
      .catch(function (e) {
        check("Start", "fail", e.message);
      });
  }

  // Read-only view of the state, for automated browser checks.
  window.auditState = function () {
    return { phase: phase, index: index, task_id: task && task.task_id, d: current.d, along: current.along,
      kind: task && task.kind, streetview_opens: streetViewOpens,
      zoom: map && map.getZoom(), bearing: map && map.getBearing(),
      screen: task && map ? [map.project(task.line_lonlat[0]), map.project(task.line_lonlat[task.line_lonlat.length - 1])] : null };
  };

  init();
})();
