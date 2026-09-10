#!/usr/bin/env node
/**
 * Regenerates public/landing/sylva/scene.html from upstream ThreeUI.
 *
 * The landing hero's background is the Three.js half of ThreeUI's "Sylva —
 * Living Green" hero (MIT, github.com/MengTo/threeui). Upstream ships it as one
 * 198KB standalone page: canvas + Sylva's own marketing copy + 33KB of CSS +
 * 153KB of scene JS and GLSL, all inline. We want the world — moss, ferns,
 * pollen, the butterfly — and none of the copy, because the copy is Mergit's
 * job and it lives in React where the router and the design tokens are.
 *
 * So this keeps the head (fonts, the `--u` design unit, scene CSS) and every
 * script from the Three.js runtime onward, and replaces the authored body with
 * a bare canvas + stage. That is the same seam upstream's own React adapter
 * cuts at (src/shaders/sylva-living-world/SylvaLivingWorldScene.tsx); the
 * difference is that it inlines the result with Vite `?raw` imports, which puts
 * ~800KB of strings into the JS bundle. We write a file instead and load it in
 * an iframe, so Three.js stays a separately cached 608KB asset that the console
 * at /app never pays for.
 *
 * The output is committed, so a normal build needs no network. Re-run only to
 * move to a newer upstream:
 *
 *   node frontend/scripts/extract-sylva-scene.mjs
 *   node frontend/scripts/extract-sylva-scene.mjs --sha <upstream-commit>
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/* Pinned, not HEAD: the slice below depends on two exact strings in the source,
   and an unreviewed upstream edit should fail loudly here rather than silently
   reshape the landing page. */
const DEFAULT_SHA = "68802d5428071ada5c20db8094b1649e6bb770ed";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../public/landing/sylva/scene.html");

/* The seam. `presentation` is where Sylva's authored markup starts; `runtime` is
   where its scripts start. Everything between the two is what we drop. */
const PRESENTATION_MARK = '<main class="hero" id="hero">';
const RUNTIME_MARK = '<script src="inner-green-assets/three.min.js"></script>';

/* `.stage` is kept because the scene's parallax and reveal code queries it. It
   is emptied of Sylva's cards and headline — React draws ours on top instead. */
const SCENE_MARKUP = `<main class="hero" id="hero">
  <canvas id="scene" role="img" aria-label="A mossy forest floor with ferns, pale flowers and drifting pollen"></canvas>
  <div class="stage" id="stage" aria-hidden="true"></div>
</main>`;

/* The scene's world tilts with the cursor, and it learns about the cursor from a
   `pointermove` listener on its own `window`. That listener is unreachable once
   the frame is `pointer-events: none` — which it has to be, because wheel events
   over a cross-origin iframe never reach the parent's JS, and a smooth-scroll
   library that listens on the parent would leave the page frozen wherever the
   hero is under the mouse.

   So the parent keeps every pointer event and forwards the coordinates in, and
   this bridge turns them back into the event the scene is already listening for.
   Coordinates only, from `window.parent` only — nothing here reads a payload
   field it did not ask for. */
const POINTER_BRIDGE = `<script data-mergit-pointer-bridge>
(function () {
  var KIND = "mergit:pointer";
  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var data = event.data;
    if (!data || data.kind !== KIND) return;
    if (data.leave) {
      window.dispatchEvent(new PointerEvent("pointerleave", { pointerType: "mouse", bubbles: true }));
      return;
    }
    var x = Number(data.x), y = Number(data.y);
    if (!isFinite(x) || !isFinite(y)) return;
    window.dispatchEvent(new PointerEvent("pointermove", {
      pointerType: "mouse", clientX: x, clientY: y, bubbles: true
    }));
  });
})();
<\/script>`;

/* The source page is a full-height document; inside our iframe it is a layer.
   `overflow:hidden` matters: without it the 100svh hero plus the iframe's own
   scrollbar gutter makes the canvas jitter on every pointer move. */
