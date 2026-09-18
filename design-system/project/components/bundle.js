/* @ds-bundle: {"format":4,"namespace":"NebulaWayside","components":[{"name":"StatusChip"},{"name":"VerdictCard"},{"name":"DamageGauge"},{"name":"DoorTimeline"},{"name":"AxleGrid"},{"name":"CarRank"}]} */
(function (global) {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";

  // ---- tiny DOM helpers -------------------------------------------------
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = String(text);
    return n;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    if (attrs) for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, String(attrs[k]));
    return n;
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  // ---- state vocabulary -------------------------------------------------
  // Four states, and only four. Each carries a glyph so colour is never the
  // only signal - see the README, "Colour is never the only signal".
  var STATES = {
    ok:      { word: "Normal",  glyph: "●", token: "status-ok" },
    watch:   { word: "Watch",   glyph: "◐", token: "status-watch" },
    alert:   { word: "Fault",   glyph: "✕", token: "status-alert" },
    unknown: { word: "Unknown", glyph: "—", token: "status-unknown" }
  };
  function state(s) { return STATES[s] || STATES.unknown; }

  // Sequential magnitude: five steps, one hue, ordered by lightness.
  function rampVar(t) {
    var step = clamp(Math.ceil(clamp(t, 0, 1) * 5), 1, 5);
    return "var(--ramp-" + step + ")";
  }

  // ---- StatusChip -------------------------------------------------------
  function StatusChip(opts) {
    opts = opts || {};
    var st = state(opts.state);
    var root = el("span", "nw-chip nw-chip--" + (opts.state in STATES ? opts.state : "unknown"));
    root.setAttribute("role", "status");
    root.appendChild(el("span", "nw-chip__glyph", st.glyph)).setAttribute("aria-hidden", "true");
    root.appendChild(el("span", "nw-chip__word", opts.label || st.word));
    if (opts.detail) root.appendChild(el("span", "nw-chip__detail", opts.detail));
    return root;
  }

  // ---- VerdictCard ------------------------------------------------------
  // The four-part answer: state, meaning, action, evidence.
  function VerdictCard(opts) {
    opts = opts || {};
    var root = el("article", "nw-card");
    var head = el("header", "nw-card__head");
    head.appendChild(StatusChip({ state: opts.state }));
    if (opts.subsystem) head.appendChild(el("span", "nw-card__subsystem", opts.subsystem));
    root.appendChild(head);

    if (opts.title) root.appendChild(el("h3", "nw-card__title", opts.title));
    if (opts.meaning) root.appendChild(el("p", "nw-card__meaning", opts.meaning));

    if (opts.figure) {
      var fig = el("div", "nw-card__figure");
      fig.appendChild(opts.figure);
      root.appendChild(fig);
    }
    if (opts.action) {
      var act = el("p", "nw-card__action");
      act.appendChild(el("strong", null, "Action — "));
      act.appendChild(document.createTextNode(opts.action));
      root.appendChild(act);
    }
    if (opts.evidence) root.appendChild(el("p", "nw-card__evidence", opts.evidence));
    return root;
  }

  // ---- DamageGauge ------------------------------------------------------
  function DamageGauge(opts) {
    opts = opts || {};
    var value = Number(opts.value) || 0;
    var max = Number(opts.max) || 1;
    var t = clamp(value / max, 0, 1);

    var root = el("div", "nw-gauge");
    if (opts.label) root.appendChild(el("div", "nw-gauge__label", opts.label));

    var v = el("div", "nw-gauge__value", value.toFixed(opts.precision == null ? 3 : opts.precision));
    root.appendChild(v);

    var W = 320, H = 14;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", height: H, role: "img" });
    s.appendChild(svg("rect", { x: 0, y: 0, width: W, height: H, rx: 4, fill: "var(--surface-sunken)" }));
    s.appendChild(svg("rect", { x: 0, y: 0, width: Math.max(2, W * t), height: H, rx: 4, fill: rampVar(t) }));
    // Failure threshold: Miner's rule says damage reaches 1.0 at failure.
    if (opts.threshold != null) {
      var tx = clamp(Number(opts.threshold) / max, 0, 1) * W;
      s.appendChild(svg("line", { x1: tx, y1: -2, x2: tx, y2: H + 2, stroke: "var(--ink-primary)", "stroke-width": 2 }));
    }
    root.appendChild(s);

    var scale = el("div", "nw-gauge__scale");
    scale.appendChild(el("span", null, "0"));
    scale.appendChild(el("span", null, String(max)));
    root.appendChild(scale);

    if (opts.caption) root.appendChild(el("p", "nw-gauge__caption", opts.caption));
    return root;
  }

  // ---- DoorTimeline -----------------------------------------------------
  // A continuous stream cut into classified segments. Gaps are real: the
  // space between cycles is when the door was doing nothing.
  function DoorTimeline(opts) {
    opts = opts || {};
    var segs = opts.segments || [];
    var span = Number(opts.duration) || segs.reduce(function (m, s) { return Math.max(m, s.end); }, 1);

    var root = el("div", "nw-timeline");
    if (opts.label) root.appendChild(el("div", "nw-timeline__label", opts.label));

    var W = 640, H = 34;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", height: H });
    s.appendChild(svg("rect", { x: 0, y: 10, width: W, height: 14, rx: 3, fill: "var(--surface-sunken)" }));

    segs.forEach(function (seg) {
      var x = (seg.start / span) * W;
      var w = Math.max(3, ((seg.end - seg.start) / span) * W);
      var st = state(seg.status);
      var g = svg("g");
      var r = svg("rect", {
        x: x, y: 6, width: w, height: 22, rx: 3,
        fill: "var(--" + st.token + ")",
        stroke: "var(--surface-plot)", "stroke-width": 2
      });
      var title = svg("title");
      title.textContent = (seg.id ? seg.id + " — " : "") + st.word +
        " — " + seg.start.toFixed(1) + "s to " + seg.end.toFixed(1) + "s";
      g.appendChild(r);
      g.appendChild(title);
      s.appendChild(g);
    });
    root.appendChild(s);

    var ax = el("div", "nw-timeline__axis");
    ax.appendChild(el("span", null, "0 s"));
    ax.appendChild(el("span", null, span.toFixed(0) + " s"));
    root.appendChild(ax);

    if (opts.caption) root.appendChild(el("p", "nw-timeline__caption", opts.caption));
    return root;
  }

  // ---- AxleGrid ---------------------------------------------------------
  // 8 cars x 8 axle-box positions. Positions 1,3,5,7 are the Side I rail;
  // 2,4,6,8 are Side II. The two sides are judged independently, so they are
  // drawn as two bands rather than one 8x8 block.
  function AxleGrid(opts) {
    opts = opts || {};
    var cells = opts.cells || [];
    var lookup = {};
    cells.forEach(function (c) { lookup[c.car + ":" + c.position] = c; });

    var root = el("div", "nw-grid");
    if (opts.label) root.appendChild(el("div", "nw-grid__label", opts.label));

    var cars = opts.cars || 8;
    var CELL = 26, GAP = 4, PAD = 34;
    var bands = [
      { name: "Side I", positions: [1, 3, 5, 7] },
      { name: "Side II", positions: [2, 4, 6, 8] }
    ];
    var bandH = 4 * (CELL + GAP);
    var W = PAD + cars * (CELL + GAP);
    var H = bands.length * (bandH + 26) + 16;
    var s = svg("svg", { viewBox: "0 0 " + W + " " + H, width: "100%" });

    bands.forEach(function (band, bi) {
      var y0 = bi * (bandH + 26);
      var lab = svg("text", { x: 0, y: y0 + 12, fill: "var(--ink-secondary)", "font-size": 11, "font-weight": 600 });
      lab.textContent = band.name;
      s.appendChild(lab);

      band.positions.forEach(function (pos, pi) {
        var y = y0 + 18 + pi * (CELL + GAP);
        var pl = svg("text", { x: 0, y: y + CELL * 0.68, fill: "var(--ink-muted)", "font-size": 10 });
        pl.textContent = "P" + pos;
        s.appendChild(pl);

        for (var car = 1; car <= cars; car++) {
          var c = lookup[car + ":" + pos];
          var t = c ? clamp(Number(c.value), 0, 1) : null;
          var g = svg("g");
          g.appendChild(svg("rect", {
            x: PAD + (car - 1) * (CELL + GAP), y: y, width: CELL, height: CELL, rx: 4,
            fill: t == null ? "var(--surface-sunken)" : rampVar(t),
            stroke: "var(--surface-plot)", "stroke-width": 2
          }));
          var ti = svg("title");
          ti.textContent = "Car " + car + ", position " + pos + " (" + band.name + ") — " +
            (t == null ? "no data" : t.toFixed(2));
          g.appendChild(ti);
          s.appendChild(g);
        }
      });
    });
    root.appendChild(s);

    var foot = el("div", "nw-grid__axis");
    for (var i = 1; i <= cars; i++) foot.appendChild(el("span", null, "C" + i));
    root.appendChild(foot);

    if (opts.caption) root.appendChild(el("p", "nw-grid__caption", opts.caption));
    return root;
  }

  // ---- CarRank ----------------------------------------------------------
  function CarRank(opts) {
    opts = opts || {};
    var cars = (opts.cars || []).slice();
    var top = cars.length ? Math.max.apply(null, cars.map(function (c) { return Number(c.score) || 0; })) : 1;

    var root = el("div", "nw-rank");
    if (opts.label) root.appendChild(el("div", "nw-rank__label", opts.label));

    var list = el("ol", "nw-rank__list");
    cars.forEach(function (c, i) {
      var row = el("li", "nw-rank__row" + (i === 0 ? " is-top" : ""));
      row.appendChild(el("span", "nw-rank__pos", String(i + 1)));
      row.appendChild(el("span", "nw-rank__car", "Car " + c.id));
      var track = el("span", "nw-rank__track");
      var fill = el("span", "nw-rank__fill");
      var frac = top > 0 ? (Number(c.score) || 0) / top : 0;
      fill.style.width = (clamp(frac, 0, 1) * 100).toFixed(1) + "%";
      fill.style.background = i === 0 ? "var(--status-alert)" : "var(--series-1)";
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "nw-rank__score", (Number(c.score) || 0).toFixed(2)));
      list.appendChild(row);
    });
    root.appendChild(list);

    if (opts.caption) root.appendChild(el("p", "nw-rank__caption", opts.caption));
    return root;
  }

  global.NebulaWayside = {
    STATES: STATES,
    StatusChip: StatusChip,
    VerdictCard: VerdictCard,
    DamageGauge: DamageGauge,
    DoorTimeline: DoorTimeline,
    AxleGrid: AxleGrid,
    CarRank: CarRank
  };
})(window);
