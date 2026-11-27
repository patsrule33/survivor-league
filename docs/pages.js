/* Rules page and owner pages.
   Rules: point values come from data/rules.json (written from scoring.py), so the
   page always matches how points are actually scored.
   Owners: data/owners.json (written by build_site.py). Season totals and wins are
   the career numbers (official through S47); "what works" compares picks by an
   index where 100 = the average owned pick that season. */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (Math.round(n * 10) / 10).toLocaleString();
  const pts = (n) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}`;
  const swatch = (slot) => `<span class="swatch" style="background:var(--s${slot})"></span>`;
  const ordinal = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");

  // ---------------- rules ----------------
  async function renderRules(main, h) {
    const R = await h.getJSON("data/rules.json");
    const C = R.challenge, S = R.special;
    const row = (what, value, note = "") => `<tr><td>${what}${note ? `<div class="note">${note}</div>` : ""}</td><td class="pts">${value}</td></tr>`;
    const table = (title, rows) => `<section class="section card rules"><h2>${title}</h2><table class="rules-table"><tbody>${rows.join("")}</tbody></table></section>`;
    main.innerHTML = `
      <section class="section card">
        <h2>How the league works</h2>
        <ul class="rules-list">
          <li><b>Draft.</b> The commissioner starts a snake draft in random order (1–5, then 5–1, …) whenever the family is ready, even mid-season. Everyone picks when they have time; there's no clock. The pool is whoever is still in the game; each owner gets the pool divided evenly, and any leftovers go unowned.</li>
          <li><b>Scoring starts</b> with the first elimination after the draft begins. Points are per contestant, and an owner's total is the sum of their roster.</li>
          <li><b>A "week" is one elimination</b> (one Tribal Council, medevac or quit). An episode with two eliminations counts as two; the Episode view adds them together.</li>
          <li><b>Scores come from survivoR</b>, a public Survivor dataset, and update every day. It usually adds an episode within a few days of airing, occasionally longer.</li>
        </ul>
      </section>
      ${table("Challenges", [
        row("Tribal immunity: 1st place", pts(C.tribal_immunity_1)),
        row("Tribal immunity: 2nd place", pts(C.tribal_immunity_2), "With three tribes, the second tribe to finish."),
        row("Tribal reward: 1st place", pts(C.tribal_reward_1)),
        row("Tribal reward: 2nd place", pts(C.tribal_reward_2)),
        row("Individual immunity", pts(C.indiv_immunity)),
        row("Individual reward", pts(C.indiv_reward), "After the merge, a team reward (split groups, schoolyard picks) pays each winner this."),
        row("Split-group immunity", pts(C.group_immunity), "Only the people who actually won it, not teammates along for the ride."),
        row("Combined reward + immunity challenge", "immunity only", "Pays the immunity points, not both."),
        row("Sat out but your side won", "still counts", ""),
      ])}
      ${table("Votes", [
        row("You voted for the person who went home", pts(R.vote_for_eliminated), "On a revote, only if you voted for them in the first round too."),
        row("You switched to them on the revote", pts(R.vote_switched_to_eliminated)),
        row("Each vote cast against you", pts(R.vote_received), "First round only. Votes cancelled by an idol don't count."),
        row("Tie and revote: the person voted out", pts(R.revote_eliminated_extra), "On top of the votes against them."),
        row("Each jury vote at Final Tribal", pts(R.jury_vote)),
        row("Vote steal or extra vote", "two ballots", "Each ballot counts on its own."),
        row("Didn't vote (lost vote, Shot in the Dark)", "no credit", "Even if your alliance got the person out. The commissioner can add credit for a planned split vote."),
      ])}
      ${table("Survival", [
        row("Surviving week 1, 2, 3, …", "+1, +2, +3, …", "Surviving week k earns k points, so lasting longer is worth more each week."),
        row("Finalists", "keep climbing", "In the final week, 3rd place earns that week's points, 2nd earns the next rung too, and the winner the rung after that."),
        row("On Edge of Extinction or Redemption Island", "nothing", "No survival points while away; they resume after returning. Exile Island still counts."),
      ])}
      ${table("Specials", [
        row("Found a hidden immunity idol", pts(S.idol_found), "Handed-out idols (e.g. at a summit) don't count. Earned ones do (bought, won at Ghost Island, made from halves). Several idols: each one counts."),
        row("Played an idol that saved someone", pts(S.idol_played_success), "Only if, without it, the person it was played for would have had the most votes (alone or tied)."),
        row("Used another advantage successfully", pts(S.advantage_used), "The commissioner decides each one on the Review page."),
        row("Voted out holding an idol", `${pts(S.idol_in_pocket)} per idol`, "Only if the idol had power. One that was never activated doesn't count."),
        row("Medically evacuated", pts(S.medevac_pity)),
        row("Quit", "loses everything", "All of that contestant's points are forfeited."),
      ])}
      <section class="section card">
        <h2>Commissioner and history</h2>
        <ul class="rules-list">
          <li><b>Review page.</b> survivoR can't judge everything, so the commissioner decides advantage plays and odd idol cases, and can add adjustments for anything else, such as a missed event or alliance credit on a split vote. Changes show at the next update.</li>
          <li><b>Only the commissioner</b> can start or delete a draft, undo picks, mark someone eliminated early, or edit the review.</li>
          <li><b>Finished seasons are locked.</b> If the rules change, only seasons after that are affected.</li>
          <li><b>All-time stats</b> use the official results as played through Season 47, and calculated results after that. Test seasons never count.</li>
        </ul>
      </section>`;
  }

  // ---------------- owners ----------------
  async function renderOwners(main, h, name) {
    const D = await h.getJSON("data/owners.json");
    const o = name && D.owners.find((x) => x.name.toLowerCase() === name.toLowerCase());
    if (!o) return ownerIndex(main, h, D);
    ownerPage(main, h, D, o);
  }

  function ownerIndex(main, h, D) {
    const cards = D.owners.map((o) => {
      const done = o.seasons.filter((s) => s.complete);
      return `<a class="owner-card" href="${h.ownerLink(o.name)}">
        <div class="owner-name">${swatch(o.slot)}${esc(o.name)}</div>
        <div class="owner-card-stats"><span><b>${o.wins.length}</b> win${o.wins.length === 1 ? "" : "s"}</span>
          <span><b>${done.length}</b> seasons</span><span><b>${fmt(Math.round(o.total))}</b> pts</span></div>
      </a>`;
    }).join("");
    main.innerHTML = `<section class="section"><h2>Owners</h2>
      <p class="note" style="margin-top:-4px">Each owner's record, best players, and what kinds of players score for them.</p>
      <div class="owner-cards">${cards}</div></section>`;
  }

  function ownerPage(main, h, D, o) {
    const L = D.league;
    const done = o.seasons.filter((s) => s.complete);
    const avgSeason = done.length ? done.reduce((t, s) => t + s.total, 0) / done.length : 0;
    const finish = (p) => (p.place === 1 ? "Winner" : p.place ? ordinal(p.place) : "still in");
    const tiles = [
      ["Championships", o.wins.length, o.wins.length ? o.wins.map((s) => `S${s}`).join(", ") : "none yet"],
      ["Seasons", done.length, `since S${o.seasons[0]?.season}`],
      ["All-time points", fmt(Math.round(o.total)), `${fmt(Math.round(avgSeason))} per season`],
      ["Best season", o.best ? fmt(o.best.total) : "—", o.best ? `S${o.best.season}` : ""],
      ["Drafted the winner", o.winners_drafted.length, o.winners_drafted.length ? o.winners_drafted.map((s) => `S${s}`).join(", ") : "not yet"],
      ["Pick quality", o.avg_index, "100 = an average pick"],
    ].map(([lbl, val, sub]) => `<div class="stat"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="sub2">${esc(sub)}</div></div>`).join("");

    const history = [...o.seasons].reverse().map((s) => `<tr class="season-link" data-s="${s.season}" tabindex="0">
        <td>S${s.season}</td><td>${fmt(s.total)}</td>
        <td style="text-align:left">${s.complete ? (s.won ? "🏆 1st" : s.rank ? `${ordinal(s.rank)} of ${s.of}` : "") : "in progress"}</td>
        <td style="text-align:left" class="src">${s.source === "official" ? "Official" : "Calculated"}</td></tr>`).join("");

    const players = (list, showIndex) => `<div class="table-wrap"><table>
      <thead><tr><th>Player</th><th>Season</th><th>${showIndex ? "vs avg pick" : "Points"}</th><th style="text-align:left">Finish</th></tr></thead>
      <tbody>${list.map((p) => `<tr><td>${esc(p.full_name || p.name)}</td><td>S${p.season}</td>
        <td><b>${showIndex ? `${p.index}` : fmt(p.points)}</b></td><td style="text-align:left">${esc(finish(p))}</td></tr>`).join("")}</tbody></table></div>`;

    // "what works": owner's index per group vs the league's
    const max = Math.max(150, ...Object.values(o.groups).flatMap((g) => Object.values(g).map((x) => x.avg)),
                         ...Object.values(L.groups).flatMap((g) => Object.values(g).map((x) => x.avg)));
    const order = { Age: ["Under 30", "30s", "40s", "50+"] };
    const dims = Object.keys(o.groups).map((dim) => {
      const groups = Object.keys(o.groups[dim]).sort((a, b) => (order[dim] ? order[dim].indexOf(a) - order[dim].indexOf(b) : a.localeCompare(b)));
      if (!groups.length) return "";
      const rows = groups.map((g) => {
        const mine = o.groups[dim][g], lg = (L.groups[dim] || {})[g];
        const cls = mine.avg >= 110 ? "good" : mine.avg <= 90 ? "bad" : "";
        return `<div class="ww-row">
          <div class="ww-label">${esc(g)} <span class="muted">${mine.n} pick${mine.n === 1 ? "" : "s"}</span></div>
          <div class="ww-track">
            <div class="ww-bar" style="width:${(mine.avg / max) * 100}%;background:var(--s${o.slot})"></div>
            <div class="ww-mark avg100" style="left:${(100 / max) * 100}%" title="Average pick (100)"></div>
            ${lg ? `<div class="ww-mark league" style="left:${(lg.avg / max) * 100}%" title="League: ${lg.avg}"></div>` : ""}
          </div>
          <div class="ww-val ${cls}">${Math.round(mine.avg)}${lg ? ` <span class="muted">league ${Math.round(lg.avg)}</span>` : ""}</div>
        </div>`;
      }).join("");
      return `<div class="ww-dim"><div class="ww-title">${esc(dim)}</div>${rows}</div>`;
    }).join("");

    const cats = ["challenges", "votes", "survival", "special"];
    const mix = `<div class="table-wrap"><table><thead><tr><th>Points from</th>${cats.map((c) => `<th>${c[0].toUpperCase() + c.slice(1)}</th>`).join("")}</tr></thead>
      <tbody><tr><td><span class="who">${swatch(o.slot)}${esc(o.name)}'s picks</span></td>${cats.map((c) => `<td><b>${o.mix[c]}%</b></td>`).join("")}</tr>
      <tr><td class="muted">League</td>${cats.map((c) => `<td class="muted">${L.mix[c]}%</td>`).join("")}</tr></tbody></table></div>`;

    // a plain-language headline from the biggest gaps vs the league
    const insights = [];
    Object.entries(o.groups).forEach(([dim, gs]) => Object.entries(gs).forEach(([g, v]) => {
      const lg = (L.groups[dim] || {})[g];
      if (v.n >= 4 && lg) insights.push({ g, diff: v.avg - lg.avg, v: v.avg, n: v.n });
    }));
    insights.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
    const top = insights.slice(0, 3).filter((x) => Math.abs(x.diff) >= 8);
    const who = (g) => ({ "Under 30": "Players under 30", "30s": "Players in their 30s", "40s": "Players in their 40s",
      "50+": "Players 50 and older", "White collar": "White-collar players", "Blue collar": "Blue-collar players",
      "No collar": "Players without a collar job (students, retirees…)" }[g] || g);
    const insightText = top.length ? `<ul class="rules-list">${top.map((x) => `<li><b>${esc(who(x.g))}</b> score ${x.diff > 0 ? "better" : "worse"} for ${esc(o.name)} than for the league: ${Math.round(x.v)} vs ${Math.round(x.v - x.diff)} (${x.n} picks).</li>`).join("")}</ul>` : `<p class="muted">No big differences from the league yet.</p>`;

    main.innerHTML = `
      <p class="note"><a href="${h.ownerLink("")}">← All owners</a></p>
      <section class="section"><div class="owner-head"><h2>${swatch(o.slot)}${esc(o.name)}</h2></div>
        <div class="stat-grid">${tiles}</div></section>
      <section class="section card"><h2>What works for ${esc(o.name)}</h2>
        ${insightText}
        <p class="note">Each pick is scored against that season's average owned pick (100 = average, 130 = 30% better), so long and short seasons compare fairly. Bars are ${esc(o.name)}'s picks; the dashed line is 100 and the dark tick is the league.</p>
        <div class="ww">${dims}</div>
        <h2 style="margin-top:18px">Where the points come from</h2>${mix}
      </section>
      <section class="section"><h2>Top players</h2>${players(o.top_players, false)}</section>
      <section class="section"><h2>Best value picks</h2><p class="note" style="margin-top:-4px">Biggest scores relative to that season's average pick.</p>${players(o.best_value, true)}</section>
      <section class="section"><h2>Season by season</h2>
        <div class="table-wrap"><table><thead><tr><th>Season</th><th>Points</th><th style="text-align:left">Finish</th><th style="text-align:left">Source</th></tr></thead><tbody>${history}</tbody></table></div>
        <p class="note">Official = the league sheet's result as played (through S47). Player points are recalculated from survivoR. Click a season to open it.</p>
      </section>`;
    main.querySelectorAll("tr.season-link").forEach((tr) => {
      const go = () => { location.hash = h.seasonLink(+tr.dataset.s); };
      tr.addEventListener("click", go);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    });
  }

  window.SFLPages = { renderRules, renderOwners };
})();