const SCENE_STYLE = `<style data-mergit-sylva-scene>
  html, body { width: 100% !important; height: 100% !important; min-height: 0 !important; margin: 0 !important; overflow: hidden !important; }
  body { position: relative !important; background: #4a4d44 !important; }
  .hero { height: 100% !important; min-height: 0 !important; }
  /* Nothing in here takes pointer events: the parent owns them and forwards the
     coordinates through the bridge above. See POINTER_BRIDGE for why. */
  #scene, #stage { pointer-events: none !important; }
</style>`;

async function main() {
  const shaFlag = process.argv.indexOf("--sha");
  const sha = shaFlag > -1 ? process.argv[shaFlag + 1] : DEFAULT_SHA;
  if (!sha) throw new Error("--sha needs a value");

  const url = `https://raw.githubusercontent.com/MengTo/threeui/${sha}/public/landing-pages/inner-green-3d.html`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`upstream fetch failed: ${response.status} ${url}`);
  const source = await response.text();

  const presentation = source.indexOf(PRESENTATION_MARK);
  const runtime = source.indexOf(RUNTIME_MARK);
  if (presentation < 0 || runtime < 0 || runtime <= presentation) {
    throw new Error(
      "could not find the scene seam in upstream source — the page was restructured, so re-read it before trusting this script"
    );
  }

  let out = `${source.slice(0, presentation)}${SCENE_MARKUP}\n\n${source.slice(runtime)}`;

  // Assets sit beside the output file rather than in upstream's subfolder.
  out = out.replaceAll("inner-green-assets/", "./");

  /* The scene is framed with `sandbox` and no `allow-same-origin`, so its origin
     is opaque — and a font fetch is always a CORS request. Upstream's @font-face
     therefore fails there with a console error on every load. It is also pointless
     now: the markup this script strips was the only text in the document. The
     landing loads Lexend itself, same-origin, from index.css. */
  const fontFace = /@font-face\s*\{[^}]*lexend-latin\.woff2[^}]*\}/i;
  if (!fontFace.test(out)) {
    throw new Error("expected upstream's Lexend @font-face — it moved, so re-check what the scene now fetches");
  }
  out = out.replace(fontFace, "/* @font-face removed: see extract-sylva-scene.mjs */");

  // Ours, not upstream's: the head's own <style> block has to keep the layer
  // overrides last so they win on specificity ties.
  out = out.replace("</head>", `${SCENE_STYLE}\n</head>`);

  // Last thing before the document closes, so the scene's own listeners exist.
  out = out.replace("</body>", `${POINTER_BRIDGE}\n</body>`);

  /* Reduced motion. The source already computes REDUCED from its own
     matchMedia (media queries resolve inside an iframe, so this works), and
     already skips parallax and the portal reveals when it is set — but the rAF
     loop itself keeps running, which is the expensive part. One frame is still
     drawn, so the world is composed rather than blank. */
  const LOOP = "(function loop() { requestAnimationFrame(loop); tick(); })();";
  if (!out.includes(LOOP)) {
    throw new Error("could not find the render loop to gate behind prefers-reduced-motion");
  }
  out = out.replace(LOOP, "(function loop() { if (!REDUCED) requestAnimationFrame(loop); tick(); })();");

  const banner = `<!--
  Generated by frontend/scripts/extract-sylva-scene.mjs — do not edit by hand.

  Scene extracted from ThreeUI "Sylva — Living Green"
  https://github.com/MengTo/threeui @ ${sha}
  MIT License, Copyright (c) Meng To / Design+Code. Full text in ./LICENSE-threeui.txt.
  Bundled Three.js (./three.min.js) is MIT, Copyright 2010-2023 Three.js Authors.
  Lexend (./lexend-latin.woff2) is SIL OFL 1.1.
-->\n`;

  await mkdir(dirname(OUT), { recursive: true });
  await writeFile(OUT, banner + out, "utf8");
  process.stdout.write(`wrote ${OUT} (${((banner.length + out.length) / 1024).toFixed(0)}KB) from ${sha}\n`);
}

await main();
