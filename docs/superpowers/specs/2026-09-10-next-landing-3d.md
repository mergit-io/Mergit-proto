# Mergit — `/next`, an editorial landing built around one 3D object (Design)

**Date:** 2026-09-10
**Status:** Approved (design)
**Relates to:** the moss landing at `/` (`docs/…/2026-07-18-mergit-prototype-design.md` era markup, rebuilt in #32/#33)

## Purpose

Build a second landing page, at `/next`, in the genre of clinical editorial
product sites: a bright ground, a strict grid, generous whitespace, restrained
type, and one three-dimensional object that the whole page is composed around.
It exists to be compared against the moss landing at `/` on a deployed URL, so
the choice between them is made by looking rather than by arguing.

The reference the user brought was a Behance concept (DENTAX, Andrii
Chervenshchuk). Two facts about it shaped this design: it is a **static Figma
concept**, so its 3D is pre-rendered stills and there is no motion to match; and
it is **unlicensed portfolio work**, so nothing of it is reused. What is taken is
the genre — grid discipline, whitespace, one hero object — which is not anyone's
property. What is built is original, and goes further than the reference by
making the object real rather than rendered.

## Decisions taken (user, 2026-09-10)

1. **A separate route**, not a replacement. `/` keeps the moss world; `/next` is
   a deployed candidate. Promotion is a later decision.
2. **The hero object is the proof block** — already Mergit's mark, already
   meaning "a finished task, sealed". No new vocabulary to teach a visitor.
3. **Procedural geometry**, authored in code. No modelled asset, no `.glb`, no
   licensing question, no megabytes.
4. **Bright editorial palette**, as in the reference — a light landing in front
   of a dark console.

## Success criteria

- `/next` renders the object, lit and composed, at 60fps on a mid-range laptop.
- `/` and `/app` download **zero** bytes of the 3D stack. Verified from a
  request log, not asserted.
- The page is readable, navigable and correct with WebGL unavailable, with
  motion refused, and on a phone.
- Body copy holds 4.5:1 on the light ground; large type holds 3:1. Measured.
- No claim on the page that the system does not support (`economy.ROLES`,
  the provider chain in `backend/model_config.py`, the stack table).

## Scope (in)

- Route `/next`, lazily loaded, public.
- A `.landing-paper` token scope, in the same mechanism `.landing-moss` uses.
- `ProofObject`: procedural hex shell, lit core, generated environment.
- Scroll choreography over the hero, driven by ScrollTrigger.
- Editorial sections reusing existing content: the run stages, the receipts,
  the stack.

## Scope (out)

- Any change to `/`, `/app`, or the console's two themes.
- Modelled or purchased 3D assets.
- Copy that does not already exist and is not already true.
- Promotion of `/next` to `/`. Separate decision, separate PR.

## Architecture

### 1. Route isolation — `src/App.tsx`, `src/pages/NextLanding.tsx`

`/next` is added with `React.lazy` + `Suspense`. The 3D stack (`three`,
`@react-three/fiber`, `@react-three/drei`, all MIT) is imported only from
components under `src/components/next/`, which only this route mounts. The
consequence is the success criterion above: nothing else on the site pays for it.

### 2. Palette — `.landing-paper` in `src/index.css`

Tokens are re-pointed for the page's subtree exactly as `.landing-moss` does:
set on the page's root element, where they win by inheritance rather than by
specificity, so `/app` is untouchable from here. Starting values derive from the
existing `[data-theme="light"]` block, tightened for editorial use — `#F4F4F1`
ground, white panels, `#101010` type, `#E2E2DC` hairlines, violet kept as the
single accent for brand continuity. `data-landing="paper"` on `<html>` hands the
document's own ground to the page, and is removed on unmount.

### 3. The object — `src/components/next/ProofObject.tsx`

Procedural, in three parts:

- **Shell** — a hexagonal prism from `ExtrudeGeometry` with a bevel, in
  `MeshPhysicalMaterial` with transmission, `ior` 1.45 and low roughness. Cut in
  two along the equator so the halves can separate.
- **Core** — a rounded box in an emissive material, the violet accent, breathing
  slowly.
- **Environment** — a PMREM-generated map from three's own `RoomEnvironment`.
  No HDR file ships; the lighting is computed at runtime from geometry.

The digest that appears on a face late in the choreography is a canvas texture,
drawn from the same string the run story uses.

### 4. Choreography

GSAP ScrollTrigger writes into refs; React never re-renders while scrolling.
Four beats over the hero's scroll: rest and idle rotation → camera dolly →
shell halves separate and the core brightens → digest etches onto a face.

### 5. Sections

Reuse what exists: `RUN_STAGES` (already shared between the card grid and the
pinned story), the receipt list, the stack table. Presented in the editorial
grid rather than the console's panels. No new claims are introduced, so nothing
new has to be kept true.

## Error handling and degradation

Each is a rendering path, not a failure message:

| Condition | Behaviour |
| --- | --- |
| `prefers-reduced-motion` | One composed frame, no rotation, no scroll choreography |
| No WebGL context | The object is not mounted; the hero composes without it |
| Weak GPU or a phone | Transmission dropped for an opaque material; `dpr` capped at 1.5 |
| Scrolled past / tab hidden | Frame loop stops and the context is released, as `SylvaScene` already does |
| 3D chunk fails to load | Hero renders without the object; `loadMotion`'s null path is the precedent |

## Testing

Headless Chrome here cannot bind a hardware WebGL context — established twice
while building `/`. So the automated checks cover everything except the object's
appearance, and the appearance is reviewed on the Render preview by a human:

- `npm run build` including `tsc -b`.
- Request log on `/` and `/app`: zero requests matching the 3D chunk names.
- Reduced-motion pass: no animation, page complete.
- Contrast: computed colours sampled and checked against 4.5:1 / 3:1.
- Layout at 1280, 1440 and 1920 wide, and at 430 wide.
- Accessibility tree: every section's content present and reachable.

## Delivery

Three stages, each one deployable on its own:

1. Route, palette, editorial sections. No 3D.
2. The object at rest, with isolation and payload verified.
3. Scroll choreography and the degradation paths.

One PR, a commit per stage.
