import { useEffect, type RefObject } from "react";
import { loadMotion } from "../lib/motion";

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
    if (!el) return;
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      const motion = await loadMotion();
      if (!motion || cancelled || !ref.current) return;
      const { gsap, SplitText } = motion;

      // Fonts first. Split before Lexend lands and the lines are measured
      // against the fallback, so a mask edge can end up mid-letter.
      await document.fonts?.ready;
      if (cancelled || !ref.current) return;

      const split = new SplitText(ref.current, { type: "lines", mask: "lines" });
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
      };
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [ref, delay]);
}
