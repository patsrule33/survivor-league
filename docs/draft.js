/* Draft room: a randomized snake draft with no clock. Anyone can open the page,
   say who they are, and make their pick when it's their turn.

   State lives in one document per season. With window.FIREBASE_CONFIG set it is
   a Firestore doc (drafts/sNN, field "state" = JSON string); without it, test
   mode keeps it in this browser's localStorage. Picks go through a transaction,
   so two people can't take the same contestant or pick out of turn.

   State: { season, createdAt, startBoot, owners:[draft order], rosterSize,
            pool:[names in the game at the start], picks:[{owner, name, at}] } */
(() => {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- storage ----------
  // Practice mode (?practice in the URL): same draft room, but saved only in this
  // browser, never in Firestore, so nobody else sees it and nothing syncs.
  const PRACTICE = /[?&]practice\b/.test(location.search);

  function localStore(mode = "test") {
    const key = (k) => `sfl-${mode === "practice" ? "practice" : "draft"}-${k}`;
    const read = (k) => { try { return JSON.parse(localStorage.getItem(key(k)) || "null"); } catch (e) { return null; } };
    const listeners = new Set(); // the "storage" event only fires in *other* tabs
    return {
      mode,
      subscribe(k, cb) {
        cb(read(k));
        const on = (e) => { if (!e || e.key === key(k)) cb(read(k)); };
        addEventListener("storage", on); listeners.add(on);
        return () => { removeEventListener("storage", on); listeners.delete(on); };
      },
      async mutate(k, fn) {
        const next = fn(read(k));
        try { if (next === null) localStorage.removeItem(key(k)); else localStorage.setItem(key(k), JSON.stringify(next)); }
        catch (e) { throw new Error("This browser blocked saving (private window?)."); }
        listeners.forEach((on) => on(null));
        return next;
      },
    };
  }

  let fbPromise = null;
  async function firebaseStore(config) {
    if (!fbPromise) fbPromise = (async () => {
      const v = "10.12.2";
      const app = await import(`https://www.gstatic.com/firebasejs/${v}/firebase-app.js`);
      const fs = await import(`https://www.gstatic.com/firebasejs/${v}/firebase-firestore.js`);
      const db = fs.getFirestore(app.initializeApp(config));
      const ref = (k) => fs.doc(db, "drafts", k);
      const parse = (snap) => (snap.exists() ? JSON.parse(snap.data().state) : null);
      return {
        mode: "live",
        subscribe(k, cb, onErr) { return fs.onSnapshot(ref(k), (s) => cb(parse(s)), onErr); },
        async mutate(k, fn) {
          return fs.runTransaction(db, async (tx) => {
            const next = fn(parse(await tx.get(ref(k))));
            if (next === null) tx.delete(ref(k));
            else tx.set(ref(k), { state: JSON.stringify(next), updated: fs.serverTimestamp() });
            return next;
          });
        },
      };
    })();
    return fbPromise;
  }

  // ---------- draft logic ----------
  function shuffle(a) {
    a = [...a];
    for (let i = a.length - 1; i > 0; i--) {
      const r = new Uint32Array(1); crypto.getRandomValues(r);
      const j = r[0] % (i + 1); [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  const totalPicks = (s) => s.rosterSize * s.owners.length;
  function onClock(s, i = s.picks.length) {           // snake: 1..n, n..1, ...
    const n = s.owners.length, round = Math.floor(i / n), pos = i % n;
    return { owner: s.owners[round % 2 === 0 ? pos : n - 1 - pos], round: round + 1, pick: i + 1 };
  }
  // s.out = contestants the commissioner marked eliminated because survivoR
  // hasn't caught up yet; they leave the pool for everyone right away.
  function available(s, live) {
    const inGame = new Set(live.cast.filter((c) => c.in_game).map((c) => c.name));
    const taken = new Set(s.picks.map((p) => p.name));
    const out = new Set(s.out || []);
    return s.pool.filter((n) => !taken.has(n) && inGame.has(n) && !out.has(n));
  }
  const isDone = (s, live) => s.picks.length >= totalPicks(s) || available(s, live).length === 0;

  // ---------- view ----------
  let unsub = null, me = null;
  const preOut = new Set(); // marked "already out" before the draft starts
  let openCommish = false;  // keep Commissioner tools open across live redraws
  try { me = localStorage.getItem("sfl-me"); } catch (e) { /* storage blocked */ }

  async function renderDraft(main, h) {
    if (unsub) { unsub(); unsub = null; }
    const live = await h.getJSON("data/live.json");
    const key = `s${live.season}`;
    let store;
    try {
      store = PRACTICE ? localStore("practice")
        : window.FIREBASE_CONFIG ? await firebaseStore(window.FIREBASE_CONFIG) : localStore("test");
    }
    catch (e) { main.innerHTML = `<p class="empty">Couldn't reach the shared draft (${esc(e.message)}).</p>`; return; }
    const slot = (o) => (live.owners.indexOf(o) + 1) || 9;
    const sw = (o) => `<span class="swatch" style="background:var(--s${slot(o)})"></span>`;
    const castBy = Object.fromEntries(live.cast.map((c) => [c.name, c]));
    const tribeDot = (c) => c && c.tribe ? `<span class="tribe" style="--tc:${esc(c.tribe_colour || "#888")}">${esc(c.tribe)}</span>` : "";

    const draw = (s) => {
      const base = location.pathname;
      const banner = store.mode === "practice"
        ? `<p class="note warn"><b>Practice draft.</b> Saved only in this browser; nobody else sees it and it never counts. Switch "I'm" to whoever is on the clock to play every owner. <a href="${base}#/${live.season}/draft">Leave practice</a></p>`
        : store.mode === "test"
        ? `<p class="note warn">Test mode: picks are saved only in this browser. Add the Firebase config to share the draft with everyone.</p>`
        : "";
      const practiceLink = store.mode === "live"
        ? `<p class="note">Want to try it first? <a href="${base}?practice#/${live.season}/draft">Open a practice draft</a> (only you see it; nothing is saved for anyone else).</p>` : "";
      const whoami = `<label class="whoami">I'm <select id="me"><option value="">choose…</option>${live.owners.map((o) => `<option ${o === me ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;

      if (!s) {
        const listed = live.cast.filter((c) => c.in_game).map((c) => c.name);
        [...preOut].forEach((n) => { if (!listed.includes(n)) preOut.delete(n); });
        const inGame = listed.filter((n) => !preOut.has(n));
        const size = Math.floor(inGame.length / live.owners.length);
        const boots = live.boots_so_far + preOut.size;
        main.innerHTML = `${banner}
          <section class="section card">
            <h2>No draft yet for ${esc(live.title)}</h2>
            <p>${inGame.length} contestants are still in the game after ${boots} eliminations, so each of the ${live.owners.length} owners would get <b>${size}</b> in a snake draft (order chosen at random).
            Scoring starts with the next elimination.${inGame.length % live.owners.length ? ` ${inGame.length % live.owners.length} contestant(s) will be left unowned.` : ""}</p>
            ${store.mode === "practice" ? "" : `<label class="testbox"><input type="checkbox" id="is-test"> <span><b>Test draft</b>: made-up rosters for trying things out. Shows on the site labelled "test", never counts toward All time, and deleting it later removes it everywhere.</span></label>`}
            <button class="btn" id="start" ${size < 1 ? "disabled" : ""}>${store.mode === "practice" ? "Start a practice draft" : "Start the draft"}</button>
            ${practiceLink}
          </section>
          <section class="section"><h2>Still in the game</h2>
            <p class="note" style="margin-top:-4px">survivoR is up to date through episode ${live.episodes_aired}. If someone has been voted out since, mark them <b>Already out</b> before starting.</p>
            ${poolList(listed, null, preOut)}</section>`;
        main.querySelector("#start")?.addEventListener("click", async () => {
          const outList = [...preOut];
          const isTest = !!main.querySelector("#is-test")?.checked;
          if (store.mode !== "practice" && !confirm(`Start the ${live.title} ${isTest ? "TEST " : ""}draft for everyone now? The order will be randomized.${isTest ? "\n\nTest draft: won't count toward All time." : ""}${outList.length ? `\n\nMarked already out: ${outList.join(", ")}` : ""}`)) return;
          try {
            await store.mutate(key, (cur) => {
              if (cur) throw new Error("A draft already exists.");
              // eliminations survivoR doesn't know about yet still move the scoring start
              return { season: live.season, createdAt: new Date().toISOString(), startBoot: boots + 1,
                       owners: shuffle(live.owners), rosterSize: size, pool: inGame, out: outList, picks: [],
                       test: isTest };
            });
            preOut.clear();
          } catch (e) { alert(e.message); }
        });
        main.querySelectorAll("button.preout").forEach((b) => b.addEventListener("click", () => {
          const n = b.dataset.name;
          if (preOut.has(n)) preOut.delete(n); else preOut.add(n);
          draw(null);
        }));
        return;
      }

      const done = isDone(s, live);
      const clock = done ? null : onClock(s);
      const avail = available(s, live);
      const mine = clock && me === clock.owner;
      const url = location.href.split("#")[0] + `#/${live.season}/draft`;
      const msg = clock ? `🔥 ${clock.owner}, you're up in the ${live.title} fantasy draft (round ${clock.round}, pick ${clock.pick}): ${url}` : "";
      const status = done
        ? `<div class="clock done">${store.mode === "practice"
            ? `<b>Practice draft complete.</b> Nothing was saved for anyone else. Clear it under Commissioner tools to go again.`
            : `<b>Draft complete.</b> The league page picks up these rosters at its next update.`}</div>`
        : `<div class="clock">${sw(clock.owner)}<div><div class="lbl">On the clock · round ${clock.round}, pick ${clock.pick} of ${totalPicks(s)}</div><div class="who-big">${esc(clock.owner)}</div></div>
           <div class="clock-actions">${whoami}<button class="btn ghost" id="copy">Copy "your turn" message</button></div></div>
           ${mine ? `<p class="note good">It's your pick. Choose a contestant below.</p>` : me ? `<p class="note">Waiting on ${esc(clock.owner)}.</p>` : `<p class="note">Choose who you are to make picks.</p>`}`;

      // board: rounds x owners in draft order
      const n = s.owners.length;
      const cell = (r, oi) => {
        const pos = r % 2 === 0 ? oi : n - 1 - oi;
        const p = s.picks[r * n + pos];
        const isNow = !done && r * n + pos === s.picks.length;
        const c = p && castBy[p.name];
        const gone = p && ((c && !c.in_game) || (s.out || []).includes(p.name));
        return `<td class="${isNow ? "now" : ""}">${p ? `<b>${esc(p.name)}</b>${gone ? ` <span class="muted">(out)</span>` : ""}` : isNow ? "on the clock" : ""}</td>`;
      };
      const board = `<div class="table-wrap"><table class="board">
        <thead><tr><th>Round</th>${s.owners.map((o) => `<th><span class="who">${sw(o)}${esc(o)}</span></th>`).join("")}</tr></thead>
        <tbody>${Array.from({ length: s.rosterSize }, (_, r) => `<tr><td>${r + 1}</td>${s.owners.map((_, oi) => cell(r, oi)).join("")}</tr>`).join("")}</tbody>
      </table></div>`;

      const testNote = s.test ? `<p class="note warn"><b>Test draft.</b> Made-up rosters for trying things out; never counts toward All time. Delete it under Commissioner tools whenever you're done (even after the season).</p>` : "";
      main.innerHTML = `${banner}${testNote}
        <section class="section">${status}</section>
        <section class="section"><h2>Draft board</h2>${board}
          <p class="note">Snake order: round 1 left to right, round 2 right to left, and so on. Scoring starts with elimination ${s.startBoot} of the season.</p>
          ${store.mode === "live" ? `<p class="note">Want to try drafting yourself? <a href="${base}?practice#/${live.season}/draft">Open a practice draft</a>: your own private draft from the current cast, on this device only. It doesn't touch this draft.</p>` : ""}</section>
        ${done ? "" : `<section class="section"><h2>Available (${avail.length})</h2>${poolList(avail, mine ? clock.owner : null)}</section>`}
        <details class="section commish"><summary>Commissioner tools</summary>
          <p class="note">Anyone can use these, so check with the family first.</p>
          <div class="commish-row">
            <label>Voted out but survivoR hasn't caught up?
              <select id="out-pick"><option value="">choose…</option>${avail.map((n) => `<option>${esc(n)}</option>`).join("")}</select></label>
            <button class="btn ghost" id="mark-out" ${avail.length ? "" : "disabled"}>Mark as eliminated</button>
          </div>
          ${(s.out || []).length ? `<div class="commish-row"><span class="muted">Marked eliminated:</span> ${(s.out || []).map((n) =>
            `<span class="chip">${esc(n)} <button class="linkish restore" data-name="${esc(n)}" aria-label="Restore ${esc(n)}">restore</button></span>`).join(" ")}</div>` : ""}
          <div class="commish-row">
            <button class="btn ghost" id="undo" ${s.picks.length ? "" : "disabled"}>Undo last pick${s.picks.length ? ` (${esc(s.picks[s.picks.length - 1].name)})` : ""}</button>
            <button class="btn danger" id="reset">Delete this draft</button>
          </div>
        </details>`;
      if (openCommish) main.querySelector("details.commish").open = true;
      main.querySelector("details.commish").addEventListener("toggle", (e) => { openCommish = e.target.open; });

      main.querySelector("#copy")?.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(msg); h.toast("Copied. Paste it in the family chat."); }
        catch (e) { prompt("Copy this message:", msg); }
      });
      main.querySelectorAll("button.pick").forEach((b) => b.addEventListener("click", async () => {
        const name = b.dataset.name;
        if (!confirm(`Draft ${name} for ${clock.owner}?`)) return;
        try {
          await store.mutate(key, (cur) => {
            if (!cur) throw new Error("The draft was deleted.");
            if (isDone(cur, live)) throw new Error("The draft is already complete.");
            const now = onClock(cur);
            if (now.owner !== me) throw new Error(`It's ${now.owner}'s turn now.`);
            if (!available(cur, live).includes(name)) throw new Error(`${name} isn't available anymore.`);
            return { ...cur, picks: [...cur.picks, { owner: me, name, at: new Date().toISOString() }] };
          });
        } catch (e) { alert(e.message); }
      }));
      main.querySelector("#mark-out")?.addEventListener("click", async () => {
        openCommish = true;
        const name = main.querySelector("#out-pick").value;
        if (!name) return;
        if (!confirm(`Mark ${name} as eliminated? They leave the pool for everyone.`)) return;
        try {
          await store.mutate(key, (cur) => {
            if (!cur) throw new Error("The draft was deleted.");
            if (cur.picks.some((p) => p.name === name)) throw new Error(`${name} was already drafted.`);
            return { ...cur, out: [...new Set([...(cur.out || []), name])] };
          });
        } catch (e) { alert(e.message); }
      });
      main.querySelectorAll("button.restore").forEach((b) => b.addEventListener("click", async () => {
        openCommish = true;
        const name = b.dataset.name;
        if (!confirm(`Put ${name} back in the pool?`)) return;
        try { await store.mutate(key, (cur) => ({ ...cur, out: (cur.out || []).filter((n) => n !== name) })); } catch (e) { alert(e.message); }
      }));
      main.querySelector("#undo")?.addEventListener("click", async () => {
        openCommish = true;
        const last = s.picks[s.picks.length - 1];
        if (!confirm(`Undo ${last.owner}'s pick of ${last.name}?`)) return;
        try { await store.mutate(key, (cur) => ({ ...cur, picks: cur.picks.slice(0, -1) })); } catch (e) { alert(e.message); }
      });
      main.querySelector("#reset")?.addEventListener("click", async () => {
        if (store.mode === "practice" ? !confirm("Clear this practice draft and start over?")
          : prompt(`This deletes the whole ${live.title} draft for everyone. Type DELETE to confirm.`) !== "DELETE") return;
        try { await store.mutate(key, () => null); } catch (e) { alert(e.message); }
      });
      wireMe();
    };

    // pickingFor: show Draft buttons. outToggle (a Set): pre-draft "Already out" toggles.
    function poolList(names, pickingFor, outToggle) {
      const groups = {};
      names.forEach((n) => { const c = castBy[n] || { name: n }; (groups[c.tribe || "—"] ||= []).push(c); });
      const action = (c) => pickingFor ? `<button class="btn small pick" data-name="${esc(c.name)}">Draft</button>`
        : outToggle ? `<button class="btn small ghost preout" data-name="${esc(c.name)}">${outToggle.has(c.name) ? "Restore" : "Already out"}</button>` : "";
      return Object.entries(groups).map(([t, cs]) => `<div class="pool-group">
          <div class="pool-tribe">${cs[0].tribe ? tribeDot(cs[0]) : esc(t)}</div>
          <div class="pool">${cs.map((c) => {
            const isOut = outToggle && outToggle.has(c.name);
            return `<div class="pool-item${isOut ? " marked-out" : ""}"><span>${esc(c.name)}${isOut ? ` <span class="muted">(out)</span>` : c.game_status && c.game_status !== "In the game" ? ` <span class="muted">(${esc(c.game_status)})</span>` : ""}</span>${action(c)}</div>`;
          }).join("")}</div>
        </div>`).join("") || `<p class="muted">Nobody left.</p>`;
    }
    function wireMe() {
      main.querySelector("#me")?.addEventListener("change", (e) => {
        me = e.target.value || null;
        try { if (me) localStorage.setItem("sfl-me", me); else localStorage.removeItem("sfl-me"); } catch (err) { /* storage blocked */ }
        draw(lastState);
      });
    }

    let lastState;
    main.innerHTML = `<p class="empty">Loading the draft…</p>`;
    unsub = store.subscribe(key, (s) => { lastState = s; draw(s); },
      (e) => { main.innerHTML = `<p class="empty">Couldn't load the draft (${esc(e.message)}).</p>`; });
  }

  window.SFLDraft = { renderDraft, stop: () => { if (unsub) { unsub(); unsub = null; } } };
})();
