import { useEffect, useRef } from "react";
// Types only — erased at build, so this does not pull three into the chunk.
import type { Material } from "three";

/* The page's one object: Mergit's proof block, built rather than drawn.
   ------------------------------------------------------------------------------
   A hexagonal shell in two halves with a lit core inside it — the same mark that
   sits in the console's proof field, given depth, glass and light. It is the
   product's whole claim as an object: a finished task, sealed, with something
   solid inside.

   Plain three.js, no react-three-fiber. R3F's peer range stops at React 19.3 and
   this repo is on it, and a single object needs no reconciler — the whole scene
   is fifty lines of setup and one loop, and owning the loop directly is what lets
   it stop cleanly when nobody is looking at it.

   Nothing here is fetched. The lighting is a PMREM-generated probe from three's
   own RoomEnvironment, so there is no HDR file, no CDN, and no request that can
   fail on a slow connection and leave the object black. */

export type ProofObjectHandle = {
  /** 0 → sealed and idle, 1 → open, core bright, digest facing the reader.
      Stage three drives this from the scroll. */
  setProgress: (t: number) => void;
};

export function ProofObject({
  className = "",
  onHandle,
}: {
  className?: string;
  onHandle?: (handle: ProofObjectHandle | null) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    let stop: (() => void) | null = null;

    (async () => {
      const THREE = await import("three");
      const { RoomEnvironment } = await import("three/examples/jsm/environments/RoomEnvironment.js");
      if (disposed || !hostRef.current) return;

      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      // 1.5 rather than the device's own ratio: this object is smooth surfaces and
      // soft gradients, which is exactly the content that gains least from a third
      // and fourth sample, on a material that costs the most to draw.
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.15;
      host.appendChild(renderer.domElement);
      renderer.domElement.style.display = "block";
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";

      const scene = new THREE.Scene();
      const pmrem = new THREE.PMREMGenerator(renderer);
      const environment = pmrem.fromScene(new RoomEnvironment(), 0.04);
      scene.environment = environment.texture;

      const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 40);
      camera.position.set(0, 0.5, 6.7);
      camera.lookAt(0, 0, 0);

      const key = new THREE.DirectionalLight(0xffffff, 2.1);
      key.position.set(3.2, 4.4, 3.6);
      const rim = new THREE.DirectionalLight(0xc8b8ff, 1.4);
      rim.position.set(-3.4, 1.2, -2.6);
      scene.add(key, rim, new THREE.AmbientLight(0xffffff, 0.35));

      /* The shell. A hexagon extruded with a bevel rather than a six-sided
         cylinder: the bevel is what catches the key light along every edge, and
         it is the difference between a solid that reads as glass and one that
         reads as a flat-shaded prism. */
      const hexagon = new THREE.Shape();
      const radius = 1.18;
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius;
        i === 0 ? hexagon.moveTo(x, y) : hexagon.lineTo(x, y);
      }
      hexagon.closePath();

      const halfGeometry = new THREE.ExtrudeGeometry(hexagon, {
        depth: 0.46,
        bevelEnabled: true,
        bevelThickness: 0.07,
        bevelSize: 0.07,
        bevelSegments: 3,
        curveSegments: 1,
      });
      halfGeometry.center();

      const glass = new THREE.MeshPhysicalMaterial({
        color: 0xffffff,
        transmission: 1,
        thickness: 0.85,
        roughness: 0.09,
        ior: 1.45,
        clearcoat: 1,
        clearcoatRoughness: 0.12,
        transparent: true,
      });

      const top = new THREE.Mesh(halfGeometry, glass);
      const bottom = new THREE.Mesh(halfGeometry, glass);
      top.position.z = 0.3;
      bottom.position.z = -0.3;

      /* The core: the solid square from the mark, the settled task itself. */
      const core = new THREE.Mesh(
        // 0.56 against a 1.18 shell: the mark's square is a small solid at the
        // centre of a much larger hex, and a core sized to fill the shell reads
        // as a block in a box rather than as something sealed inside one.
        new THREE.BoxGeometry(0.56, 0.56, 0.56),
        new THREE.MeshStandardMaterial({
          color: 0x5a34f5,
          emissive: 0x4a26e0,
          emissiveIntensity: 0.28,
          roughness: 0.34,
          metalness: 0.1,
        })
      );

      const group = new THREE.Group();
      group.add(top, bottom, core);
      group.rotation.x = 0.3;
      scene.add(group);

      const resize = () => {
        const { clientWidth: w, clientHeight: h } = host;
        if (!w || !h) return;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(host);

      let progress = 0;
      let frame = 0;
      let running = false;
      const clock = new THREE.Clock();

      const draw = () => {
        const t = clock.getElapsedTime();
        // Sealed at rest, opening as progress climbs; the core brightens as it does.
        const gap = 0.3 + progress * 0.62;
        top.position.z = gap;
        bottom.position.z = -gap;
        core.material.emissiveIntensity = 0.28 + progress * 1.5;
        core.rotation.y = t * 0.35 + progress * 1.1;
        group.rotation.y = reduced ? 0.5 : t * 0.22 + progress * 0.8;
        group.position.y = reduced ? 0 : Math.sin(t * 0.7) * 0.045;
        renderer.render(scene, camera);
      };

      const loop = () => {
        frame = requestAnimationFrame(loop);
        draw();
      };

      const start = () => {
        if (running || reduced) return;
        running = true;
        clock.start();
        loop();
      };
      const pause = () => {
        running = false;
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
      };

      /* Off screen or in a hidden tab, the loop stops: a rendering GL context that
         nobody is looking at is the most expensive thing on a landing page. One
         frame is always drawn first, so the object is composed rather than blank
         when it scrolls back in — and it is all a reduced-motion visitor gets. */
      const io = new IntersectionObserver(([entry]) => (entry?.isIntersecting ? start() : pause()));
      io.observe(host);
      const onVisibility = () => (document.hidden ? pause() : start());
      document.addEventListener("visibilitychange", onVisibility);
      draw();

      onHandle?.({
        setProgress: (value: number) => {
          progress = Math.min(1, Math.max(0, value));
          if (!running) draw();
        },
      });

      stop = () => {
        pause();
        io.disconnect();
        observer.disconnect();
        document.removeEventListener("visibilitychange", onVisibility);
        onHandle?.(null);
        // Give the GPU everything back: an orphaned context survives the component.
        halfGeometry.dispose();
        core.geometry.dispose();
        (core.material as Material).dispose();
        glass.dispose();
        environment.texture.dispose();
        pmrem.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    })();

    return () => {
      disposed = true;
      stop?.();
    };
  }, [onHandle]);

  return <div ref={hostRef} className={className} aria-hidden="true" />;
}
