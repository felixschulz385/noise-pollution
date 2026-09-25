// Offset maths for the audit, pure functions (tested from Node).
//
// A task carries the barrier line in local metres (EPSG:3006, relative to
// the view centre) and in lon/lat, the unit tangent `t` and left normal `n`
// of its digitised direction around the centre, and the Jacobian J of
// (lon, lat) with respect to (x, y) there. The map is rotated so `n` is
// screen-up. A pan of the map centre by `dm` metres splits into
// d = dm·n (the offset: the overlay is the line offset by d, so it stays put
// on screen across the road) and dm·t (along the road: logged, ignored).
(function (root) {
  "use strict";

  var MAX_MITER = 4;

  function apply(J, v) { return [J[0][0] * v[0] + J[0][1] * v[1], J[1][0] * v[0] + J[1][1] * v[1]]; }

  function inverse(J) {
    var det = J[0][0] * J[1][1] - J[0][1] * J[1][0];
    return [[J[1][1] / det, -J[0][1] / det], [-J[1][0] / det, J[0][0] / det]];
  }

  function dot(a, b) { return a[0] * b[0] + a[1] * b[1]; }

  function unit(v) {
    var len = Math.hypot(v[0], v[1]);
    return len > 0 ? [v[0] / len, v[1] / len] : [0, 0];
  }

  function leftNormal(a, b) {
    var u = unit([b[0] - a[0], b[1] - a[1]]);
    return [-u[1], u[0]];
  }

  // Map centre (lon, lat) -> {d, along}: its displacement from the task's
  // start centre, in metres across (along n) and along (t) the barrier.
  function decompose(task, lon, lat) {
    var dm = apply(inverse(task.jacobian), [lon - task.center[0], lat - task.center[1]]);
    return { d: dot(dm, task.normal), along: dot(dm, task.tangent) };
  }

  // Map centre at offset d across and `along` metres along the barrier
  // from the start centre: the inverse of decompose.
  function centerAt(task, d, along) {
    var a = along || 0;
    var dm = [d * task.normal[0] + a * task.tangent[0], d * task.normal[1] + a * task.tangent[1]];
    var dll = apply(task.jacobian, dm);
    return [task.center[0] + dll[0], task.center[1] + dll[1]];
  }

  // Per-vertex displacement (metres) of the parallel offset curve at
  // distance d, positive = left of the digitised direction; mitred joins,
  // capped at MAX_MITER·|d| so a sharp corner can't spike. Matches shapely's
  // offset_curve(d) on smooth lines.
  function offsetDisplacements(line, d) {
    var n = line.length, out = [];
    if (n < 2) return line.map(function () { return [0, 0]; });
    for (var i = 0; i < n; i++) {
      var before = i > 0 ? leftNormal(line[i - 1], line[i]) : null;
      var after = i < n - 1 ? leftNormal(line[i], line[i + 1]) : null;
      var m;
      if (!before) m = after;
      else if (!after) m = before;
      else {
        var bis = unit([before[0] + after[0], before[1] + after[1]]);
        var c = dot(bis, after);
        m = c > 1 / MAX_MITER ? [bis[0] / c, bis[1] / c] : [bis[0] * MAX_MITER, bis[1] * MAX_MITER];
        if (bis[0] === 0 && bis[1] === 0) m = after;
      }
      out.push([d * m[0], d * m[1]]);
    }
    return out;
  }

  // The overlay line in lon/lat: each original vertex moved by its offset
  // displacement, converted with J (small vectors: millimetre error).
  function overlayLonLat(task, d) {
    var disp = offsetDisplacements(task.line_m, d);
    return task.line_lonlat.map(function (p, i) {
      var dll = apply(task.jacobian, disp[i]);
      return [p[0] + dll[0], p[1] + dll[1]];
    });
  }

  // Street View camera for the current view: the point of the recorded line
  // nearest the view centre without its sideways shift (`along` metres along
  // t from the start centre), and the compass heading (degrees clockwise
  // from true north) of the line's digitised direction there. Looking that
  // way, the app's screen-up (left of the digitised direction) is on the
  // camera's left.
  function streetView(task, along) {
    var p = [along * task.tangent[0], along * task.tangent[1]];
    var line = task.line_m, best = null;
    for (var i = 0; i < line.length - 1; i++) {
      var a = line[i], ab = [line[i + 1][0] - a[0], line[i + 1][1] - a[1]];
      var len2 = dot(ab, ab);
      if (len2 === 0) continue;
      var s = Math.max(0, Math.min(1, dot([p[0] - a[0], p[1] - a[1]], ab) / len2));
      var q = [a[0] + s * ab[0], a[1] + s * ab[1]];
      var dist = Math.hypot(p[0] - q[0], p[1] - q[1]);
      if (!best || dist < best.dist) best = { dist: dist, q: q, dir: ab };
    }
    if (!best) best = { q: [0, 0], dir: task.tangent };
    var ll = apply(task.jacobian, best.q), dll = apply(task.jacobian, best.dir);
    var lat = task.center[1] + ll[1];
    var heading = Math.atan2(dll[0] * Math.cos(lat * Math.PI / 180), dll[1]) * 180 / Math.PI;
    return { lon: task.center[0] + ll[0], lat: lat, heading: (heading + 360) % 360 };
  }

  // Google Maps URLs (no API key): opens the panorama nearest the viewpoint.
  function streetViewUrl(sv) {
    return "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + sv.lat.toFixed(6) + "," +
      sv.lon.toFixed(6) + "&heading=" + (Math.round(sv.heading) % 360);
  }

  // MapLibre zoom (512 px world at z0) showing `viewM` metres across `widthPx`.
  function zoomFor(lat, widthPx, viewM) {
    var metresPerPxAtZ0 = 40075016.686 * Math.cos(lat * Math.PI / 180) / 512;
    return Math.log(metresPerPxAtZ0 * widthPx / viewM) / Math.LN2;
  }

  var api = {
    inverse: inverse,
    decompose: decompose,
    centerAt: centerAt,
    offsetDisplacements: offsetDisplacements,
    overlayLonLat: overlayLonLat,
    streetView: streetView,
    streetViewUrl: streetViewUrl,
    zoomFor: zoomFor
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.AuditGeometry = api;
})(typeof window !== "undefined" ? window : globalThis);
