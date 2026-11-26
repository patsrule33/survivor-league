/* Firebase web-app config for the shared draft room.
   (Firebase console -> Project settings -> Your apps -> Web app -> Config.)
   These values are not secrets: they identify the project, and Firestore security
   rules (firestore.rules) decide what anyone can do. Set to null for test mode,
   where picks are saved only in the current browser. */
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyAjJdpuTDcmjFvyZKh6uIihGEbgh0h0xNQ",
  authDomain: "patsrule33-survivor-league.firebaseapp.com",
  projectId: "patsrule33-survivor-league",
  storageBucket: "patsrule33-survivor-league.firebasestorage.app",
  messagingSenderId: "694623055376",
  appId: "1:694623055376:web:f91328f43dbd9346f82495",
};

/* The commissioner's Firebase user ID (a random code, not an email; safe to
   publish). Only this account can use commissioner tools; firestore.rules has
   the same ID. null = not set up yet, so anyone can use them (the old behavior). */
window.COMMISSIONER_UID = null;
