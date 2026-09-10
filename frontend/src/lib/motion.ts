import type { gsap as GsapType } from "gsap";

/* One place that knows how to get GSAP, and one place that decides whether we
   are allowed to animate at all.

   Loaded with `import()` rather than a top-level import so the whole motion
   stack — GSAP, ScrollTrigger, SplitText, Lenis — becomes its own chunk. The
   console at /app has no animation of this kind and should not pay for it, and
   the landing can render its first frame before the chunk arrives.

   GSAP is free for commercial use under its Standard "no charge" license
   (gsap.com/standard-license, Webflow-funded): all plugins, no attribution
   required, no restriction that touches a product like this. Lenis is MIT. */
export type Motion = {
  gsap: typeof GsapType;
  ScrollTrigger: typeof import("gsap/ScrollTrigger").ScrollTrigger;
  SplitText: typeof import("gsap/SplitText").SplitText;
};

export function prefersReducedMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Pointer-driven flourishes are wrong on a touch screen — there is no hover to
    respond to, and the effect just eats a tap. */
export function hasFinePointer() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches
  );
}

let pending: Promise<Motion | null> | null = null;

/**
 * Resolves the motion stack, or `null` when the visitor asked for less motion.
 *
 * `null` rather than a throw or a flag: every caller has to have a still,
 * readable version of itself anyway, so the honest shape is "there is no
 * animation available" and the component renders its static self.
 */
export function loadMotion(): Promise<Motion | null> {
  if (prefersReducedMotion()) return Promise.resolve(null);
  pending ??= (async () => {
    try {
      const [{ gsap }, { ScrollTrigger }, { SplitText }] = await Promise.all([
        import("gsap"),
        import("gsap/ScrollTrigger"),
        import("gsap/SplitText"),
      ]);
      gsap.registerPlugin(ScrollTrigger, SplitText);
      return { gsap, ScrollTrigger, SplitText };
    } catch {
      /* A chunk that fails to arrive — a dropped connection, a stale cache
         pointing at a deploy that no longer exists — is the same situation as
         a visitor who asked for no motion, and callers already handle that.
         Rejecting instead would surface as an unhandled rejection in every hook,
         none of which can do anything useful with it.

         The cache is cleared on the way out: without this, one failed load would
         be remembered for the life of the page and every later caller would get
         the same rejection back, so a single dropped request would permanently
         disable motion instead of costing one retry. */
      pending = null;
      return null;
    }
  })();
  return pending;
}
