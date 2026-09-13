import { initializeApp } from "firebase/app";
import { getAuth, GithubAuthProvider, GoogleAuthProvider } from "firebase/auth";

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

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export const githubProvider = new GithubAuthProvider();
