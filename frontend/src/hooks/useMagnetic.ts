import { useEffect, type RefObject } from "react";
import { hasFinePointer, loadMotion } from "../lib/motion";

/**
 * Makes a control lean towards the cursor while the cursor is near it, and
 * settle back when it leaves.
 *
 * The pull is on a wrapper-free transform of the element itself, tweened with
 * `quickTo` — a re-used tween rather than a new one per pointer event, which is
 * the difference between this costing nothing and it costing a frame.
 *
 * `radius` is how far away the cursor starts to matter, `pull` how far the
 * control is willing to travel. Both in px.
 */
export function useMagnetic(
  ref: RefObject<HTMLElement | null>,
  { radius = 110, pull = 14 } = {}
) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !hasFinePointer()) return;
    let cancelled = false;
    let cleanup: (() => void) | null = null;

    (async () => {
      const motion = await loadMotion();
      if (!motion || cancelled || !ref.current) return;
      const { gsap } = motion;
      const target = ref.current;
      const toX = gsap.quickTo(target, "x", { duration: 0.45, ease: "power3.out" });
      const toY = gsap.quickTo(target, "y", { duration: 0.45, ease: "power3.out" });

      const onMove = (event: PointerEvent) => {
        if (event.pointerType === "touch") return;
        const rect = target.getBoundingClientRect();
        const dx = event.clientX - (rect.left + rect.width / 2);
        const dy = event.clientY - (rect.top + rect.height / 2);
        // Distance from the element's edge, not its centre, so a wide button and
        // a small round one both start pulling at the same apparent gap.
        const reach = Math.hypot(dx / (rect.width / 2 + radius), dy / (rect.height / 2 + radius));
        if (reach > 1) {
          toX(0);
          toY(0);
          return;
        }
        const strength = 1 - reach;
        toX(gsap.utils.clamp(-pull, pull, dx * 0.35 * strength));
        toY(gsap.utils.clamp(-pull, pull, dy * 0.35 * strength));
      };

      const onLeave = () => {
        toX(0);
        toY(0);
      };

      window.addEventListener("pointermove", onMove, { passive: true });
      document.addEventListener("pointerleave", onLeave);
      cleanup = () => {
        window.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerleave", onLeave);
        toX(0);
        toY(0);
      };
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [ref, radius, pull]);
}
