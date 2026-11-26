/* Shared storage for the draft room and the review screen.

   SFLStore.open(collection) -> { mode, subscribe(key, cb, onErr), mutate(key, fn) }
     mode "live":     Firestore doc <collection>/<key>, field "state" = JSON string,
                      changes go through a transaction (window.FIREBASE_CONFIG set)
     mode "practice": ?practice in the URL — this browser only, never Firestore
     mode "test":     no Firebase config — this browser only
   mutate(key, fn): fn(current state or null) returns the new state (null deletes). */
(() => {
  "use strict";
  const PRACTICE = /[?&]practice\b/.test(location.search);

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
  function firestore(config) {
    if (!fbPromise) fbPromise = (async () => {
      const v = "10.12.2";
      const app = await import(`https://www.gstatic.com/firebasejs/${v}/firebase-app.js`);
      const fs = await import(`https://www.gstatic.com/firebasejs/${v}/firebase-firestore.js`);
      return { fs, db: fs.getFirestore(app.initializeApp(config)) };
    })();
    return fbPromise;
  }

  async function firebaseStore(collection, config) {
    const { fs, db } = await firestore(config);
    const ref = (k) => fs.doc(db, collection, k);
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
  }

  window.SFLStore = {
    PRACTICE,
    async open(collection) {
      if (PRACTICE) return localStore(collection, "practice");
      if (window.FIREBASE_CONFIG) return firebaseStore(collection, window.FIREBASE_CONFIG);
      return localStore(collection, "test");
    },
  };
})();
