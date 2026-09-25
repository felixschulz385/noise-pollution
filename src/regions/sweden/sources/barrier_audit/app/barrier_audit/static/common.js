// Shared by the device check and the audit: the imagery service and the
// checks both run before any work starts. Also loadable from Node (the
// geometry is tested there).
(function (root) {
  "use strict";

  var WMS_BASE = "https://minkarta.lantmateriet.se/map/ortofoto/";
  var WMS_LAYERS = "Ortofoto_0.5,Ortofoto_0.4,Ortofoto_0.25,Ortofoto_0.16";
  var WMS_TILES = WMS_BASE + "?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=" + WMS_LAYERS +
    "&STYLES=&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/jpeg";
  // Finest imagery is 0.16 m/px: a 256 px tile at z19 is 0.15 m/px at 59°N.
  var WMS_MAXZOOM = 19;

  function mercator(lon, lat) {
    var r = 6378137;
    return [r * lon * Math.PI / 180, r * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))];
  }

  function webglInfo() {
    var canvas = document.createElement("canvas");
    var gl2 = null, gl1 = null;
    try { gl2 = canvas.getContext("webgl2"); } catch (e) { /* reported below */ }
    if (!gl2) {
      try { gl1 = canvas.getContext("webgl") || canvas.getContext("experimental-webgl"); } catch (e) { /* reported below */ }
    }
    var gl = gl2 || gl1;
    var data = { webgl2: !!gl2, webgl1: !!gl1, renderer: null };
    if (gl) {
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      data.renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    }
    return data;
  }

  function withTimeout(promise, ms, what) {
    return new Promise(function (resolve, reject) {
      var t = setTimeout(function () { reject(new Error(what + " timed out after " + ms / 1000 + " s")); }, ms);
      promise.then(function (v) { clearTimeout(t); resolve(v); }, function (e) { clearTimeout(t); reject(e); });
    });
  }

  function decode(blob) {
    if (root.createImageBitmap) return createImageBitmap(blob);
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { reject(new Error("image could not be decoded")); };
      img.src = URL.createObjectURL(blob);
    });
  }

  // Spread of pixel brightness: a blank or single-colour tile (no coverage,
  // or a proxy's error image) comes out near zero.
  function brightnessSpread(image) {
    var c = document.createElement("canvas");
    c.width = 64; c.height = 64;
    var ctx = c.getContext("2d");
    ctx.drawImage(image, 0, 0, 64, 64);
    var px = ctx.getImageData(0, 0, 64, 64).data, n = 0, sum = 0, sq = 0;
    for (var i = 0; i < px.length; i += 4) {
      var v = (px[i] + px[i + 1] + px[i + 2]) / 3;
      sum += v; sq += v * v; n++;
    }
    var mean = sum / n;
    return Math.sqrt(Math.max(0, sq / n - mean * mean));
  }

  // One 300 m tile around (lon, lat): resolves to {ok, warn, detail, data}.
  function checkTile(lon, lat, timeoutMs) {
    var m = mercator(lon, lat);
    var bbox = [m[0] - 150, m[1] - 150, m[0] + 150, m[1] + 150].map(function (v) { return v.toFixed(1); }).join(",");
    var url = WMS_TILES.replace("{bbox-epsg-3857}", bbox);
    var t0 = performance.now();
    return withTimeout(fetch(url, { mode: "cors", cache: "no-store" }), timeoutMs || 15000, "Imagery request")
      .then(function (r) {
        if (!r.ok) throw new Error("server answered HTTP " + r.status);
        var type = r.headers.get("content-type") || "";
        if (type.indexOf("image/") !== 0) throw new Error("got " + (type || "no content type") + " instead of an image (a proxy login page?)");
        return r.blob();
      })
      .then(function (blob) { return decode(blob).then(function (img) { return [blob, img]; }); })
      .then(function (pair) {
        var ms = Math.round(performance.now() - t0);
        var spread = brightnessSpread(pair[1]);
        var data = { ms: ms, bytes: pair[0].size, brightness_spread: Math.round(spread * 10) / 10 };
        if (spread < 3) return { ok: true, warn: true, detail: "Loaded, but the image is blank (" + ms + " ms)", data: data };
        return { ok: true, warn: ms > 5000, detail: "One tile in " + ms + " ms (" + Math.round(pair[0].size / 1024) + " kB)", data: data };
      })
      .catch(function (e) {
        var msg = e.message === "Failed to fetch" || e.name === "TypeError"
          ? "Blocked or offline (" + e.message + "). The network may block minkarta.lantmateriet.se."
          : e.message;
        return { ok: false, warn: false, detail: msg, data: null };
      });
  }

  root.AuditCommon = {
    WMS_TILES: WMS_TILES,
    WMS_MAXZOOM: WMS_MAXZOOM,
    mercator: mercator,
    webglInfo: webglInfo,
    withTimeout: withTimeout,
    checkTile: checkTile
  };
})(typeof window !== "undefined" ? window : globalThis);
