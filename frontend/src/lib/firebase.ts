import { initializeApp } from "firebase/app";
import { getAuth, GithubAuthProvider, GoogleAuthProvider, type Auth } from "firebase/auth";

// Read from the environment rather than hardcoding a project. A Firebase project id is
// immutable, so the old one could never be renamed — only replaced. Keeping it in `.env`
// means the source tree names no project at all, and swapping projects is a config change
// instead of a code change.
//
// None of these are secrets: Firebase web config ships inside every client bundle by design,
// and access is controlled by Auth rules and API-key restrictions in the Firebase console.
// They live in `.env` for portability, not for confidentiality.
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

/** False when no project is configured — with `VITE_DEMO_MODE=true` nothing here is used. */
export const isAuthConfigured = Boolean(firebaseConfig.apiKey && firebaseConfig.projectId);

// Initialise ONLY when a project is configured. `getAuth()` throws `auth/invalid-api-key`
// on a missing key, and because this module is imported at the top of ProtectedRoute, that
// throw happens before React renders anything — the whole app dies with a blank page.
// A demo build (VITE_DEMO_MODE=true) has no Firebase project and must still boot.
let auth: Auth | null = null;
let googleProvider: GoogleAuthProvider | null = null;
let githubProvider: GithubAuthProvider | null = null;

if (isAuthConfigured) {
  const app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  googleProvider = new GoogleAuthProvider();
  githubProvider = new GithubAuthProvider();
}

export { auth, googleProvider, githubProvider };
