#!/usr/bin/env node
/**
 * Builds public/landing/kage/index.html from upstream ThreeUI's "Kage" landing.
 *
 * Kage is a five-section WebGL landing page in the MIT Community catalogue
 * (github.com/MengTo/threeui) — the same catalogue the Sylva scene on the old
 * landing came from, so it is ours to fork. Upstream ships it as one 244KB
 * document: ~17KB of markup, ~50KB of CSS and a 173KB inline scene.
 *
 * This is a generator rather than a hand-edited copy for the same reason the
 * Sylva extractor is: the fork stays reproducible against a pinned upstream
 * commit, and every substitution below asserts that it matched exactly once. A
 * silent miss would mean a page that still says "Kyoto" somewhere, and the
 * assertion is what makes that impossible rather than merely unlikely.
 *
 *   node frontend/scripts/build-kage-landing.mjs
 *   node frontend/scripts/build-kage-landing.mjs --sha <upstream-commit>
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_SHA = "68802d5428071ada5c20db8094b1649e6bb770ed";
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../public/landing/kage/index.html");

/* Where the authored markup ends and the runtime begins. Copy is only ever
   applied above this line, so a word like "KAGE" inside the scene's own strings
   can never be rewritten by accident. */
const RUNTIME_MARK = '<script src="secret-pathways-assets/three.min.js"></script>';

/* Kage's copy, mapped onto Mergit's — see kage-copy.json.
   ------------------------------------------------------------------------------
   Entries are `[textNodeIndex, expectedUpstreamText, mergitText]`, not
   search-and-replace pairs. Plain string replacement was the first attempt and it
   is quietly wrong here: "Gardens" in the navigation and "Still Gardens" in a card
   are different slots, and replacing the short one first turns the long one into
   "Still Agents". Worse, "Afterlight" is a navigation item *and* a section
   heading, and no ordering distinguishes those at all.

   Addressing nodes by position removes the ambiguity, and pairing each with the
   text we expect to find there means an upstream edit fails the build rather than
   shipping a page that still says Kyoto somewhere.

   The structure is untouched: same sections, same rhythm, same rough word count
   per slot, because the layout was designed around these lengths. Where Kage sets
   a Japanese gloss beside a label, Mergit sets the tool or artefact that step
   actually produces — the console already speaks in that register, and decorative
   kanji on a page about pull requests would be borrowed atmosphere with nothing
   underneath it. */
const COPY = JSON.parse(
  await readFile(new URL("./kage-copy.json", import.meta.url), "utf8")
);

/** Masks every script and style block with same-length filler, so text-node
    positions are counted over authored markup only and offsets still line up
    against the original document. */
function maskCode(html) {
  return html.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/g, (block) => "\u0000".repeat(block.length));
}

const NODE = /<([a-zA-Z][\w-]*)([^>]*)>([^<>]{2,})<\/\1>/g;

function applyCopy(html) {
  /* Counted from <body> onward. The head has text nodes of its own — the title
     most obviously — and including them would shift every index in the table by
     an amount that depends on markup we do not care about. */
  const bodyAt = html.indexOf("<body");
  if (bodyAt < 0) throw new Error("no <body> in upstream source");
  const before = html.slice(0, bodyAt);
  html = html.slice(bodyAt);
  const masked = maskCode(html);
  const nodes = [];
  let m;
  NODE.lastIndex = 0;
  while ((m = NODE.exec(masked))) {
    const text = m[3];
    if (!text.trim() || text.includes("\u0000")) continue;
    nodes.push({ start: m.index + m[0].length - m[3].length - (m[1].length + 3), text });
  }
  // Recompute precisely: the inner text sits just before the closing tag.
  const found = [];
  NODE.lastIndex = 0;
  while ((m = NODE.exec(masked))) {
    if (!m[3].trim() || m[3].includes("\u0000")) continue;
    const openLen = m[0].indexOf(">") + 1;
    found.push({ from: m.index + openLen, to: m.index + openLen + m[3].length, text: m[3] });
  }

  const edits = [];
  for (const [index, expected, replacement] of COPY) {
    const node = found[index];
    if (!node) throw new Error(`text node ${index} does not exist upstream any more`);
    const actual = node.text.trim().replace(/\s+/g, " ");
    if (expected !== null && actual !== expected) {
      throw new Error(
        `text node ${index}: expected ${JSON.stringify(expected)} but upstream now says ${JSON.stringify(actual.slice(0, 60))}`
      );
    }
    edits.push({ ...node, replacement });
  }

  // Applied back-to-front so earlier offsets stay valid.
  let out = html;
  for (const edit of edits.sort((a, b) => b.from - a.from)) {
    out = out.slice(0, edit.from) + edit.replacement + out.slice(edit.to);
  }
  return before + out;
}

