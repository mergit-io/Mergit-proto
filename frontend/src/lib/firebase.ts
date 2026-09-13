import { initializeApp } from "firebase/app";
import { getAuth, GithubAuthProvider, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyA_JsoXcYvF7KqpcIHMYt3qO8dAP5xSA-A",
  authDomain: "omnibox-8f73e.firebaseapp.com",
  projectId: "omnibox-8f73e",
  storageBucket: "omnibox-8f73e.firebasestorage.app",
  messagingSenderId: "649389772569",
  appId: "1:649389772569:web:f5e3336c41404c62eebf88",
  measurementId: "G-86W4XQ1X41",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export const githubProvider = new GithubAuthProvider();
