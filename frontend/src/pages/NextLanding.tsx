import { useEffect } from "react";
import { useSmoothScroll } from "../hooks/useSmoothScroll";
import { NextNav } from "../components/next/NextNav";
import { NextHero } from "../components/next/NextHero";
import {
  NextFooter,
  ProofEditorial,
  RunEditorial,
  StackEditorial,
} from "../components/next/NextSections";

/* The second landing: the same system, argued on paper instead of in a forest.
   It exists to be compared against `/` on a deployed URL — see
   docs/superpowers/specs/2026-09-10-next-landing-3d.md — so it is a real page
   with real content rather than a mock. */
export function NextLanding() {
  useSmoothScroll();
  /* Same mechanism the moss landing uses: the tokens below are re-pointed for
     this subtree only, and the document's own ground is handed over for as long
     as the page is mounted. /app keeps both its themes. */
  useEffect(() => {
    document.documentElement.dataset.landing = "paper";
    return () => {
      delete document.documentElement.dataset.landing;
    };
  }, []);

  return (
    <div className="landing-paper min-h-screen">
      <NextNav />
      <NextHero />
      <RunEditorial />
      <ProofEditorial />
      <StackEditorial />
      <NextFooter />
    </div>
  );
}