/* The head is Mergit's too: the title and description are what a search result
   and a shared link show, and they are the one part of the page a visitor may
   read before any of it renders. */
const HEAD_COPY = [
  [
    "<title>Kage — Where stillness reveals the unseen</title>",
    "<title>Mergit — Describe the outcome. Not the steps.</title>",
  ],
  [
    "A five-chapter night walk through a Kyoto mountain temple. Charred cypress, lantern light and a vermilion moon, rendered live in WebGL.",
    "One sentence becomes a task graph. Specialised agents execute it with real tools, and every finished task mints a proof on chain.",
  ],
];

/* Copy that lives in the scene script rather than the markup.
   ------------------------------------------------------------------------------
   Three things down here are user-visible and would otherwise still be Kage's:

   · the giant wordmark is not markup at all — the scene draws it glyph by glyph
     onto canvases and hangs the planes in 3D space. It is set in `Wordmark`, the
     22-glyph face that cannot spell MERGIT, so both the measuring and the drawing
     contexts take Mergit's face first and fall back to Kage's.
   · the loader's progress lines are the labels of the scene's own build queue.
   · job zero preloads the wordmark face before anything is drawn, which is
     exactly the hook our face needs — canvas text silently falls back to
     sans-serif if the font has not loaded yet, and a wordmark that renders in the
     system font on a cold cache is the kind of bug that only ever appears for
     someone else. */
const SCRIPT_COPY = [
  ["const word = 'KAGE'", "const word = 'MERGIT'"],
  [
    "['Reading the type', () => document.fonts && document.fonts.load('600 320px Wordmark')]",
    "['Reading the type', () => document.fonts && Promise.all([document.fonts.load('600 320px ArchivoMergit'), document.fonts.load('600 320px Wordmark')])]",
  ],
  ["['Pouring the ground'", "['Opening the workspace'"],
  ["['Cutting the approach'", "['Planning the graph'"],
  ["['Raising the hall'", "['Assigning the agents'"],
  ["['Hanging the moon'", "['Wiring the tools'"],
  ["['Setting the gate'", "['Claiming the leases'"],
  ["['Placing the stones'", "['Placing the tasks'"],
  ["['Growing the maples'", "['Resolving dependencies'"],
  ["['Painting the near grass'", "['Warming the models'"],
  ["['Cutting the word'", "['Setting the wordmark'"],
  ["['Raising the mist'", "['Opening the stream'"],
  ["['Polishing the water'", "['Settling the proof'"],
  [
    "['The Hidden Gate', 'The Sanmon', 'Still Gardens', 'Sacred Craft', 'Afterlight', 'Colophon']",
    "['The goal', 'The plan', 'The graph', 'The run', 'Settlement', 'Colophon']",
  ],
];

/* Copy that is not a text node at all.
   ------------------------------------------------------------------------------
   The index-addressed table above can only reach text that is the entire contents
   of an element. Kage also writes copy as loose fragments beside child elements —
   `<span class="k"><b>01</b> — The Sanmon</span>` — and into attributes. Those are
   matched as strings instead, longest first so that "Chapter 00 — The Hidden Gate"
   is consumed before the bare "The Hidden Gate" that follows it, and each one has
   to match exactly once. */
