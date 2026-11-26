/* Survivor Fantasy League: static leaderboard + results views.
   Reads data/index.json and data/seasonNN.json (written by build_site.py).

   Points are scored per elimination (the data calls these "weeks"). The
   Elimination/Episode toggle regroups them: Episode mode sums an episode's
   eliminations, so a double-elimination episode is one column. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const main = $("#main"), tip = $("#tip"), seasonSel = $("#season");
  const cache = {};
  let index = [];

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (Math.round(n * 10) / 10).toLocaleString();
  const signed = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt(Math.abs(n));
  const color = (slot) => `var(--s${slot})`;
  const swatch = (slot) => `<span class="swatch" style="background:${color(slot)}"></span>`;
  const ordinal = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
  const CATS = ["challenges", "votes", "survival", "special"];

  // ---------- unit: elimination or episode (remembered per viewer) ----------
  let unit = "elim";
  try { if (localStorage.getItem("sfl-unit") === "ep") unit = "ep"; } catch (e) { /* storage blocked */ }
  function setUnit(u) {
    unit = u;
    try { localStorage.setItem("sfl-unit", u); } catch (e) { /* storage blocked */ }
  }
  const U = () => (unit === "ep"
    ? { word: "Episode", short: "Ep", lower: "episode" }
    : { word: "Elimination", short: "Elim", lower: "elimination" });

  /** The season's columns for the current unit: [{key, label, idx:[week indexes], weeks:[...]}] */
  function units(d) {
    if (unit === "elim") return d.weeks.map((w, i) => ({ key: w.week, label: String(w.week), idx: [i], weeks: [w] }));
    const out = [];
    d.weeks.forEach((w, i) => {
      let u = out[out.length - 1];
      if (!u || u.key !== w.episode) out.push((u = { key: w.episode, label: String(w.episode), idx: [], weeks: [] }));
      u.idx.push(i); u.weeks.push(w);
    });
    return out;
  }
  const sumIdx = (arr, idx) => idx.reduce((t, i) => t + arr[i], 0);
  const ownerVals = (o, us) => us.map((u) => sumIdx(o.weekly, u.idx));
  const contVals = (c, u) => {
    const r = { total: 0 }; CATS.forEach((k) => (r[k] = 0));
    u.idx.forEach((i) => { CATS.forEach((k) => (r[k] += c.weekly[i][k])); r.total += c.weekly[i].total; });
    return r;
  };

  // ---------- routing: #/47/results/elim/5  or  #/47/results/ep/13 ----------
  function parseHash() {
    const p = location.hash.replace(/^#\/?/, "").split("/");
    const season = +p[0] || null;
    let view = p[1] || "leaderboard", u = null, arg = null;
    if (view === "weeks") { view = "results"; u = "elim"; arg = +p[2] || null; } // old links
    else if (view === "results") { u = p[2] === "ep" ? "ep" : p[2] === "elim" ? "elim" : null; arg = +p[3] || null; }
    return { season, view, unit: u, arg };
  }
  const link = (season, view, u, arg) => `#/${season}/${view}${view === "results" && u ? `/${u}${arg ? "/" + arg : ""}` : ""}`;

  async function getJSON(url) {
    if (!cache[url]) {
      const r = await fetch(url, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${url}: ${r.status}`);
      cache[url] = await r.json();
    }
    return cache[url];
  }

  let lastPage = "", current = null;
  async function route() {
    hideTip();
    let { season, view, unit: hashUnit, arg } = parseHash();
    if (!season || !index.some((s) => s.season === season)) season = (index.find((s) => !s.test) || index[0]).season;
    if (hashUnit && hashUnit !== unit) setUnit(hashUnit);
    if (lastPage && lastPage !== `${season}/${view}`) scrollTo(0, 0); // new view: start at top; new elimination: stay put
    lastPage = `${season}/${view}`;
    seasonSel.value = season;
    if (window.SFLDraft) window.SFLDraft.stop();
    if (window.SFLReview) window.SFLReview.stop();
    document.body.classList.toggle("career-view", view === "career" || view === "draft");
    if (view === "draft") {
      current = null;
      document.querySelectorAll(".tabs a").forEach((a) => {
        a.href = link(season, a.dataset.view, unit);
        if (a.dataset.view === "draft") a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      });
      $("#subtitle").textContent = "Draft room";
      document.title = "Draft · Survivor Fantasy League";
      await window.SFLDraft.renderDraft(main, { getJSON, toast });
      return;
    }
    if (view === "career") {
      const c = await getJSON("data/career.json");
      current = null;
      document.querySelectorAll(".tabs a").forEach((a) => {
        a.href = link(season, a.dataset.view, unit);
        if (a.dataset.view === "career") a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      });
      $("#subtitle").textContent = "All seasons";
      document.title = "All time · Survivor Fantasy League";
      renderCareer(c);
      return;
    }
    const d = await getJSON(`data/season${season}.json`);
    current = { d, view, arg };
    document.querySelectorAll(".tabs a").forEach((a) => {
      a.href = link(season, a.dataset.view, unit);
      if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.unit === unit)));
    const us = units(d), last = us[us.length - 1];
    $("#subtitle").textContent = `${d.title}${d.test ? " (test)" : ""} · ${d.complete ? "Final standings" : last ? `Through ${U().lower} ${last.label}` : "Rosters set"}`;
    $("#built").textContent = `Scores last built ${new Date(d.built).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}.`;
    document.title = `${d.title} · Survivor Fantasy League`;
    if (view === "review") { await window.SFLReview.renderReview(main, d, { getJSON, toast }); return; }
    if (!last) { renderPreseason(d); return; }   // drafted, nothing scored yet
    if (view === "results") renderResults(d, arg || last.key);
    else if (view === "contestants") renderContestants(d);
    else renderLeaderboard(d);
  }

  // switching unit keeps you on the same moment of the season
  function onUnitClick(u) {
    if (u === unit || !current) return;
    const { d, view, arg } = current;
    let target = null;
    if (view === "results" && arg) {
      if (u === "ep") target = (d.weeks.find((w) => w.week === arg) || {}).episode;           // elim -> its episode
      else target = (d.weeks.find((w) => w.episode === arg) || {}).week;                     // episode -> its first elim
    }
    setUnit(u);
    if (view === "results") location.hash = link(d.season, "results", u, target);
    else route();
  }

  // ---------- helpers ----------
  const ownerBy = (d) => Object.fromEntries(d.owners.map((o) => [o.name, o]));
  const contBy = (d) => Object.fromEntries(d.contestants.map((c) => [c.name, c]));
  // a contestant can be on two rosters (double picks); unowned shows a dash
  const ownerCell = (c, ob) => (c.owners || []).length
    ? c.owners.map((n) => ob[n]).filter(Boolean).map((o) => `<span class="who">${swatch(o.slot)}${esc(o.name)}</span>`).join(" ")
    : '<span class="muted">—</span>';
  const isOut = (c) => c.status.kind === "out" || c.status.kind === "quit";
  function statusTag(c, d) {
    const s = c.status;
    if (s.kind === "winner") return "Winner";
    if (s.kind === "finalist") return ordinal(s.place);
    if (s.kind === "out" || s.kind === "quit") {
      const where = unit === "ep" ? `ep ${d.weeks[s.week - 1].episode}` : `elim ${s.week}`;
      return s.kind === "quit" ? `quit ${where}` : `out ${where}`;
    }
    return "";
  }
  // finish order: still in the game first, then by place (1 = winner)
  const placeKey = (c) => (c.place == null ? 0 : c.place);
  const byTotal = (a, b) => b.total - a.total || placeKey(a) - placeKey(b);

  /** Owner ranks after each unit, for rank movement. */
  function ranksAt(d, us, upto) {
    const cum = d.owners.map((o) => ({ o, v: sumIdx(o.weekly, us.slice(0, upto + 1).flatMap((u) => u.idx)) }));
    cum.sort((a, b) => b.v - a.v);
    return Object.fromEntries(cum.map((x, i) => [x.o.name, i + 1]));
  }

  const testBanner = (d) => d.test
    ? `<p class="note warn"><b>Test season.</b> Made-up rosters for trying things out; this never counts toward All time.</p>` : "";

  // ---------- rosters set, no eliminations scored yet ----------
  function renderPreseason(d) {
    const cb = contBy(d);
    const rows = [...d.owners].sort((a, b) => a.slot - b.slot).map((o) => `<div class="owner-row">
        <div class="rank">–</div>
        <div class="owner-name">${swatch(o.slot)}${esc(o.name)}</div>
        <div class="owner-total"><div class="big">0</div></div>
        <div class="roster">${o.roster.map((n) => `<span class="chip"><span class="nm">${esc(n)}</span></span>`).join("")}</div>
      </div>`).join("");
    main.innerHTML = `${testBanner(d)}
      <section class="section card"><h2>Rosters are set</h2>
        <p>No eliminations have been scored yet. Scoring starts with elimination ${d.first_week_boot ?? "?"} of the season; results show up here after it airs and survivoR adds it.</p></section>
      <section class="section"><h2>Rosters</h2><div class="standings">${rows}</div></section>`;
  }

  // ---------- leaderboard ----------
  function renderLeaderboard(d) {
    const cb = contBy(d), us = units(d), n = us.length, last = us[n - 1];
    const prev = n > 1 ? ranksAt(d, us, n - 2) : {};
    const ranked = [...d.owners].sort((a, b) => a.rank - b.rank);
    const rows = ranked.map((o) => {
      const mv = prev[o.name] ? prev[o.name] - o.rank : 0;
      const move = mv > 0 ? `<span class="move up" aria-label="up ${mv}">▲${mv}</span>`
        : mv < 0 ? `<span class="move down" aria-label="down ${-mv}">▼${-mv}</span>` : "";
      const chips = o.roster.map((nm) => cb[nm]).filter(Boolean).sort(byTotal).map((c) => {
        const tag = statusTag(c, d);
        return `<span class="chip${isOut(c) ? " out" : ""}"><span class="nm">${esc(c.name)}</span><b>${fmt(c.total)}</b>${tag ? `<span class="tag">${esc(tag)}</span>` : ""}</span>`;
      }).join("");
      const lastPts = sumIdx(o.weekly, last.idx);
      return `<div class="owner-row">
        <div class="rank">${o.rank}</div>
        <div class="owner-name">${swatch(o.slot)}${esc(o.name)} ${move}</div>
        <div class="owner-total"><div class="big">${fmt(o.total)}</div><div class="delta">${signed(lastPts)} in ${U().short.toLowerCase()} ${last.label}</div></div>
        <div class="roster">${chips}</div>
      </div>`;
    }).join("");
    const ob = ownerBy(d);
    const official = d.official ? `<section class="section card official">
        <h2>Official final result</h2>
        <div class="official-row">${d.official.map(([name, pts], i) => `<span class="who">${i === 0 ? "🏆 " : ""}${ob[name] ? swatch(ob[name].slot) : ""}<b>${esc(name)}</b> <span class="num">${fmt(pts)}</span></span>`).join("")}</div>
        <p class="note">From the league sheet, as it was played. The standings and detail below are recalculated from survivoR with today's rules, so they can differ.</p>
      </section>` : "";
    main.innerHTML = `${testBanner(d)}${official}
      <section class="section"><h2>${d.official ? "Recalculated standings" : "Standings"}</h2><div class="standings">${rows}</div></section>
      <section class="section card">
        <h2>The race</h2>
        <p class="note" style="margin:-4px 0 10px">Running total by ${U().lower}. Hover or tap for the numbers.</p>
        <div class="legend">${d.owners.map((o) => `<span>${swatch(o.slot)}${esc(o.name)}</span>`).join("")}</div>
        <div class="chart" id="race"></div>
      </section>`;
    raceChart($("#race"), d, us);
  }

  function niceStep(range, count) {
    const raw = range / count, mag = 10 ** Math.floor(Math.log10(raw));
    const n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }

  function raceChart(el, d, us) {
    const series = d.owners.map((o) => {
      const pts = [0]; let run = 0;
      ownerVals(o, us).forEach((v) => pts.push((run += v)));
      return { o, pts };
    });
    lineChart(el, {
      labels: us.map((u) => u.label), axisWord: U().short, series,
      aria: `Running total points by ${U().lower} for each owner`,
      title: (i) => `${U().word} ${us[i - 1].label} · ${us[i - 1].weeks.map((w) => esc(w.eliminated)).join(", ")} out`,
    });
  }

  /** Cumulative line chart. series[k].pts[0] is the start (0); null = not playing yet. */
  function lineChart(el, { labels, axisWord, series, aria, title, startLabel = "Start" }) {
    const n = labels.length;
    const val = (s, i) => s.pts[i];
    const draw = () => {
      const W = Math.max(280, el.clientWidth), H = W < 520 ? 240 : 300;
      const m = { l: 40, r: 64, t: 12, b: 28 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const all = series.flatMap((s) => s.pts).filter((v) => v != null);
      const step = niceStep(Math.max(1, Math.max(...all) - Math.min(0, ...all)), 4);
      const yMin = Math.floor(Math.min(0, ...all) / step) * step;
      const yMax = Math.ceil(Math.max(...all) / step) * step || step;
      const x = (i) => m.l + (iw * i) / n;
      const y = (v) => m.t + ih - ((v - yMin) / (yMax - yMin)) * ih;
      let g = "";
      for (let v = yMin; v <= yMax + 1e-9; v += step) {
        g += `<line class="${v === 0 ? "baseline" : "gridline"}" x1="${m.l}" x2="${m.l + iw}" y1="${y(v)}" y2="${y(v)}"/>`;
        g += `<text class="tick" x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
      }
      const every = n > 14 && W < 520 ? 3 : n > 8 && W < 520 ? 2 : 1;
      for (let i = 1; i <= n; i++) if ((n - i) % every === 0) // always label the latest
        g += `<text class="tick" x="${x(i)}" y="${H - 8}" text-anchor="middle">${labels[i - 1]}</text>`;
      g += `<text class="tick" x="${m.l}" y="${H - 8}" text-anchor="start">${axisWord}</text>`;
      const lines = series.map((s) => {
        let d = "", pen = false;
        s.pts.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
        return `<path class="series" stroke="${color(s.o.slot)}" d="${d}"/>`;
      }).join("");
      // end labels, nudged apart so they never overlap
      const ends = series.filter((s) => val(s, n) != null).map((s) => ({ name: s.o.name, y: y(val(s, n)) })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
      const over = ends.length ? ends[ends.length - 1].y - (m.t + ih + 4) : 0;
      if (over > 0) ends.forEach((e) => (e.y -= over));
      const endLabels = ends.map((e) => `<text class="endlabel" x="${x(n) + 8}" y="${e.y + 4}">${esc(e.name)}</text>`).join("");
      el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(aria)}">
        ${g}${lines}${endLabels}<g id="hover"></g>
        <rect x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent" id="hit"/></svg>`;
      const hover = $("#hover", el), hit = $("#hit", el), svg = $("svg", el);
      const show = (ev) => {
        const r = svg.getBoundingClientRect();
        const px = ((ev.clientX - r.left) / r.width) * W;
        const i = Math.max(0, Math.min(n, Math.round(((px - m.l) / iw) * n)));
        const live = series.filter((s) => val(s, i) != null);
        hover.innerHTML = `<line class="cross" x1="${x(i)}" x2="${x(i)}" y1="${m.t}" y2="${m.t + ih}"/>` +
          live.map((s) => `<circle class="dot" r="4.5" cx="${x(i)}" cy="${y(val(s, i))}" fill="${color(s.o.slot)}"/>`).join("");
        const rowsHtml = [...live].sort((a, b) => val(b, i) - val(a, i)).map((s) => {
          const prev = i ? val(s, i - 1) : null;
          return `<div class="r"><span>${swatch(s.o.slot)}${esc(s.o.name)}</span><span class="num">${fmt(val(s, i))}${prev != null ? ` <span class="muted">(${signed(val(s, i) - prev)})</span>` : ""}</span></div>`;
        }).join("");
        showTip(`<div class="t">${i ? title(i) : startLabel}</div>${rowsHtml}`, ev.clientX, ev.clientY);
      };
      hit.addEventListener("pointermove", show);
      hit.addEventListener("pointerdown", show);
      hit.addEventListener("pointerleave", () => { hover.innerHTML = ""; hideTip(); });
    };
    draw();
    new ResizeObserver(() => { if (el.isConnected) draw(); }).observe(el);
  }

  function showTip(html, cx, cy) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = cx + 14, top = cy + 14;
    if (left + r.width > innerWidth - 8) left = cx - r.width - 14;
    if (top + r.height > innerHeight - 8) top = cy - r.height - 14;
    tip.style.left = Math.max(8, left) + "px"; tip.style.top = Math.max(8, top) + "px";
  }
  function hideTip() { tip.hidden = true; }
  function toast(text) {
    let t = $("#toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = text; t.hidden = false;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.hidden = true; }, 2500);
  }

  // ---------- results (by elimination or by episode) ----------
  function eliminationFacts(w) {
    const facts = [["Eliminated", `<b>${esc(w.eliminated)}</b>`]];
    if (w.rounds && w.rounds.length) w.rounds.forEach((r, i) =>
      facts.push([w.rounds.length > 1 ? (i ? "Revote" : "First vote") : "The vote", r.map(([t, n]) => `${esc(t)} ${n}`).join(", ") || "—"]));
    else if (!w.jury) facts.push(["The vote", "No vote"]);
    (w.idol_plays || []).forEach((p) => facts.push(["Idol played", `${esc(p.player)}${p.votes_negated ? ` (cancelled ${p.votes_negated} vote${p.votes_negated > 1 ? "s" : ""})` : " (no votes cancelled)"}`]));
    w.challenges.forEach((c) => facts.push([c.label, c.players.map(esc).join(", ")]));
    w.specials.forEach((s) => facts.push([s.label, esc(s.player)]));
    (w.adjustments || []).forEach((a) => facts.push(["Adjustment",
      `${esc(a.player)} ${a.points > 0 ? "+" : ""}${fmt(a.points)} ${esc(a.category)}${a.reason ? ` <span class="muted">(${esc(a.reason)})</span>` : ""}`]));
    if (w.jury) facts.push(["Jury votes", w.jury.map(([t, n]) => `${esc(t)} ${n}`).join(", ")]);
    return `<ul class="facts">${facts.map(([k, v]) => `<li><span class="k">${esc(k)}</span><span>${v}</span></li>`).join("")}</ul>`;
  }

  function renderResults(d, key) {
    const us = units(d);
    const pos = Math.max(0, us.findIndex((u) => u.key === key));
    const u = us[pos >= 0 ? pos : us.length - 1];
    const ob = ownerBy(d);
    const vals = d.owners.map((o) => ({ o, v: ownerVals(o, us) }));
    const best = us.map((_, i) => Math.max(...vals.map((x) => x.v[i])));
    const ranked = [...vals].sort((a, b) => a.o.rank - b.o.rank);
    const W = U();

    const matrix = `<div class="table-wrap"><table>
      <thead><tr><th>Owner</th>${us.map((x) => `<th class="${x.key === u.key ? "cur" : ""}"><a href="${link(d.season, "results", unit, x.key)}" aria-label="${W.word} ${x.label}">${x.label}</a></th>`).join("")}<th class="total">Total</th></tr></thead>
      <tbody>${ranked.map(({ o, v }) => `<tr><td><span class="who">${swatch(o.slot)}${esc(o.name)}</span></td>${v.map((p, i) =>
        `<td class="${p === best[i] && p > 0 ? "best" : p === 0 ? "zero" : p < 0 ? "neg" : ""}">${fmt(p)}</td>`).join("")}<td class="total">${fmt(o.total)}</td></tr>`).join("")}</tbody>
    </table></div><p class="note">Columns are ${W.lower}s${unit === "ep" ? " (an episode with two eliminations adds both)" : ""}. Underlined = top owner. Click a number for details.</p>`;

    const pills = us.map((x) => `<button class="pill" data-k="${x.key}" aria-pressed="${x.key === u.key}">${x.label}${unit === "ep" && x.weeks.length > 1 ? "<small>×2</small>" : ""}</button>`).join("");

    // what happened: one block per elimination, in order
    const story = u.weeks.map((w, i) => `<div class="elim-block">
        ${unit === "ep" ? `<h3>Elimination ${w.week}${u.weeks.length > 1 ? ` · ${ordinal(i + 1)} of ${u.weeks.length} this episode` : ""}</h3>` : ""}
        ${eliminationFacts(w)}</div>`).join("");

    // owner points in this unit
    const here = vals.map(({ o, v }) => ({ o, p: v[pos] }));
    const max = Math.max(1, ...here.map((x) => Math.abs(x.p)));
    const bars = [...here].sort((a, b) => b.p - a.p).map(({ o, p }) =>
      `<div class="bar-row"><span class="who">${swatch(o.slot)}${esc(o.name)}</span>
        <div class="bar-track"><div class="bar" style="width:${(Math.max(0, p) / max) * 100}%;background:${color(o.slot)}"></div></div>
        <span class="bar-val">${fmt(p)}</span></div>`).join("");

    // contestants who scored or were still in
    const firstIdx = u.idx[0];
    const outHere = Object.fromEntries(u.weeks.map((w, i) => [w.eliminated, u.weeks.length > 1 ? `out ${ordinal(i + 1)}` : "out"]));
    const people = d.contestants.map((c) => ({ c, s: contVals(c, u) }))
      .filter(({ c, s }) => s.total !== 0 || !(isOut(c) && c.status.week - 1 < firstIdx))
      .sort((a, b) => b.s.total - a.s.total || placeKey(a.c) - placeKey(b.c));
    const cell = (v, cls = "") => `<td class="${cls} ${v === 0 ? "zero" : v < 0 ? "neg" : ""}">${fmt(v)}</td>`;
    const ctable = `<div class="table-wrap"><table>
      <thead><tr><th>Contestant</th><th style="text-align:left">Owner</th><th>Challenges</th><th>Votes</th><th>Survival</th><th>Special</th><th class="total">Total</th></tr></thead>
      <tbody>${people.map(({ c, s }) => {
        return `<tr><td>${esc(c.name)}${outHere[c.name] ? ` <span class="muted">· ${outHere[c.name]}</span>` : ""}</td>
          <td style="text-align:left">${ownerCell(c, ob)}</td>
          ${CATS.map((k) => cell(s[k])).join("")}${cell(s.total, "total")}</tr>`;
      }).join("")}</tbody></table></div>`;

    const head = unit === "ep"
      ? `<h2>Episode ${u.label}</h2><span class="ink2">${u.weeks.length > 1 ? `Eliminations ${u.weeks[0].week}–${u.weeks[u.weeks.length - 1].week}` : `Elimination ${u.weeks[0].week}`}</span>`
      : `<h2>Elimination ${u.label}</h2><span class="ink2">Episode ${u.weeks[0].episode}</span>`;

    main.innerHTML = `
      <section class="section"><h2>Points by ${W.lower}</h2>${matrix}</section>
      <section class="section">
        <div class="pills" role="group" aria-label="Pick ${unit === "ep" ? "an episode" : "an elimination"}">${pills}</div>
        <div class="week-head">${head}</div>
        <div class="grid2">
          <div class="card"><h2>What happened</h2>${story}</div>
          <div class="card"><h2>Owner points this ${W.lower}</h2><div class="bars">${bars}</div></div>
        </div>
      </section>
      <section class="section"><h2>Contestant scoring, ${W.lower} ${u.label}</h2>${ctable}</section>`;
    main.querySelectorAll(".pill").forEach((b) => b.addEventListener("click", () => { location.hash = link(d.season, "results", unit, b.dataset.k); }));
  }

  // ---------- all time (career) ----------
  let careerRange = "all";
  function renderCareer(c) {
    const seasons = c.seasons.filter((s) => careerRange === "all" || s.season >= 45);
    const slot = (n) => c.owner_slots[n] || 9;
    const names = [...new Set(seasons.flatMap((s) => Object.keys(s.totals)))].sort((a, b) => slot(a) - slot(b));
    const stats = names.map((n) => {
      const played = seasons.filter((s) => s.totals[n] != null);
      const total = played.reduce((t, s) => t + s.totals[n], 0);
      const wins = seasons.filter((s) => s.winner === n);
      const best = played.reduce((b, s) => (!b || s.totals[n] > b.totals[n] ? s : b), null);
      return { name: n, slot: slot(n), total, wins, played: played.length, avg: played.length ? total / played.length : 0, best };
    }).sort((a, b) => b.total - a.total);
    const o = (n) => ({ name: n, slot: slot(n) });

    const table = `<div class="table-wrap"><table>
      <thead><tr><th>Owner</th><th class="total">Points</th><th style="text-align:left">Wins</th><th>Seasons</th><th>Avg / season</th><th>Best season</th></tr></thead>
      <tbody>${stats.map((s, i) => `<tr>
        <td><span class="who"><b>${i + 1}</b> ${swatch(s.slot)}${esc(s.name)}</span></td>
        <td class="total">${fmt(s.total)}</td>
        <td style="text-align:left"><span class="who"><b class="num">${s.wins.length}</b><span class="wins">${s.wins.map((w) => `<i title="S${w.season}" style="background:${color(s.slot)}"></i>`).join("")}</span></span></td>
        <td>${s.played}</td><td>${fmt(Math.round(s.avg * 10) / 10)}</td>
        <td>${s.best ? `${fmt(s.best.totals[s.name])} <span class="muted">(S${s.best.season})</span>` : "—"}</td></tr>`).join("")}</tbody></table></div>`;

    const series = names.map((n) => {
      const pts = [null]; let run = null;
      seasons.forEach((s) => {
        const v = s.totals[n];
        if (v == null && run == null) { pts.push(null); return; }
        if (run == null) { pts[pts.length - 1] = 0; run = 0; }
        run += v || 0; pts.push(run);
      });
      return { o: o(n), pts };
    });

    const head = `<thead><tr><th>Season</th><th style="text-align:left">Winner</th>${names.map((n) => `<th><span class="who">${swatch(slot(n))}${esc(n)}</span></th>`).join("")}<th style="text-align:left">Source</th></tr></thead>`;
    const rows = [...seasons].reverse().map((s) => {
      const top = Math.max(...Object.values(s.totals));
      return `<tr class="season-link" tabindex="0" data-s="${s.season}">
        <td>S${s.season}</td>
        <td style="text-align:left">${s.winner ? `<span class="who">${swatch(slot(s.winner))}${esc(s.winner)}</span>` : '<span class="muted">in progress</span>'}</td>
        ${names.map((n) => s.totals[n] == null ? `<td class="gone">·</td>` : `<td class="${s.winner && s.totals[n] === top ? "best" : ""}">${fmt(s.totals[n])}</td>`).join("")}
        <td style="text-align:left" class="src">${s.source === "official" ? "Official" : "Calculated"}</td></tr>`;
    }).join("");

    main.innerHTML = `
      <section class="section">
        <div class="week-head" style="justify-content:space-between">
          <h2>All-time standings</h2>
          <div class="seg" role="group" aria-label="Seasons to include">
            <button type="button" data-range="all" aria-pressed="${careerRange === "all"}">All seasons</button>
            <button type="button" data-range="s45" aria-pressed="${careerRange === "s45"}">Since S45</button>
          </div>
        </div>
        ${table}
        <p class="note">${careerRange === "all" ? `Seasons ${seasons[0].season}–${seasons[seasons.length - 1].season}. Will joined in S45, so "Since S45" compares all five owners over the same seasons.` : "Seasons 45 onward, when all five owners played."}</p>
      </section>
      <section class="section card">
        <h2>Points over time</h2>
        <p class="note" style="margin:-4px 0 10px">Running total by season. Hover or tap for the numbers.</p>
        <div class="legend">${names.map((n) => `<span>${swatch(slot(n))}${esc(n)}</span>`).join("")}</div>
        <div class="chart" id="career-chart"></div>
      </section>
      <section class="section"><h2>Season by season</h2>
        <div class="table-wrap"><table>${head}<tbody>${rows}</tbody></table></div>
        <p class="note">Official = the league sheet's final totals, as played (through S${c.official_through}). Calculated = scored from survivoR with today's rules. Underlined = season winner. Click a season to open it.</p>
      </section>`;
    lineChart($("#career-chart"), {
      labels: seasons.map((s) => String(s.season)), axisWord: "S", series, startLabel: "Before",
      aria: "Running total points by season for each owner",
      title: (i) => { const s = seasons[i - 1]; return `Season ${s.season}${s.winner ? ` · ${esc(s.winner)} won` : ""}`; },
    });
    main.querySelectorAll("[data-range]").forEach((b) => b.addEventListener("click", () => { careerRange = b.dataset.range; renderCareer(c); }));
    main.querySelectorAll("tr.season-link").forEach((tr) => {
      const go = () => { location.hash = link(+tr.dataset.s, "leaderboard"); };
      tr.addEventListener("click", go);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    });
  }

  // ---------- contestants ----------
  let sortKey = "total", openRow = null;
  const SORTS = {
    total: byTotal,
    finish: (a, b) => placeKey(a) - placeKey(b) || b.total - a.total,
    name: (a, b) => a.name.localeCompare(b.name),
    owner: (a, b) => (a.owners[0] || "~").localeCompare(b.owners[0] || "~") || byTotal(a, b),
  };
  function renderContestants(d) {
    const ob = ownerBy(d), us = units(d);
    const rows = [...d.contestants].sort(SORTS[sortKey]);
    const head = (key, label, cls = "") => `<th class="${cls} ${sortKey === key ? "cur" : ""}"><button class="sort" data-sort="${key}">${label}${sortKey === key ? " ↓" : ""}</button></th>`;
    const body = rows.map((c) => {
      const goneIdx = isOut(c) ? c.status.week - 1 : Infinity; // last week index they played
      const tds = us.map((u) => {
        const v = contVals(c, u).total;
        return u.idx[0] > goneIdx && v === 0 ? `<td class="gone">·</td>` : `<td class="${v === 0 ? "zero" : v < 0 ? "neg" : ""}">${fmt(v)}</td>`;
      }).join("");
      const sums = CATS.map((k) => [k, c.weekly.reduce((t, s) => t + s[k], 0)]);
      const detail = openRow === c.name ? `<tr class="detail"><td colspan="${us.length + 4}"><div class="cats">
          <span><b>${esc(c.full_name)}</b></span>${sums.map(([k, v]) => `<span>${k[0].toUpperCase() + k.slice(1)}: <b class="num">${fmt(v)}</b></span>`).join("")}
        </div></td></tr>` : "";
      return `<tr class="clickable" data-name="${esc(c.name)}" tabindex="0" aria-expanded="${openRow === c.name}">
        <td>${esc(c.name)}</td>
        <td style="text-align:left">${ownerCell(c, ob)}</td>
        <td style="text-align:left" class="ink2">${isOut(c) && c.place ? `${ordinal(c.place)} <span class="muted">· ${esc(statusTag(c, d))}</span>` : esc(statusTag(c, d)) || "Still in"}</td>
        ${tds}<td class="total">${fmt(c.total)}</td></tr>${detail}`;
    }).join("");
    main.innerHTML = `<section class="section"><h2>Every contestant, every ${U().lower}</h2>
      <div class="table-wrap"><table>
        <thead><tr>${head("name", "Contestant")}${head("owner", "Owner", "left")}${head("finish", "Finish", "left")}${us.map((u) => `<th>${u.label}</th>`).join("")}${head("total", "Total", "total")}</tr></thead>
        <tbody>${body}</tbody></table></div>
      <p class="note">Columns are ${U().lower}s. Ties on total go to the better finish. Tap a row for the category breakdown.</p></section>`;
    main.querySelectorAll("button.sort").forEach((b) => b.addEventListener("click", () => { sortKey = b.dataset.sort; renderContestants(d); }));
    main.querySelectorAll("tr.clickable").forEach((tr) => {
      const toggle = () => { openRow = openRow === tr.dataset.name ? null : tr.dataset.name; renderContestants(d); };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    });
  }

  // ---------- commissioner sign-in (footer) ----------
  function renderCommishBar(v) {
    const bar = $("#commish-bar");
    if (!bar || !window.FIREBASE_CONFIG || window.SFLStore.PRACTICE) return;
    if (!v.ready) { bar.innerHTML = ""; return; }
    if (!v.uid) {
      bar.innerHTML = `<button class="linkish" id="cm-in">Commissioner sign-in</button>`;
    } else if (v.isCommish) {
      bar.innerHTML = `Signed in as the commissioner · <button class="linkish" id="cm-out">Sign out</button>`;
    } else if (!v.configured) {
      bar.innerHTML = `Signed in. Your commissioner ID: <code>${esc(v.uid)}</code> <button class="linkish" id="cm-copy">copy</button>. Send it to finish setup · <button class="linkish" id="cm-out">Sign out</button>`;
    } else {
      bar.innerHTML = `Signed in, but not as the commissioner · <button class="linkish" id="cm-out">Sign out</button>`;
    }
    $("#cm-in")?.addEventListener("click", async () => {
      try { await window.SFLAuth.signIn(); }
      catch (e) {
        alert(/operation-not-allowed|configuration-not-found/.test(e.code || "")
          ? "Google sign-in isn't turned on in Firebase yet (Firebase console → Authentication → Sign-in method → Google)."
          : /unauthorized-domain/.test(e.code || "")
          ? "This web address isn't allowed to sign in yet (Firebase console → Authentication → Settings → Authorized domains)."
          : `Sign-in didn't work (${e.code || e.message}).`);
      }
    });
    $("#cm-out")?.addEventListener("click", () => window.SFLAuth.signOut());
    $("#cm-copy")?.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(v.uid); toast("Copied your commissioner ID."); } catch (e) { prompt("Copy this ID:", v.uid); }
    });
  }

  // ---------- boot ----------
  async function boot() {
    try {
      index = await getJSON("data/index.json");
      getJSON("data/meta.json").then((m) => {   // footer: how fresh survivoR is
        if (!m || !m.survivor_updated) return;
        const d = new Date(m.survivor_updated).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
        $("#source-date").textContent = `, last updated ${d} (through Survivor ${m.through_season}, episode ${m.through_episode})`;
      }).catch(() => { /* footer just omits the date */ });
      seasonSel.innerHTML = index.map((s) => `<option value="${s.season}">${esc(s.title)}${s.test ? " (test)" : s.complete ? "" : " (live)"}</option>`).join("");
      seasonSel.addEventListener("change", () => { location.hash = link(seasonSel.value, parseHash().view, unit); });
      document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => onUnitClick(b.dataset.unit)));
      addEventListener("hashchange", route);
      if (window.SFLAuth) window.SFLAuth.onChange(renderCommishBar);
      await route();
    } catch (e) {
      main.innerHTML = `<p class="empty">Couldn't load the league data (${esc(e.message)}).</p>`;
    }
  }
  boot();
})();
