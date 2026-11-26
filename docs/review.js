/* Scoring review: the commissioner's calls on things survivoR can't judge, plus
   manual point adjustments. Saved per season in Firestore reviews/sNN (practice
   and test modes keep it in this browser). build_site.py reads it on the next
   update and rescores the current season; finished seasons are locked.

   State: { decisions: { "<item id>": "award" | "none" },
            adjust: [{ id, week, player, category, points, reason, at }] } */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CATS = ["challenges", "votes", "survival", "special"];
  // what "award" means per kind (matches REVIEW_KINDS in survivor_data.py)
  const KINDS = {
    advantage_played: { award: "+5 advantage used", none: "No points",
      text: (r) => `${r.castaway} played ${aOrAn(r.advantage)}${r.played_for && r.played_for !== r.castaway ? ` for ${r.played_for}` : ""}`,
      help: "Award +5 if the advantage was successfully used." },
    shared_idol_found: { award: "+10 each", none: "No points",
      text: (r) => `${r.castaway} found a hidden immunity idol together`,
      help: "An idol found by several people at once. Award +10 to each, or nobody." },
    handed_out_idol: { award: "+10 idol found", none: "No points",
      text: (r) => `${r.castaway} got a hidden immunity idol (${(r.location || "handed out").toLowerCase()})`,
      help: "This idol was given out rather than found (e.g. at a summit). By default it doesn't earn the +10." },
    idol_never_active: { award: "−20 anyway", none: "No penalty",
      text: (r) => `${r.castaway} was voted out holding an idol that never had power`,
      help: "A Beware idol whose condition was never met couldn't have saved them, so by default there's no −20." },
  };
  function aOrAn(w) { return /^[aeiou]/i.test(w || "") ? `an ${w}` : `a ${w}`; }

  let unsub = null;
  const stop = () => { if (unsub) { unsub(); unsub = null; } };

  async function renderReview(main, d, h) {
    stop();
    const key = `s${d.season}`;
    const locked = !!d.complete;
    const weeks = d.weeks || [];
    const elimLabel = (k) => { const w = weeks.find((x) => x.week === k); return w ? `Elimination ${k} (${w.eliminated} out, ep ${w.episode})` : `Elimination ${k}`; };
    let store;
    try { store = await window.SFLStore.open("reviews"); }
    catch (e) { main.innerHTML = `<p class="empty">Couldn't reach the review data (${esc(e.message)}).</p>`; return; }

    const banner = store.mode === "practice"
      ? `<p class="note warn"><b>Practice.</b> Decisions here are saved only in this browser and never affect scores.</p>`
      : store.mode === "test" ? `<p class="note warn">Test mode: decisions are saved only in this browser.</p>` : "";

    const draw = (st) => {
      st = st || { decisions: {}, adjust: [] };
      const decided = (r) => st.decisions[r.id] || r.decision || null;
      const items = d.review || [];
      const waiting = items.filter((r) => !decided(r)).length;
      const header = `<section class="section card">
          <h2>Scoring review · ${esc(d.title)}${d.test ? " (test)" : ""}</h2>
          ${locked
            ? `<p><b>This season is finished and locked.</b> Its scores never change, so nothing here can be edited.</p>`
            : `<p>Calls survivoR can't make on its own, plus manual adjustments. Decisions are saved for everyone and show on the leaderboard at the next update (daily around 10am Eastern, or run <b>Update scores</b> on GitHub).</p>
               <p class="note">${items.length ? `${waiting ? `<b>${waiting} waiting</b> for a decision.` : "Everything has a decision."} Undecided items score nothing.` : ""} Anyone with the link can change these, so this page is for the commissioner.</p>`}
        </section>`;

      // judgment calls, grouped by elimination
      const byWeek = {};
      items.forEach((r) => (byWeek[r.week] ||= []).push(r));
      const calls = items.length ? Object.keys(byWeek).map(Number).sort((a, b) => a - b).map((k) => `
          <div class="review-group"><div class="review-week">${esc(elimLabel(k))}</div>
          ${byWeek[k].map((r) => {
            const K = KINDS[r.kind]; const dec = decided(r);
            const facts = [r.success && `survivoR: ${r.success}`, r.votes_nullified != null && `${r.votes_nullified} vote(s) cancelled`].filter(Boolean).join(" · ");
            return `<div class="review-item${dec ? "" : " pending"}">
              <div><div class="review-text">${esc(K.text(r))}</div>
                <div class="note">${esc(K.help)}${facts ? ` <span class="muted">(${esc(facts)})</span>` : ""}</div></div>
              <div class="seg" role="group" aria-label="Decision">
                ${["award", "none"].map((c) => `<button type="button" data-id="${esc(r.id)}" data-choice="${c}" aria-pressed="${dec === c}" ${locked ? "disabled" : ""}>${esc(K[c])}</button>`).join("")}
              </div></div>`;
          }).join("")}</div>`).join("")
        : `<p class="muted">${weeks.length ? "Nothing needs a decision." : "Nothing to review yet: no eliminations have been scored this season."}</p>`;

      // manual adjustments
      const adjRows = (st.adjust || []).map((a) => `<tr>
          <td>${esc(elimLabel(a.week))}</td><td style="text-align:left">${esc(a.player)}</td><td style="text-align:left">${esc(a.category)}</td>
          <td class="${a.points < 0 ? "neg" : ""}">${a.points > 0 ? "+" : ""}${esc(a.points)}</td><td style="text-align:left">${esc(a.reason)}</td>
          <td>${locked ? "" : `<button class="linkish rm-adj" data-id="${esc(a.id)}">remove</button>`}</td></tr>`).join("");
      const players = (d.contestants || []).map((c) => c.name).sort();
      const form = locked || !weeks.length ? "" : `<div class="adj-form">
          <label>Elimination <select id="adj-week">${weeks.map((w) => `<option value="${w.week}">${esc(elimLabel(w.week))}</option>`).join("")}</select></label>
          <label>Contestant <select id="adj-player">${players.map((p) => `<option>${esc(p)}</option>`).join("")}</select></label>
          <label>Category <select id="adj-cat">${CATS.map((c) => `<option ${c === "votes" ? "selected" : ""}>${c}</option>`).join("")}</select></label>
          <label>Points <input id="adj-pts" type="number" step="1" value="2" style="width:70px"></label>
          <label class="grow">Reason <input id="adj-reason" type="text" placeholder="e.g. split vote: alliance credit"></label>
          <button class="btn" id="adj-add">Add adjustment</button></div>`;

      main.innerHTML = `${banner}${header}
        <section class="section"><h2>Judgment calls</h2>${calls}</section>
        <section class="section"><h2>Adjustments</h2>
          <p class="note" style="margin-top:-4px">For anything else: alliance credit on a split vote, a survivoR mistake, a missed event. Points add to that elimination's category.</p>
          ${adjRows ? `<div class="table-wrap"><table><thead><tr><th>Elimination</th><th style="text-align:left">Contestant</th><th style="text-align:left">Category</th><th>Points</th><th style="text-align:left">Reason</th><th></th></tr></thead><tbody>${adjRows}</tbody></table></div>` : `<p class="muted">No adjustments.</p>`}
          ${form}
        </section>`;

      const save = async (fn) => {
        try { await store.mutate(key, (cur) => fn(cur || { decisions: {}, adjust: [] })); }
        catch (e) { alert(e.message); }
      };
      main.querySelectorAll("button[data-choice]").forEach((b) => b.addEventListener("click", () => {
        const { id, choice } = b.dataset;
        save((cur) => ({ ...cur, decisions: { ...cur.decisions, [id]: choice } }));
      }));
      main.querySelectorAll(".rm-adj").forEach((b) => b.addEventListener("click", () => {
        if (!confirm("Remove this adjustment?")) return;
        save((cur) => ({ ...cur, adjust: (cur.adjust || []).filter((a) => a.id !== b.dataset.id) }));
      }));
      main.querySelector("#adj-add")?.addEventListener("click", () => {
        const pts = Number(main.querySelector("#adj-pts").value);
        const reason = main.querySelector("#adj-reason").value.trim();
        if (!pts) { alert("Enter a non-zero number of points."); return; }
        if (!reason) { alert("Add a short reason so everyone knows what it's for."); return; }
        const a = { id: `${Date.now()}-${Math.floor(Math.random() * 1e6)}`, week: Number(main.querySelector("#adj-week").value),
                    player: main.querySelector("#adj-player").value, category: main.querySelector("#adj-cat").value,
                    points: pts, reason: reason.slice(0, 200), at: new Date().toISOString() };
        save((cur) => ({ ...cur, adjust: [...(cur.adjust || []), a] }));
      });
    };

    if (locked) { draw(null); return; }  // finished seasons: read-only, nothing to load
    main.innerHTML = `<p class="empty">Loading the review…</p>`;
    unsub = store.subscribe(key, draw, (e) => {
      const rules = /permission/i.test(e.message || "");
      main.innerHTML = `<p class="empty">${rules
        ? "The review screen can't save yet: the Firebase rules need the new <b>reviews</b> section. Paste <code>firestore.rules</code> into Firebase console → Firestore → Rules and publish."
        : `Couldn't load the review (${esc(e.message)}).`}</p>`;
    });
  }

  window.SFLReview = { renderReview, stop };
})();