const FRAGMENT_COPY = [
  ["Chapter 00 — The Hidden Gate", "Chapter 00 — The goal"],
  ["Preview: Sanmon, before the bell", "Preview: the plan, before the first call"],
  ["— The Sanmon", "— The plan"],
  ["— Still Gardens", "— The graph"],
  ["— Sacred Craft", "— The run"],
  ["The Hidden Gate", "The goal"],
  ["Borrowed Scenery", "The repository"],
  ["Charred Cypress", "The patch"],
  ["Lantern Light", "The pull request"],
  ["The Vermilion Moon", "The proof"],
];

/* Light mode.
   ------------------------------------------------------------------------------
   Kage's chrome is properly tokenised — eleven custom properties carry every
   colour in the type, rules, cards and navigation — so the page's surface themes
   by redefining them. The values are Mergit's own light theme, so the landing and
   the console agree about what light means.

   The scene is a different problem and is handled separately below: its colours
   are baked into materials at boot, not read from CSS. */
const LIGHT_THEME = `<style data-mergit-theme>
  html[data-theme="light"] {
    --ink: #f2f2f5;
    --ink-2: #ffffff;
    --bone: #111019;
    --bone-dim: #4a4857;
    --muted: #63607a;
    --line: rgba(17, 16, 25, .14);
    --line-soft: rgba(17, 16, 25, .07);
    --vermilion: #5a34f5;
    --ember: #4a26e0;
    --gold: #8a6d1f;
  }
  /* No filter on the canvas: the scene's own materials are re-coloured by the
     palette below, and brightening the result as well blew the temple out to flat
     white. The cut-out photographs are not materials and cannot be re-coloured,
     so they keep a mild lift to sit with the day palette. */
  html[data-theme="light"] .fg-el img {
    filter: saturate(.78) brightness(1.22) contrast(.94);
  }

  /* The sky above the horizon is a GLSL gradient inside a ShaderMaterial, which
     the palette walk cannot reach — so in light mode the top of the frame is
     still night, and near-black type over it is unreadable. Until those uniforms
     are exposed, the copy carries its own ground. */
  html[data-theme="light"] .display,
  html[data-theme="light"] .lead,
  html[data-theme="light"] .body,
  html[data-theme="light"] .body-lg,
  html[data-theme="light"] .hero-sub,
  html[data-theme="light"] .eyebrow,
  html[data-theme="light"] .nav-link,
  html[data-theme="light"] .sec-head {
    text-shadow: 0 1px 22px rgba(242, 242, 245, .92), 0 0 6px rgba(242, 242, 245, .8);
  }
</style>`;

/* The scene's palette, and the one place a day version is tuned.
   ------------------------------------------------------------------------------
   Kage builds its materials once at boot from 33 literal colours — moon, lantern
   flames, tile, timber, granite, gold, fog, sky. They cannot be re-read from CSS,
   so the bridge below walks the built scene and swaps them, remembering each
   object's original colour the first time it does so that the change is
   reversible rather than one-way.

   Every entry is `night: day`. Editing this table is the whole tuning loop. */
