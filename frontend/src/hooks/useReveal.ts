import { useEffect } from "react";

/**
 * Reveals `[data-reveal]` elements as they scroll into view.
 *
 * The hidden state lives behind an `html.reveal-ready` class that this hook adds,
 * so a page whose JS never runs shows its content rather than a blank column.
 * Anything already on screen at mount is revealed immediately — a first section
 * that fades in after the user is already looking at it reads as a stutter.
 */
export function useReveal() {
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (!nodes.length) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    const root = document.documentElement;
    root.classList.add("reveal-ready");

    const show = (el: HTMLElement) => el.classList.add("is-in");

    // `reveal-ready` is the class that makes [data-reveal] hidden, and it sits on
    // <html>. It has to come off on unmount: left behind, it keeps hiding reveal nodes
    // on pages this observer knows nothing about, and nothing would ever reveal them.
    const frames: number[] = [];
    const cleanup = () => {
      frames.forEach(cancelAnimationFrame);
      root.classList.remove("reveal-ready");
    };

    // Above-the-fold content is already being looked at; reveal it on the next
    // frame so the class lands after the hidden state has been painted.
    const viewport = window.innerHeight;
    const below: HTMLElement[] = [];
    nodes.forEach((el) => {
      if (el.getBoundingClientRect().top < viewport * 0.9) {
        frames.push(requestAnimationFrame(() => show(el)));
      } else {
        below.push(el);
      }
    });

    if (!below.length) return cleanup;

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          show(e.target as HTMLElement);
          io.unobserve(e.target);
        });
      },
      // No negative bottom margin: it shrinks the root's bottom edge, so a reveal node
      // in the last stretch of the document can never intersect once the page is
      // scrolled to the end — it would simply never appear.
      { rootMargin: "0px", threshold: 0.08 }
    );

    below.forEach((el) => io.observe(el));
    return () => {
      io.disconnect();
      cleanup();
    };
  }, []);
}
