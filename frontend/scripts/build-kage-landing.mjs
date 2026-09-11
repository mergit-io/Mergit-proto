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

  /* The wordmark, made legible.
     ----------------------------------------------------------------------------
     Upstream sets the giant type behind the world: it shares the depth buffer
     with the temple and takes the scene's fog, so the hall occludes it and the
     haze desaturates whatever is left. On the night walk that is the effect —
     the word is scenery. Here the word is the product's name, and a name that
     the middle of its own hero page hides four letters of is not a name.

     Three edits, all on the glyph material: it stops testing depth, so nothing
     in the world can cut into it; it opts out of fog, so distance cannot grey it
     out; and the vertical wash it is painted with starts at white rather than at
     the scene's bone. It still rises glyph by glyph and still dissolves as the
     camera closes on it — the choreography is untouched, only the occlusion. */
  [
    `new THREE.MeshBasicMaterial({ map: tx(c, { aniso: 16 }), transparent: true,
        depthWrite: false, side: THREE.DoubleSide, fog: true, opacity: 1 })`,
    `new THREE.MeshBasicMaterial({ map: tx(c, { aniso: 16 }), transparent: true,
        depthWrite: false, depthTest: false, side: THREE.DoubleSide, fog: false, opacity: 1 })`,
  ],
  ["grad.addColorStop(0, 'rgb(226,236,229)');", "grad.addColorStop(0, 'rgb(255,255,255)');"],
  ["grad.addColorStop(.52, 'rgb(198,214,203)');", "grad.addColorStop(.52, 'rgb(240,246,242)');"],
  ["grad.addColorStop(1, 'rgb(150,170,157)');", "grad.addColorStop(1, 'rgb(206,220,211)');"],

  /* Six letters, not four. Upstream fills the frame exactly, which is safe for a
     word whose last glyph is a K; MERGIT ends in a T, whose right arm sat under
     the scrollbar gutter — the frame is measured from the window and the canvas
     is narrower than it by that much. Held a little inside instead. */
  ["const fill = narrow ? .96 : 1.00;", "const fill = narrow ? .93 : .955;"],

  /* And lifted off the floor of the frame. The preview card is pinned to the
     bottom-right corner in this layout, which is where the last two letters
     land; raising the baseline clears the card rather than arguing with it. */
  ["const base = hit(0, narrow ? -.16 : -.585);", "const base = hit(0, narrow ? -.20 : -.50);"],

  /* The card cloth, and the black rectangles it used to leave behind.
     ----------------------------------------------------------------------------
     Each card's still is drawn into a 2D canvas, rippled, and uploaded as a WebGL
     texture. The page is framed with `sandbox` and no `allow-same-origin`, so its
     origin is opaque and every asset it loads is a cross-origin one: drawing the
     still taints the canvas, and `texImage2D` on a tainted canvas throws.

     Upstream never sees this — it serves the page at the top level — and the
     failure is not graceful. The output canvas is appended to the card before the
     cloth is built, so the throw escapes with the canvas still in the DOM,
     covering the card's own painting with nothing. That is the "empty" section:
     three black rectangles where the stills should be.

     Two changes. The image is requested with CORS credentials of its own, which
     the server answers for /landing (see backend/main.py and vite.config.ts), so
     the canvas is never tainted and the cloth works as authored. And if that
     header is ever missing, the build is caught and the canvas removed, so the
     card falls back to the still it already had rather than to a black hole. */
  [
    `    const img = new Image();
    img.onload = () => {`,
    `    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {`,
  ],
  [
    `      const inst = createCloth(out, get, { wind: 3, speed: .5, amplitude: 30, drape: 40,
        brush: 2.05, brushSize: 150, damping: 1, light: .5, sheen: .1, shadow: .25,
        cornerRadius: 20, perspective: 1200, pin: 'top' });`,
    `      let inst = null;
      try {
        inst = createCloth(out, get, { wind: 3, speed: .5, amplitude: 30, drape: 40,
          brush: 2.05, brushSize: 150, damping: 1, light: .5, sheen: .1, shadow: .25,
          cornerRadius: 20, perspective: 1200, pin: 'top' });
      } catch {
        /* a tainted canvas, or no WebGL left to give — either way the card keeps
           the painting it already has */
        inst = null;
      }`,
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

/* The hero's call to action.
   ------------------------------------------------------------------------------
   Kage's hero has nowhere to send anyone — it is one document, and the only way
   on is down. Mergit's hero is the top of a product, and the console was three
   full screens below the fold in the only place it appeared. This puts it under
   the sub-heading, beside a second link that does what the scroll cue asks for,
   in the idiom the page already uses for both. */
const HERO_CTA = [
  `<p class="hero-sub body" data-rv="up">One sentence becomes a task graph, and specialised agents execute it against real systems.</p>`,
  `<p class="hero-sub body" data-rv="up">One sentence becomes a task graph, and specialised agents execute it against real systems.</p>
    <div class="hero-act" data-rv="fade">
      <a class="arrowlink" href="#mergit:/app" data-cursor>
        <span>Open the console</span>
        <span class="ar"><svg viewBox="0 0 14 14" fill="none"><path d="M3 11 11 3M5 3h6v6" stroke="#dfe7e0" stroke-width="1.3"/></svg></span>
      </a>
      <a class="arrowlink arrowlink--quiet" href="#gate" data-cursor>
        <span>See how a run works</span>
        <span class="ar"><svg viewBox="0 0 14 14" fill="none"><path d="M7 3v8M3.4 7.6 7 11.2l3.6-3.6" stroke="#dfe7e0" stroke-width="1.3"/></svg></span>
      </a>
    </div>`,
];

/* Chapter II, given something to say.
   ------------------------------------------------------------------------------
   The section was three card viewports under a rule and nothing else: upstream
   used it as a wordless gallery of the temple, and a gallery of a place needs no
   caption. Forked onto a product it read as a page that had failed to load —
   which is exactly how it was reported. The heading and lead below say what the
   chapter is, and each card now carries the sentence its label was standing in
   for, so the section explains the run whether or not the live views ever draw. */
const PATHWAYS_INTRO = [
  `<div class="sec-head" data-rv="fade">
    <span class="k"><b>02</b> — The graph</span><span class="rule"></span><span class="k jp">roles</span>
  </div>
  <div class="cards" id="cards">`,
  `<div class="sec-head" data-rv="fade">
    <span class="k"><b>02</b> — The graph</span><span class="rule"></span><span class="k jp">roles</span>
  </div>
  <div class="cur-head">
    <h2 class="display h-sec" data-rv="up">How the work actually gets done.</h2>
    <p class="body-lg" data-rv="up">A run has three movements. The orchestrator turns your sentence into a graph of tasks and their dependencies; specialised agents execute those tasks with real tools against real systems; and every finished task hashes what it produced and mints a proof on chain.</p>
  </div>
  <div class="cards" id="cards">`,
];

/* The card copy. Each pairs with the label already in the frame. */
const CARD_COPY = [
  [
    `<div class="card-meta"><span>The task graph</span><span>01 / 03</span></div>`,
    `<div class="card-meta"><span>The task graph</span><span>01 / 03</span></div>
      <p class="card-copy">A planning model reads the goal and writes the graph: every task, what it needs first, and which of the six agent roles owns it. Nothing runs until the shape of the work is decided.</p>`,
  ],
  [
    `<div class="card-meta"><span>Real side effects</span><span>02 / 03</span></div>`,
    `<div class="card-meta"><span>Real side effects</span><span>02 / 03</span></div>
      <p class="card-copy">Each agent works a tool-call loop — reading the repository, running code, posting to Slack, opening the pull request. The side effects are real, so the approvals and the spend limits are too.</p>`,
  ],
  [
    `<div class="card-meta"><span>The proof</span><span>03 / 03</span></div>`,
    `<div class="card-meta"><span>The proof</span><span>03 / 03</span></div>
      <p class="card-copy">A finished task hashes its own output and writes the record to chain. The claim that the work happened stops being the agent's word for it and becomes something anyone can check.</p>`,
  ],
];

/* The footer's last column.
   ------------------------------------------------------------------------------
   Upstream's "Elsewhere" is a colophon: journal, field notes, colophon, all
   pointing at `#top` because the page is the whole site. Forked onto a product
   those became three links that look like a way out and are not one. They are
   repointed at the console, which is the only elsewhere Mergit has.

   The `#mergit:` prefix is the sentinel the nav bridge turns into a real
   navigation — see CTA_LINKS below for why an anchor cannot do this itself. */
const FOOTER_LINKS = [
  `      <li><a href="#top" data-cursor>Open the console</a></li>
      <li><a href="#top" data-cursor>Delegate a goal</a></li>
      <li><a href="#top" data-cursor>Sign in</a></li>`,
  `      <li><a href="#mergit:/app" data-cursor>Open the console</a></li>
      <li><a href="#mergit:/app" data-cursor>Delegate a goal</a></li>
      <li><a href="#mergit:/login" data-cursor>Sign in</a></li>`,
];

/* The menu behind the two lines.
   ------------------------------------------------------------------------------
   Upstream's burger is a phone control: the handler returns early above 820px,
   because above 820px the links it would reveal are already in the bar. Forked
   here it kept its hover animation at every width and did nothing at most of
   them — a button that responds to the cursor and then declines to act reads as
   broken, and was reported as broken.

   Rather than hide it, it is given the thing a desktop menu is actually for and
   the bar has no room for: the chapters by name, and the ways into the product.
   Below 820px nothing changes — upstream's sheet still owns the click. */
const MENU_MARKUP = [
  "</header>",
  `</header>

<div class="menu" id="menu" aria-hidden="true">
  <div class="menu-in">
    <div class="menu-col">
      <h4>Chapters</h4>
      <ul>
        <li><a href="#top" data-cursor><b>00</b> The goal</a></li>
        <li><a href="#gate" data-cursor><b>01</b> The plan</a></li>
        <li><a href="#pathways" data-cursor><b>02</b> The graph</a></li>
        <li><a href="#lessons" data-cursor><b>03</b> The run</a></li>
        <li><a href="#eternity" data-cursor><b>04</b> Settlement</a></li>
      </ul>
    </div>
    <div class="menu-col">
      <h4>Product</h4>
      <ul>
        <li><a href="#mergit:/app" data-cursor><b>→</b> Open the console</a></li>
        <li><a href="#mergit:/app" data-cursor><b>→</b> Delegate a goal</a></li>
        <li><a href="#mergit:/login" data-cursor><b>→</b> Sign in</a></li>
      </ul>
    </div>
    <div class="menu-col menu-note">
      <h4>Mergit</h4>
      <p>Describe the outcome, not the steps. One sentence becomes a task graph, specialised agents execute it with real tools, and every finished task mints a proof on chain.</p>
      <span class="jp">a finished task is a fact, not a claim</span>
    </div>
  </div>
</div>`,
];

const PAGE_STYLE = `<style data-mergit-page>
  /* The hero's two links, on one line until the frame is too narrow for it. */
  .hero-act{ display:flex; flex-wrap:wrap; align-items:center; gap:clamp(18px,2.4vw,38px); margin-top:clamp(20px,2.6vh,32px); }
  .arrowlink--quiet{ color:var(--bone-dim); }
  /* On a phone the two links stack, and the second one lands in the wordmark.
     It is also the only link on the page that duplicates something already
     there — the scroll cue says the same thing a few lines down. */
  @media (max-width:820px){ .arrowlink--quiet{ display:none; } }

  /* The preview card shares the lower-right corner with the last letters of the
     wordmark. It is moved down and in by the width of one letter's overhang, so
     the two sit beside each other instead of on top of each other. */
  body[data-layout-hero="b"] .peek{ bottom:clamp(20px,3.6vh,58px); width:clamp(140px,13.5vw,224px); }
  .arrowlink--quiet:hover{ color:var(--bone); }

  /* Chapter II's card copy. Held to a reading measure and dimmed one step below
     the card label, so the three of them read as captions to the viewports
     rather than as three columns of body text. */
  .card-copy{
    margin-top:10px; max-width:42ch;
    font-size:clamp(12px,.86vw,13.5px); line-height:1.62; color:var(--muted);
  }

  /* The menu. A full-frame sheet rather than a dropdown: it is the only thing on
     screen while it is open, so it does not have to win a stacking contest with
     a canvas, a vignette and a grain layer. */
  .menu{
    position:fixed; inset:0; z-index:60;
    display:grid; place-items:center; padding:calc(var(--pad) + 40px) var(--pad) var(--pad);
    background:rgba(3,6,9,.93);
    opacity:0; visibility:hidden; pointer-events:none;
    transition:opacity .42s var(--ease), visibility 0s linear .42s;
  }
  @supports (backdrop-filter: blur(1px)) { .menu{ backdrop-filter:blur(18px) saturate(.9); } }
  html.menu-open .menu{ opacity:1; visibility:visible; pointer-events:auto; transition-delay:0s; }
  html.menu-open, html.menu-open body{ overflow:hidden; }
  /* The bar rides above the sheet, or the control that opened it — and the only
     one that closes it — is the one thing the sheet covers. The links go with
     the sheet instead: they are the first column of it. */
  html.menu-open .nav{ z-index:70; }
  html.menu-open .nav-links{ opacity:0; pointer-events:none; }
  .nav-links{ transition:opacity .3s var(--ease); }
  .menu-in{
    width:min(1180px,100%);
    display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:clamp(28px,5vw,88px);
  }
  .menu-col h4{
    margin:0 0 18px; padding-bottom:12px; border-bottom:1px solid var(--line);
    font-size:10px; font-weight:500; letter-spacing:.24em; text-transform:uppercase; color:var(--muted);
  }
  .menu-col ul{ list-style:none; margin:0; padding:0; }
  .menu-col li{ margin:0; }
  .menu-col a{
    display:flex; align-items:baseline; gap:14px; padding:11px 0;
    font-size:clamp(16px,1.5vw,22px); font-weight:300; letter-spacing:-.01em;
    color:var(--bone-dim); transition:color .3s var(--ease), transform .45s var(--ease-out);
  }
  .menu-col a b{ font-size:10px; font-weight:500; letter-spacing:.18em; color:var(--vermilion); }
  .menu-col a:hover{ color:var(--bone); transform:translate3d(6px,0,0); }
  .menu-note p{ margin:0 0 16px; max-width:38ch; font-size:13px; line-height:1.7; color:var(--muted); }
  .menu-note .jp{ font-size:11px; letter-spacing:.26em; color:var(--bone-dim); }
  /* Upstream animates the two lines into a cross only inside its phone query. */
  .nav-burger.active i:nth-child(1){ top:7px; width:26px; transform:rotate(45deg); }
  .nav-burger.active i:nth-child(2){ top:7px; width:26px; transform:rotate(-45deg); }
  @media (max-width:820px){
    .menu{ display:none; }   /* upstream's own sheet owns this width */
  }
  @media (max-width:1100px){
    .menu-in{ grid-template-columns:repeat(2,minmax(0,1fr)); }
    .menu-note{ display:none; }
  }
  @media (prefers-reduced-motion: reduce){
    .menu{ transition-duration:.001s; }
    .menu-col a{ transition:none; }
  }
</style>`;

/* Opening and closing it. Upstream's handler runs first and returns early above
   820px, so this one takes that width and leaves the other alone. */
const MENU_SCRIPT = `<script data-mergit-menu>
(function () {
  var root = document.documentElement;
  var burger = document.querySelector(".nav-burger");
  var menu = document.getElementById("menu");
  if (!burger || !menu) return;
  var WIDE = 820;

  function set(open) {
    root.classList.toggle("menu-open", open);
    burger.classList.toggle("active", open);
    burger.setAttribute("aria-expanded", String(open));
    menu.setAttribute("aria-hidden", String(!open));
  }
  function close() { if (root.classList.contains("menu-open")) set(false); }

  burger.addEventListener("click", function () {
    if (innerWidth <= WIDE) return;
    set(!root.classList.contains("menu-open"));
  });
  /* Anything that navigates closes it, including the console links — those are
     handled by the nav bridge, which does not touch this class. */
  menu.addEventListener("click", function (event) {
    if (event.target.closest("a")) close();
  });
  addEventListener("keydown", function (event) { if (event.key === "Escape") close(); });
  addEventListener("resize", function () { if (innerWidth <= WIDE) close(); }, { passive: true });
})();
<\/script>`;

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
    /* Exactly once, like every other table here. These reach into 173KB of scene
       source, where a literal that happens to appear twice would be edited twice
       and the second edit would land somewhere nobody looked at. */
    const hits = patchedTail.split(from).length - 1;
    if (hits !== 1) {
      throw new Error(`scene copy matched ${hits} times, expected 1: ${JSON.stringify(from.slice(0, 60))}`);
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

  /* Everything Mergit adds to the page rather than renames on it: the hero's
     links, chapter II's heading and captions, and the menu sheet. Each is an
     exactly-once substitution for the same reason the copy table is — a miss
     here would ship a landing page quietly missing a section. */
  for (const [from, to] of [HERO_CTA, PATHWAYS_INTRO, ...CARD_COPY, FOOTER_LINKS, MENU_MARKUP]) {
    const hits = head.split(from).length - 1;
    if (hits !== 1) {
      throw new Error(`insertion point matched ${hits} times, expected 1: ${JSON.stringify(from.slice(0, 70))}`);
    }
    head = head.replace(from, to);
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
  out = out.replace("</body>", `${NAV_BRIDGE}\n${MENU_SCRIPT}\n</body>`);
  out = out.replace("</head>", `${PAGE_STYLE}\n</head>`);
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