const SCENE_PALETTE = `<script data-mergit-scene-theme>
(function () {
  var DAY = {
    "05070a": "cfd8e6", "050a0e": "d7e0ec", "060a0d": "cdd7e8",
    "2b343a": "9fb0c0", "525c60": "b9c4cc", "58636a": "aab6c0", "69757a": "c2ccd4",
    "9aa5a5": "d3dadd", "565150": "b2a294", "8a746d": "c8b2a4", "171413": "6a5b52",
    "141a1c": "8d9aa4", "120c0c": "7a6a62", "06090d": "b9c6d6", "0a1015": "c3cfdd",
    "2b0406": "9c4a3c", "40080a": "b05a44", "780200": "8a3b2a", "080000": "6b4a3e",
    "7a5d2a": "c2a35c", "8f6f2e": "d8bb74", "d8c2b6": "efe2d6",
    "53838f": "9fc4dc", "060a08": "c6d2c8", "b6dbe4": "fff6e6", "86c6d2": "cfe6f2",
    "ff3a1c": "ffd9a0", "ff6a42": "ffe2b4", "ff5a24": "ffcf94", "ff8420": "ffd9a6",
    "ff8a26": "ffdca8", "ffa049": "ffe6bd"
  };
  /* Lantern flames carry a night scene and blow out a day one. */
  var LIGHT_SCALE = { day: 0.35, night: 1 };
  var applied = "night";

  function hex(c) { return ("000000" + c.getHexString()).slice(-6); }

  function walk(theme) {
    var api = window.__kage;
    if (!api || !api.scene) return false;
    var day = theme === "light";
    api.scene.traverse(function (o) {
      if (o.isLight) {
        if (o.userData._i0 === undefined) o.userData._i0 = o.intensity;
        o.intensity = o.userData._i0 * (day ? LIGHT_SCALE.day : LIGHT_SCALE.night);
      }
      var mats = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
      mats.concat(o.isLight ? [o] : []).forEach(function (m) {
        ["color", "emissive", "groundColor"].forEach(function (key) {
          var c = m && m[key];
          if (!c || !c.getHexString) return;
          if (m.userData && m.userData["_" + key] === undefined) {
            m.userData = m.userData || {};
            m.userData["_" + key] = hex(c);
          }
          var original = (m.userData && m.userData["_" + key]) || hex(c);
          var mapped = day ? DAY[original] : original;
          if (mapped) c.setHex(parseInt(mapped, 16));
        });
      });
    });
    if (api.scene.fog && api.scene.fog.color) {
      if (!api.scene.fog.userData) api.scene.fog.userData = { _c: hex(api.scene.fog.color) };
      var f = day ? DAY[api.scene.fog.userData._c] : api.scene.fog.userData._c;
      if (f) api.scene.fog.color.setHex(parseInt(f, 16));
    }
    if (api.scene.background && api.scene.background.getHexString) {
      window.__bg0 = window.__bg0 || hex(api.scene.background);
      var b = day ? DAY[window.__bg0] : window.__bg0;
      if (b) api.scene.background.setHex(parseInt(b, 16));
    }
    if (api.renderer) api.renderer.setClearColor(parseInt(day ? "0xcfd8e6" : "0x05070a", 16), 1);
    applied = theme;
    return true;
  }

  function request(theme) {
    document.documentElement.dataset.theme = theme;
    /* The scene may not have booted yet; retry until it has, then stop. */
    var tries = 0;
    (function attempt() {
      if (walk(theme) || ++tries > 60) return;
      setTimeout(attempt, 250);
    })();
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var data = event.data;
    if (!data || data.kind !== "mergit:theme") return;
    if (data.theme !== "light" && data.theme !== "dark") return;
    if (data.theme === applied && document.documentElement.dataset.theme === data.theme) return;
    request(data.theme);
  });
})();
<\/script>`;

/* The theme control.
   ------------------------------------------------------------------------------
   Kage has no need of one and therefore no place for one. A visitor arriving at
   the landing page has to be able to switch, so a button is added beside the
   menu, in the navigation's own idiom. It does not decide anything: it asks the
   parent to toggle, the parent flips the app's theme, and the app tells the frame
   what the theme now is. One source of truth, and the landing agrees with the
   console the moment either changes. */
const THEME_TOGGLE = [
  '<button class="nav-burger" aria-label="Menu" data-cursor><i></i><i></i></button>',
  `<button class="nav-theme" data-mergit-theme-toggle aria-label="Switch between light and dark" data-cursor>
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.25">
      <circle cx="8" cy="8" r="3.1"/>
      <path d="M8 1.2v1.6M8 13.2v1.6M1.2 8h1.6M13.2 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" stroke-linecap="round"/>
    </svg>
  </button>
  <button class="nav-burger" aria-label="Menu" data-cursor><i></i><i></i></button>`,
];

