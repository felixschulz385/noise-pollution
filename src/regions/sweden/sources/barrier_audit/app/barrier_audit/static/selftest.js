// Device check: confirms Python, localhost, the answers folder, WebGL, the
// Lantmäteriet imagery and the map interaction on the reviewer's laptop,
// then saves a report to answers/ for the reviewer to send back.
(function () {
  "use strict";

  var C = window.AuditCommon;

  // A real road barrier (element 22534:36323, osm_offset, E4/E20 south of
  // Stockholm), in lon/lat.
  var SAMPLE_LINE = [
    [17.913175, 59.273205], [17.913099, 59.27307], [17.912947, 59.272811], [17.912783, 59.272554],
    [17.912605, 59.272299], [17.912414, 59.272048], [17.912209, 59.271799], [17.911992, 59.271554],
    [17.911757, 59.271308], [17.911707, 59.271258]
  ];

  var TIMEOUT_MS = { tile: 15000, map: 30000 };
  var reportId = new Date().toISOString().replace(/[:.]/g, "-").replace("Z", "");
  var results = {};
  var info = null;
  var saving = false, saveAgain = false;

  var CHECKS = [
    ["server", "Python app running"],
    ["answers", "Answers folder writable"],
    ["location", "Unzipped to a normal folder"],
    ["webgl", "WebGL (needed to draw the map)"],
    ["tile", "Aerial imagery reachable"],
    ["map", "Map draws the imagery"],
    ["screen", "Screen size"],
    ["drag", "Step 1: map can be dragged"],
    ["key", "Step 2: arrow key reaches the page"],
    ["seen", "Step 3: imagery and red line visible"]
  ];
  var AUTOMATIC = ["server", "answers", "location", "webgl", "tile", "map", "screen"];
  var MARKS = { pending: "…", ok: "✓", warn: "!", fail: "✗" };

  function el(id) { return document.getElementById(id); }

  function buildList() {
    var list = el("check-list");
    CHECKS.forEach(function (c) {
      var li = document.createElement("li");
      li.id = "check-" + c[0];
      li.innerHTML = '<span class="mark"></span><span class="label"></span><span class="detail"></span>';
      li.querySelector(".label").textContent = c[1];
      list.appendChild(li);
      set(c[0], "pending", "");
    });
  }

  function set(id, status, detail, data) {
    results[id] = { status: status, detail: detail || "", data: data || null };
    var li = el("check-" + id);
    li.className = status;
    li.querySelector(".mark").textContent = MARKS[status];
    li.querySelector(".detail").textContent = detail || "";
    if (status !== "pending" && AUTOMATIC.every(function (k) { return results[k].status !== "pending"; })) {
      saveReport();
    }
  }

  function checkServer() {
    return fetch("/api/info", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      info = data;
      el("version").textContent = "app " + data.app_version + " · Python " + data.python_version;
      var major = data.python_version.split(".").map(Number);
      var oldPython = major[0] < 3 || (major[0] === 3 && major[1] < 8);
      set("server", oldPython ? "warn" : "ok", "Python " + data.python_version + " on " + data.platform);
      set("answers", data.answers_writable ? "ok" : "fail",
        data.answers_writable ? data.answers_dir : "Cannot write to " + data.answers_dir + " (" + data.answers_error + ")");
      set("location", data.root_looks_temporary ? "warn" : "ok",
        data.root_looks_temporary
          ? "This looks like a temporary folder inside the zip. Right-click the zip, choose Extract All, and start again from there."
          : data.root);
    }).catch(function (e) {
      set("server", "fail", "No answer from the local app: " + e.message);
      set("answers", "fail", "Unknown (app not reachable)");
      set("location", "fail", "Unknown (app not reachable)");
    });
  }

  function checkWebgl() {
    var data = C.webglInfo();
    if (data.webgl2) set("webgl", "ok", "WebGL 2 · " + data.renderer, data);
    else if (data.webgl1) set("webgl", "warn", "Only WebGL 1 · " + data.renderer, data);
    else set("webgl", "fail", "Not available. The browser or computer blocks WebGL.", data);
    return data.webgl2 || data.webgl1;
  }

  function checkTile() {
    var mid = SAMPLE_LINE[Math.floor(SAMPLE_LINE.length / 2)];
    return C.checkTile(mid[0], mid[1], TIMEOUT_MS.tile).then(function (r) {
      set("tile", r.ok ? (r.warn ? "warn" : "ok") : "fail", r.detail, r.data);
    });
  }

  // Compass bearing that puts the line's start-to-end direction pointing
  // right on screen, so "up" is the left side of the digitised direction.
  function bearingAlong(line) {
    var a = line[0], b = line[line.length - 1];
    var dx = (b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), dy = b[1] - a[1];
    return Math.atan2(dx, dy) * 180 / Math.PI - 90;
  }

  function checkMap(webglOk) {
    if (!webglOk) {
      set("map", "fail", "Skipped: needs WebGL");
      return;
    }
    var lons = SAMPLE_LINE.map(function (p) { return p[0]; });
    var lats = SAMPLE_LINE.map(function (p) { return p[1]; });
    var center = [(Math.min.apply(null, lons) + Math.max.apply(null, lons)) / 2,
      (Math.min.apply(null, lats) + Math.max.apply(null, lats)) / 2];
    var tileErrors = 0, lastError = "";
    var map;
    try {
      map = new maplibregl.Map({
        container: "map",
        center: center,
        zoom: 17,
        bearing: bearingAlong(SAMPLE_LINE),
        pitchWithRotate: false,
        dragRotate: false,
        attributionControl: { compact: false },
        style: {
          version: 8,
          sources: {
            ortho: { type: "raster", tiles: [C.WMS_TILES], tileSize: 256, maxzoom: C.WMS_MAXZOOM, attribution: "© Lantmäteriet" },
            sample: { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: SAMPLE_LINE } } }
          },
          layers: [
            { id: "bg", type: "background", paint: { "background-color": "#d9d9d4" } },
            { id: "ortho", type: "raster", source: "ortho" },
            { id: "sample", type: "line", source: "sample", paint: { "line-color": "#ff2d2d", "line-width": 3 } }
          ]
        }
      });
    } catch (e) {
      set("map", "fail", "The map could not start: " + e.message);
      return;
    }
    window.auditMap = map;
    map.touchZoomRotate.disableRotation();
    map.keyboard.disable();
    map.on("error", function (e) {
      tileErrors++;
      lastError = (e && e.error && e.error.message) || "unknown error";
    });
    var t0 = performance.now();
    var done = false;
    map.on("idle", function () {
      if (done) return;
      done = true;
      var ms = Math.round(performance.now() - t0);
      var data = { ms: ms, tile_errors: tileErrors, last_error: lastError };
      if (tileErrors === 0) set("map", "ok", "Drawn in " + ms + " ms", data);
      else set("map", "warn", "Drawn in " + ms + " ms with " + tileErrors + " tile error(s): " + lastError, data);
    });
    setTimeout(function () {
      if (done) return;
      done = true;
      set("map", "fail", "Not finished after " + TIMEOUT_MS.map / 1000 + " s" + (tileErrors ? " (" + lastError + ")" : ""),
        { tile_errors: tileErrors, last_error: lastError });
    }, TIMEOUT_MS.map);

    map.on("dragend", function () {
      if (results.drag.status === "ok") return;
      set("drag", "ok", "Drag works");
    });
  }

  function checkScreen() {
    var data = { width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio, screen: [screen.width, screen.height] };
    var detail = data.width + " × " + data.height + " px window (pixel ratio " + data.dpr + ")";
    set("screen", data.width < 1100 || data.height < 650 ? "warn" : "ok",
      data.width < 1100 || data.height < 650 ? detail + ". Small: maximise the browser window for the audit." : detail, data);
  }

  function wireManual() {
    document.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowUp" || results.key.status === "ok") return;
      e.preventDefault();
      set("key", "ok", "Arrow key received");
    });
    ["yes", "no"].forEach(function (answer) {
      el("seen-" + answer).addEventListener("click", function () {
        el("seen-yes").classList.toggle("chosen", answer === "yes");
        el("seen-no").classList.toggle("chosen", answer === "no");
        set("seen", answer === "yes" ? "ok" : "fail", answer === "yes" ? "Reviewer sees imagery and the line" : "Reviewer does not see them");
      });
    });
  }

  function saveReport() {
    if (saving) { saveAgain = true; return; }
    if (!info || !info.answers_writable) {
      reportStatus("failed", "The report cannot be saved (" + (info ? "the answers folder is not writable" : "the local app is not reachable") +
        "). Please send a screenshot of this page instead.");
      return;
    }
    saving = true;
    var body = {
      report_id: reportId,
      kind: "device_check",
      saved_at: new Date().toISOString(),
      user_agent: navigator.userAgent,
      language: navigator.language,
      results: results
    };
    fetch("/api/selftest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "HTTP " + r.status); return j; }); })
      .then(function (j) {
        var manualDone = ["drag", "key", "seen"].every(function (k) { return results[k].status !== "pending"; });
        reportStatus("saved", manualDone
          ? "Done. Please send the file " + j.saved + " (inside the unzipped folder) to Felix. You can then close this page and the black window."
          : "Report saved to " + j.saved + ". Now please do the three steps below the map; the report updates automatically.");
      })
      .catch(function (e) { reportStatus("failed", "The report could not be saved (" + e.message + "). Please send a screenshot of this page instead."); })
      .then(function () {
        saving = false;
        if (saveAgain) { saveAgain = false; saveReport(); }
      });
  }

  function reportStatus(cls, text) {
    var box = el("report-status");
    box.className = "report-status " + cls;
    box.textContent = text;
  }

  buildList();
  wireManual();
  checkScreen();
  var webglOk = checkWebgl();
  checkServer().then(function () {
    checkTile();
    checkMap(webglOk);
  });
})();
