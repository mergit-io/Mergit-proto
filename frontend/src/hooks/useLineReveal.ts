import { useEffect, type RefObject } from "react";
import { loadMotion, prefersReducedMotion } from "../lib/motion";

/**
 * Reveals a heading a line at a time, each line rising out from behind its own
 * edge.
 *
 * SplitText does the measuring, which is the part worth borrowing: the lines are
 * wherever the browser actually broke them at this width, so the mask edges land
 * on real baselines instead of on `<br>`s we guessed. `mask: "lines"` wraps each
 * line in a clipping element, which is what makes it read as type emerging
 * rather than type fading.
 *
 * The element is left completely alone when motion is off — no split, no wrapper,
 * no inline styles — so the still page is the plain heading it always was.
 */
export function useLineReveal(ref: RefObject<HTMLElement | null>, delay = 0) {
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    /* Hidden synchronously, before anything is awaited. Two awaits stand between
       here and the first frame of the reveal — the motion chunk and the web font
       — and on a slow connection that is long enough for the heading to be read,
       and then to hide itself and animate back in. `visibility` rather than
       opacity so the text keeps its space and nothing reflows.

       Whatever happens next, this has to come back: the `finally` below is the
       only thing standing between a failed import and a headline that is never
       visible again. */
    el.style.visibility = "hidden";
    const reveal = () => {
      el.style.visibility = "";
    };

    (async () => {
      let motion;
      try {
        motion = await loadMotion();
      } finally {
        if (!motion || cancelled) reveal();
      }
      if (!motion || cancelled || !ref.current) return;
      const { gsap, SplitText } = motion;

      // Fonts first. Split before Lexend lands and the lines are measured
      // against the fallback, so a mask edge can end up mid-letter.
      await document.fonts?.ready;
      if (cancelled || !ref.current) {
        reveal();
        return;
      }

      const split = new SplitText(ref.current, { type: "lines", mask: "lines" });
      reveal();
      const tween = gsap.from(split.lines, {
        yPercent: 118,
        duration: 1.1,
        ease: "expo.out",
        stagger: 0.09,
        delay,
      });

      cleanup = () => {
        tween.kill();
        split.revert();
        reveal();
      };
    })();

    return () => {
      cancelled = true;
      cleanup?.();
      reveal();
    };
  }, [ref, delay]);
}