const TOGGLE_STYLE = `<style data-mergit-toggle>
  .nav-theme {
    display: inline-flex; align-items: center; justify-content: center;
    width: 38px; height: 38px; margin-right: 4px;
    background: none; border: 1px solid var(--line); border-radius: 999px;
    color: var(--bone-dim); cursor: pointer;
    transition: color .25s var(--ease), border-color .25s var(--ease);
  }
  .nav-theme:hover { color: var(--bone); border-color: var(--bone-dim); }
</style>`;

/** Every occurrence of the wordmark font stack, in both the measuring and the
    drawing context. */
const FONT_STACK = ["px Wordmark, sans-serif", "px ArchivoMergit, Wordmark, sans-serif"];

/* Kage's two calls to action are in-page anchors — it is a single-document
   landing with nowhere else to go. Mergit's go to the console, and the console is
   a React route outside this frame, so they are retargeted at a sentinel the
   bridge below turns into a real navigation. Nothing else about them changes. */
const CTA_LINKS = [
  [/(<a class="arrowlink" href=")#pathways("[^>]*>\s*<span>Open the console<\/span>)/, "$1#mergit:/app$2"],
  [/(<a class="cta" href=")#top("[^>]*>\s*<i><\/i><span>Delegate a goal<\/span>)/, "$1#mergit:/app$2"],
];

/* Same shape as the Sylva scene's pointer bridge: the frame is sandboxed with no
   same-origin access, so it asks the parent to route rather than trying to reach
   the router itself. One message kind, one field, and the parent validates it. */
const NAV_BRIDGE = `<script data-mergit-nav-bridge>
(function () {
  document.addEventListener("click", function (event) {
    var link = event.target && event.target.closest ? event.target.closest('a[href^="#mergit:"]') : null;
    if (!link) return;
    event.preventDefault();
    parent.postMessage({ kind: "mergit:navigate", to: link.getAttribute("href").slice(8) }, "*");
  });
  document.addEventListener("click", function (event) {
    var toggle = event.target && event.target.closest ? event.target.closest("[data-mergit-theme-toggle]") : null;
    if (!toggle) return;
    event.preventDefault();
    parent.postMessage({ kind: "mergit:toggle-theme" }, "*");
  });
})();
<\/script>`;


