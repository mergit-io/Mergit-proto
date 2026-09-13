import { useEffect } from "react";
import { loadMotion } from "../lib/motion";

/**
 * Inertial scrolling for the landing page, and the one wire that keeps it in
 * step with ScrollTrigger.
 *
 * Lenis animates the real scroll position rather than transforming a wrapper, so
 * `position: sticky`, IntersectionObserver and ScrollTrigger's own pinning all
 * keep working — but ScrollTrigger has to be told to recompute on Lenis' frames
 * instead of on native scroll events, and Lenis has to be driven from GSAP's
 * ticker so the two never disagree about what time it is.
 *
 * Mounted by the landing only. It is destroyed on the way to /app, because the
 * console is a dense tool where a scroll that keeps moving after you stop is a
 * liability rather than a flourish.
 */
export function useSmoothScroll() {
  useEffect(() => {
    let cancelled = false;
    let teardown: (() => void) | null = null;

    (async () => {
      const motion = await loadMotion();
      if (!motion || cancelled) return;
      const { default: Lenis } = await import("lenis");
      if (cancelled) return;

      const { gsap, ScrollTrigger } = motion;
      /* Nothing here kills ScrollTriggers on the way out, deliberately: every
         trigger on the page belongs to the component that created it and is
         reverted by that component's own cleanup. A sweep from here would also
         take out triggers this hook knows nothing about. */
      const lenis = new Lenis({
        duration: 1.05,
        // Native on touch: the OS' own scrolling is better than anything we can
        // fake, and fighting it is how a page starts to feel slippery.
        smoothWheel: true,
        syncTouch: false,
      });

      const onScroll = () => ScrollTrigger.update();
      lenis.on("scroll", onScroll);

      // GSAP's ticker is in seconds, Lenis wants milliseconds.
      const raf = (time: number) => lenis.raf(time * 1000);
      gsap.ticker.add(raf);
      gsap.ticker.lagSmoothing(0);

      /* In-page anchors have to go through Lenis. Left alone they set
         scrollTop directly, which Lenis then reads as the user having thrown the
         page somewhere, and the jump lands with a lurch. */
      const onClick = (event: MouseEvent) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey) return;
        const anchor = (event.target as Element | null)?.closest?.('a[href^="#"]');
        const href = anchor?.getAttribute("href");
        if (!href || href === "#") return;
        const target = document.querySelector(href);
        if (!target) return;
        event.preventDefault();
        lenis.scrollTo(target as HTMLElement, { offset: -72 });
      };
      document.addEventListener("click", onClick);

      teardown = () => {
        document.removeEventListener("click", onClick);
        lenis.off("scroll", onScroll);
        gsap.ticker.remove(raf);
        gsap.ticker.lagSmoothing(500, 33);
        lenis.destroy();
      };
    })();

    return () => {
      cancelled = true;
      teardown?.();
    };
  }, []);
}
