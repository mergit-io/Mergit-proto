# omniBox — 3-Minute Demo Video Script
**Hackathon: Anvil MMXXVI — Multi-Agent Autonomy Track**

---

## Pre-recording checklist
- [ ] `make dev` running — backend on :8000, frontend on :3000
- [ ] Backend `.env` has: `GROQ_API_KEY`, `GITHUB_TOKEN`, `TAVILY_API_KEY`
- [ ] `GITHUB_DEFAULT_REPO` set to a real repo you own with an open issue
- [ ] Browser open at `http://localhost:3000` — logged in, Dashboard visible
- [ ] OBS / Quicktime recording at 1920×1080, mic test done
- [ ] Terminal open with `make dev` output visible (optional B-roll)

---

## [0:00 – 0:18] HOOK — The Problem

**Screen:** Landing page (`/`) — hero section visible

**Narration (speak naturally):**
> "Every dev team has the same problem — someone files a GitHub issue, and it sits there for days while engineers context-switch to read the code, write a fix, open a PR, and leave a comment. What if that entire workflow ran itself?
> This is omniBox — a multi-agent autonomy system that takes any natural-language goal and executes it end-to-end with no human in the loop."

---

## [0:18 – 0:45] OVERVIEW — What it does

**Screen:** Slowly scroll the landing page — Features section, HowItWorks

**Narration:**
> "omniBox is not a chatbot and it's not a scripted pipeline. You describe a goal in plain English. A Claude orchestrator decomposes it into a task DAG — a directed graph of specialist agents. Each agent has its own model, tools, and output schema. They execute in parallel where dependencies allow, and the results chain into each other automatically.
> Four agents: Researcher, Writer, Coder, and Integrator — each powered by Groq's fastest models."

---

## [0:45 – 1:30] DEMO 1 — GitHub Issue Auto-Fix (the main flow)

**Screen:** Switch to Dashboard (`/app`), cursor on the goal input box

**Narration:**
> "Let me show you the flagship feature — autonomous GitHub issue fixing."

**[Type into the input box — speak as you type:]**
```
Fix the bug in [your-repo]/[repo-name] issue #1 and open a pull request
```

> "I hit Delegate. The orchestrator plans this in under two seconds."

**[Goal detail page opens, DAG appears with 3 nodes: researcher → coder → integrator]**

> "Three agents — Researcher reads the repo and the issue, Coder writes the fix and runs it, Integrator opens the PR and posts a comment. Watch the live log on the right — every tool call streams in real time."

**[Point to the Live Log panel — tool calls ticking: github_get_issue, github_list_dir, github_read_file…]**

> "The Researcher is reading the codebase right now. It uses GitHub's API — not just cloning the repo, but intelligently navigating to the files relevant to the bug."

**[Pause ~10 seconds — let it run, narrate what you see]**

> "Coder agent has the code context now — it's writing a fix and running it in a sandboxed subprocess to verify the output."

**[Wait for integrator to start]**

> "Integrator is opening the pull request… and posting a comment on the original issue with the PR link."

**[Goal shows COMPLETED — click Output panel]**

> "Done. A real pull request, opened on a real GitHub repo, with a professional PR description — fully autonomous, zero human intervention."

---

## [1:30 – 1:55] DEMO 2 — Architecture Diagram from Repo

**Screen:** Back to Dashboard input

**[Type:]**
```
Analyze the architecture of [owner]/[repo] and generate a Mermaid flow diagram of all components and data flow
```

**[Navigate to Goal Detail — after completion, click Output]**

**Narration:**
> "This is the Writer agent producing a Mermaid architecture diagram — rendered live in the browser. The Researcher read the actual source files to produce this — not hallucinated, grounded in the real code."

**[Point to the SVG Mermaid diagram in the output panel]**

---

## [1:55 – 2:20] DEMO 3 — GitHub Actions Automation

**Screen:** Navigate to `/app/actions`

**Narration:**
> "The Actions page lets you inspect a repo's CI/CD setup and automate changes with natural language."

**[Type repo name, click Load — workflows and branch protection appear]**

**[Click quick action chip: "Add CI (pytest)"]**

> "One click pre-fills the instruction. I hit Delegate — the agents will write the GitHub Actions YAML, open a PR with it, and configure branch protection if needed. All from a sentence."

**[Click Delegate — navigate to the goal detail]**

---

## [2:20 – 2:45] AUTONOMY HIGHLIGHT — Self-heal & Replanning

**Screen:** Brief screen-share of code or backend logs (terminal)

**Narration:**
> "What makes omniBox actually autonomous — not just scripted — is what happens when things go wrong.
>
> If a task hits its retry limit, a **dynamic replanner** kicks in — the orchestrator is called again with context of what completed and what failed, and it devises an alternative plan. The goal continues.
>
> If the system detects a *developer-side bug* — a crash in our own code — it automatically files a GitHub issue on the omniBox repo and spawns a fix goal. The system debugs itself.
>
> And any agent can call **spawn_goal** mid-execution to create sub-goals it discovers are needed — true emergent autonomy."

---

## [2:45 – 3:00] CLOSE — Stack & Availability

**Screen:** Models page (`/app/models`) — show the 40 model choices briefly, then back to landing

**Narration:**
> "omniBox supports 40 LLMs across Groq, Anthropic, OpenAI, Google, and Mistral — switchable at runtime with no restarts. It's fully traced with Omium SDK, persisted to SQLite for crash recovery, and the entire UI streams live via Server-Sent Events.
>
> Source code is at github.com/viscous106/omniBox.
> omniBox — any goal, fully autonomous."

**[Fade to landing page hero]**

---

## Recording tips

| Section | Screen | Notes |
|---------|--------|-------|
| 0:00–0:18 | Landing page | Slow scroll, let animations play |
| 0:18–0:45 | Landing features | Move cursor gently, don't rush |
| 0:45–1:30 | Dashboard → Goal Detail | This is your longest segment — let it actually run, don't fast-forward |
| 1:30–1:55 | Goal Output (Mermaid) | Zoom in on the diagram SVG |
| 1:55–2:20 | Actions page | Keep it brisk — 25 seconds only |
| 2:20–2:45 | Terminal / code | Can use a pre-recorded or frozen log |
| 2:45–3:00 | Models → Landing | Gentle fade out |

**Cut pacing:** Edit out wait time between tool calls in Demo 1. Speed up 2× anything that's just a spinner, cut back to 1× when output appears.

**Music (optional):** Low ambient electronic — keep it under the voice, not over it.