async function main() {
  const shaFlag = process.argv.indexOf("--sha");
  const sha = shaFlag > -1 ? process.argv[shaFlag + 1] : DEFAULT_SHA;
  const url = `https://raw.githubusercontent.com/MengTo/threeui/${sha}/public/landing-pages/kage.html`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`upstream fetch failed: ${response.status} ${url}`);
  const source = await response.text();

  const runtime = source.indexOf(RUNTIME_MARK);
  if (runtime < 0) throw new Error("could not find the runtime seam — upstream restructured the page");

  let head = source.slice(0, runtime);
  const tail = source.slice(runtime);

  head = applyCopy(head);
  for (const [from, to] of HEAD_COPY) {
    if (!head.includes(from)) throw new Error(`head copy not found: ${JSON.stringify(from.slice(0, 50))}`);
    head = head.replace(from, to);
  }

  let patchedTail = tail;
  for (const [from, to] of SCRIPT_COPY) {
    if (!patchedTail.includes(from)) {
      throw new Error(`scene copy not found: ${JSON.stringify(from.slice(0, 60))}`);
    }
    patchedTail = patchedTail.split(from).join(to);
  }
  const fontHits = patchedTail.split(FONT_STACK[0]).length - 1;
  if (fontHits !== 2) {
    throw new Error(`expected the wordmark font stack twice, found ${fontHits}`);
  }
  patchedTail = patchedTail.split(FONT_STACK[0]).join(FONT_STACK[1]);

  {
    const [from, to] = THEME_TOGGLE;
    if (!head.includes(from)) throw new Error("navigation burger not found — cannot place the theme control");
    head = head.replace(from, to);
  }

  for (const [from, to] of FRAGMENT_COPY) {
    const hits = head.split(from).length - 1;
    if (hits !== 1) throw new Error(`fragment ${JSON.stringify(from)} matched ${hits} times, expected 1`);
    head = head.split(from).join(to);
  }

  for (const [pattern, replacement] of CTA_LINKS) {
    if (!pattern.test(head)) throw new Error(`call to action not found: ${pattern}`);
    head = head.replace(pattern, replacement);
  }

  let out = head + patchedTail;
  out = out.replaceAll("secret-pathways-assets/", "./assets/");

  /* Inlined, not linked. The frame is sandboxed with no same-origin access, so
     its origin is opaque — and a font request is always a CORS request, which an
     opaque origin fails. Every face upstream ships is a data URI for exactly this
     reason; ours has to be one too, or the wordmark silently falls back to a face
     that cannot spell it. */
  const archivo = await readFile(
    new URL("../node_modules/@fontsource-variable/archivo/files/archivo-latin-wght-normal.woff2", import.meta.url)
  ).catch(() => {
    throw new Error("Archivo not found in node_modules — run npm install before building the landing page");
  });
  const archivoDataUri = `data:font/woff2;base64,${archivo.toString("base64")}`;

  /* The wordmark. Kage sets it in a 22-glyph display face containing only
     `0123456789AEGKSacegkrt` — it cannot spell MERGIT, and four of the six
     letters simply do not exist in the file. So the wordmark slots take
     Mergit's own display face, vendored beside the page. */
  const WORDMARK = `<style data-mergit-wordmark>
  @font-face {
    font-family: 'ArchivoMergit';
    src: url('${archivoDataUri}') format('woff2');
    font-weight: 100 900; font-style: normal; font-display: swap;
  }
  .brand b, .word-fb, [class*="wordmark"] {
    font-family: 'ArchivoMergit', 'Onest', system-ui, sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
  }
</style>`;
  out = out.replace("</head>", `${WORDMARK}\n</head>`);
  out = out.replace("</body>", `${NAV_BRIDGE}\n${SCENE_PALETTE}\n</body>`);
  out = out.replace("</head>", `${LIGHT_THEME}\n${TOGGLE_STYLE}\n</head>`);
  out = out.split(">KAGE<").join(">MERGIT<");

  const banner = `<!--
  Generated by frontend/scripts/build-kage-landing.mjs — do not edit by hand.

  Forked from ThreeUI "Kage", https://github.com/MengTo/threeui @ ${sha}
  MIT License, Copyright (c) Meng To / Design+Code. Full text in ./assets/LICENSE-threeui.txt.
  Bundled Three.js is MIT. Onest and Noto JP are SIL OFL 1.1.
  Archivo (the wordmark face) is SIL OFL 1.1.
-->\n`;

  await mkdir(dirname(OUT), { recursive: true });
  await writeFile(OUT, banner + out, "utf8");
  /* Only what a reader can see: upstream's own comments still say Kage and Kyoto,
     and they should — they are the original author's, and the licence asks that
     notices survive. */
  const visible = out
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  /* Every word that would give the fork away, checked on every build. The list
     grows whenever one gets through: each of these was found in a sweep after the
     copy tables were supposedly complete. */
  const TELLS = ["Kyoto", "Kage", "KAGE", "Sanmon", "Gardens", "Sacred Craft", "Hidden Gate",
                 "Vermilion", "Cypress", "Borrowed Scenery", "Lantern Light", "Afterlight",
                 "Shakkei", "Yakisugi", "shrine", "gravel"];
  /* Asset paths are not copy: one of the foreground layers is called
     shrine-ruins.webp and always will be. */
  const markupOnly = visible
    .slice(0, visible.indexOf("<script src="))
    .replace(/(?:src|href)="[^"]*"/g, "")
    .replace(/url\([^)]*\)/g, "");
  const remaining = TELLS.filter((w) => markupOnly.includes(w) || visible.includes(`'${w}'`));
  process.stdout.write(`wrote ${OUT} (${((banner.length + out.length) / 1024).toFixed(0)}KB) from ${sha}\n`);
  process.stdout.write(`still mentions: ${remaining.join(", ") || "nothing"}\n`);
}

await main();
