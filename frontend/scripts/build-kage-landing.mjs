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
  out = out.replace("</body>", `${NAV_BRIDGE}\n</body>`);
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
