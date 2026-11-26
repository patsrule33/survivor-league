/* Shared storage + commissioner sign-in for the draft room and the review screen.

   SFLStore.open(collection, {format}) -> { mode, subscribe(key, cb, onErr), mutate(key, fn) }
     mode "live":     Firestore doc <collection>/<key> (window.FIREBASE_CONFIG set);
                      changes go through a transaction
     mode "practice": ?practice in the URL — this browser only, never Firestore
     mode "test":     no Firebase config — this browser only
     format "json":   doc field "state" holds the state as a JSON string
     format "native": the state's fields are stored as real Firestore fields, so
                      security rules can check them (the draft room uses this)
   mutate(key, fn): fn(current state or null) returns the new state (null deletes).

   SFLAuth: commissioner sign-in (Google, via Firebase Auth).
     SFLAuth.state() -> { ready, user, uid, configured, isCommish }
     SFLAuth.onChange(cb), SFLAuth.signIn(), SFLAuth.signOut()
     SFLAuth.canCommish(store): may this page use commissioner tools? Always in
       practice/test mode; in live mode only the commissioner (or anyone until
       window.COMMISSIONER_UID is set, which is how it worked before). */
(() => {
  "use strict";
  const PRACTICE = /[?&]practice\b/.test(location.search);
  const V = "10.12.2";

  function localStore(collection, mode) {
    const key = (k) => `sfl-${mode}-${collection}-${k}`;
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

  let fbPromise = null; // one Firebase app for the whole page
  function firebase() {
    if (!fbPromise) fbPromise = (async () => {
      const app = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-app.js`);
      const fs = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-firestore.js`);
      const fbApp = app.initializeApp(window.FIREBASE_CONFIG);
      return { fs, db: fs.getFirestore(fbApp), app: fbApp };
    })();
    return fbPromise;
  }

  async function firebaseStore(collection, format) {
    const { fs, db } = await firebase();
    const ref = (k) => fs.doc(db, collection, k);
    const parse = (snap) => {
      if (!snap.exists()) return null;
      const data = snap.data();
      if (typeof data.state === "string") return JSON.parse(data.state);  // json format (or an older draft)
      const { updated, ...rest } = data;
      return rest;
    };
    const toDoc = (next) => (format === "native"
      ? { ...next, updated: fs.serverTimestamp() }
      : { state: JSON.stringify(next), updated: fs.serverTimestamp() });
    return {
      mode: "live",
      subscribe(k, cb, onErr) { return fs.onSnapshot(ref(k), (s) => cb(parse(s)), onErr); },
      async mutate(k, fn) {
        return fs.runTransaction(db, async (tx) => {
          const next = fn(parse(await tx.get(ref(k))));
          if (next === null) tx.delete(ref(k));
          else tx.set(ref(k), toDoc(next));
          return next;
        });
      },
    };
  }

  window.SFLStore = {
    PRACTICE,
    async open(collection, { format = "json" } = {}) {
      if (PRACTICE) return localStore(collection, "practice");
      if (window.FIREBASE_CONFIG) return firebaseStore(collection, format);
      return localStore(collection, "test");
    },
  };

  // ---------- commissioner sign-in ----------
  const listeners = new Set();
  let st = { ready: !window.FIREBASE_CONFIG, user: null, uid: null };
  const view = () => {
    const configured = !!window.COMMISSIONER_UID;
    return { ...st, configured, isCommish: configured && st.uid === window.COMMISSIONER_UID };
  };
  const emit = () => listeners.forEach((cb) => cb(view()));
  let authPromise = null;
  function auth() {
    if (!window.FIREBASE_CONFIG) return Promise.resolve(null);
    if (!authPromise) authPromise = (async () => {
      const { app } = await firebase();
      const a = await import(`https://www.gstatic.com/firebasejs/${V}/firebase-auth.js`);
      const au = a.getAuth(app);
      a.onAuthStateChanged(au, (u) => { st = { ready: true, user: u ? (u.displayName || "signed in") : null, uid: u ? u.uid : null }; emit(); });
      return { a, au };
    })();
    return authPromise;
  }

  window.SFLAuth = {
    state: view,
    onChange(cb) { listeners.add(cb); auth(); return () => listeners.delete(cb); },
    async signIn() {
      const x = await auth(); if (!x) return;
      const provider = new x.a.GoogleAuthProvider();
      try { await x.a.signInWithPopup(x.au, provider); }
      catch (e) {  // popup blocked (some phones): fall back to a full-page redirect
        if (/popup/i.test(e.code || "")) await x.a.signInWithRedirect(x.au, provider);
        else throw e;
      }
    },
    async signOut() { const x = await auth(); if (x) await x.a.signOut(x.au); },
    canCommish(store) {
      if (!store || store.mode !== "live") return true;
      const v = view();
      return !v.configured || v.isCommish;
    },
  };
  if (window.FIREBASE_CONFIG && !PRACTICE) auth();  // restore an existing sign-in early
})();
