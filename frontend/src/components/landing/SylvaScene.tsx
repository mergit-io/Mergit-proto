import { useEffect, useRef, useState } from "react";

/* The landing hero's ground: ThreeUI's "Sylva — Living Green" world (MIT), cut
   down to its Three.js half by frontend/scripts/extract-sylva-scene.mjs and
   served as a standalone document.

   An iframe rather than a React component because the scene is 150KB of authored
   JS and GLSL that owns its own canvas, resize handling and pointer loop. Framing
   it keeps all of that — and Three.js itself — out of our bundle and out of the
   console's critical path, and it means an exception inside the scene cannot take
   the page down with it. The cost is that nothing inside can talk to the router,
   which is exactly why the hero's copy and links are drawn in React on top rather
   than left in the source page.

   `sandbox="allow-scripts"` and no `allow-same-origin`: the scene needs to run,
   and needs nothing else. Same-origin would hand vendored third-party code a
   handle on our document, cookies and localStorage for no gain. */
const SCENE_URL = "/landing/sylva/scene.html";
const POINTER_KIND = "mergit:pointer";

export function SylvaScene({ className = "" }: { className?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  /* Two independent reasons to stop rendering, both of them the same fix: unmount
     the frame. A paused rAF loop still holds the GL context and its buffers; an
     unmounted iframe gives them back. Scrolled past the hero, or tabbed away, is
     the common case on a landing page — that is a full GPU's worth of work being
     done for nobody. */
  const [onScreen, setOnScreen] = useState(true);
  const [tabVisible, setTabVisible] = useState(() =>
    typeof document === "undefined" ? true : !document.hidden
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) =>
      setOnScreen(entry?.isIntersecting ?? true)
    );
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const update = () => setTabVisible(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  const mounted = onScreen && tabVisible;

  useEffect(() => {
    if (!mounted) setReady(false);
  }, [mounted]);

  /* The frame takes no pointer events — the parent owns them, because wheel
     events over a cross-origin iframe never reach the parent's JS, and the page's
     smooth scrolling listens there. So the cursor is forwarded in instead, which
     the scene's bridge turns back into the `pointermove` it already listens for.

     One post per frame, and only while the cursor is actually over the hero. In
     the frame's coordinates, not the viewport's: the two agree only while the
     hero is at the top of the page. */
  useEffect(() => {
    if (!ready) return;
    const host = hostRef.current;
    const frame = frameRef.current;
    if (!host || !frame) return;

    let queued: { x: number; y: number } | null = null;
    let raf = 0;
    let inside = false;

    const post = (message: Record<string, unknown>) =>
      frame.contentWindow?.postMessage({ kind: POINTER_KIND, ...message }, "*");

    const flush = () => {
      raf = 0;
      if (queued) post(queued);
      queued = null;
    };

    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const rect = host.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const over = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height;
      if (!over) {
        if (inside) {
          inside = false;
          queued = null;
          post({ leave: true });
        }
        return;
      }
      inside = true;
      queued = { x, y };
      if (!raf) raf = requestAnimationFrame(flush);
    };

    const onLeave = () => {
      if (!inside) return;
      inside = false;
      queued = null;
      post({ leave: true });
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [ready]);

  return (
    <div
      ref={hostRef}
      className={`sylva-scene ${className}`}
      data-state={ready ? "ready" : "loading"}
      /* The moss ground is painted here too, so the hero is composed before the
         scene has loaded rather than flashing the page background through it. */
      style={{ background: "#4a4d44" }}
    >
      {mounted && (
        <iframe
          ref={frameRef}
          title="Sylva living world"
          src={SCENE_URL}
          sandbox="allow-scripts"
          loading="eager"
          tabIndex={-1}
          aria-hidden="true"
          onLoad={() => setReady(true)}
          style={{
            position: "absolute",
            inset: 0,
            display: "block",
            width: "100%",
            height: "100%",
            border: 0,
            background: "#4a4d44",
            pointerEvents: "none",
          }}
        />
      )}
    </div>
  );
}
