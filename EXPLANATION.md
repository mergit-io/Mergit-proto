# omniBox — 5-Minute Pitch & Explanation

---

## [0:00 – 0:30] The Hook — Why This Exists

"Let me start with a question. How many of you have had a GitHub issue sit unresolved for 3 days — not because it was hard, but because nobody had the time to context-switch into that codebase, read the code, write a fix, open a PR, and leave a comment?

That's not an engineering problem. That's a coordination and bandwidth problem.

What if you could just describe the problem in plain English, walk away, and come back to a merged pull request?

That's omniBox. A multi-agent autonomy system that takes any natural-language goal and executes it end-to-end. No scripts. No templates. No human in the loop."

---

## [0:30 – 1:15] What It Is — The Big Picture

"omniBox is built around one idea: **the orchestrator decides, the agents execute, the tools act on the real world.**

Here's how it works at a high level.

You type a goal. Anything — fix a bug, add a CI pipeline, research a topic and write a report, build a new GitHub repo from scratch. The system takes that goal and sends it to an **orchestrator** — a Claude model — whose only job is to decompose that goal into a **task graph**: a DAG of specialist agents, each with specific inputs, tools, and dependencies.

That plan is persisted to a SQLite database. Three asyncio loops run continuously inside the backend — one picks up new goals and orchestrates them, one picks up ready tasks and executes them in parallel up to five at a time, and one reclaims any tasks that crashed mid-run and retries them. If the server dies and restarts, every goal picks up exactly where it left off. Nothing is lost.

That's the foundation. Now let me walk you through the actual components."

---

## [1:15 – 2:15] The Agents — Specialist Execution

"We have four specialist agents. Each one has its own model, its own set of tools, and its own output schema.

**Researcher** — powered by Groq's LLaMA 4 Maverick, the fastest model we have. It searches the web via Tavily, reads GitHub repos file by file, fetches issue details, searches code by symbol, and synthesises everything into a structured output: summary, key points, sources, and raw code context for downstream agents.

**Writer** — takes research or raw API data and produces polished, human-readable output. Reports, architecture docs, PR descriptions. It's also wired to generate Mermaid diagrams — so if you ask it to document a codebase, you get an interactive flowchart rendered right in the UI.

**Coder** — writes real, runnable Python. Not pseudocode. It executes the code in a sandboxed subprocess with a 30-second timeout, captures the actual terminal output, and only submits if the code ran successfully. If it fails, it reads its own error and tries again.

**Integrator** — the one that acts on the real world. It opens GitHub pull requests, posts comments on issues, creates entire new repositories with README files, reads and sets branch protection rulesets, and manages GitHub Actions workflows. It can also wait for an inbound webhook — suspending itself until an external event arrives.

All four agents run through the same generic agent runner. It's a tool-call loop: build messages, call the LLM, execute any tool calls, store results, repeat until the agent calls submit_result. Every tool call is idempotency-checked — we hash the task ID, tool name, and arguments, and if we've already run this exact call successfully, we return the stored result instead of re-running. That's how we prevent duplicate PRs or double Slack posts after a crash."

---

## [2:15 – 3:00] The Demo Flow — GitHub Issue to Pull Request

"Let me make this concrete with the flagship flow.

A developer opens a GitHub issue: 'The calculate function returns None for zero input instead of returning 0.'

omniBox receives that via a webhook. It auto-creates a goal. The orchestrator plans three tasks in under two seconds.

Task one: Researcher. It calls github_get_issue to read the bug description. Then github_list_dir to explore the repo structure. Then github_read_file on the relevant source files. It outputs the code context — the actual broken function — plus a summary of the bug.

Task two: Coder. It receives that code context. It writes a fix — a real Python patch. It runs it with code_exec and verifies the output matches the expected behaviour. Only once it passes does it submit.

Task three: Integrator. It receives the fixed code from the coder. It calls github_pr — which commits the changed files, creates a feature branch, and opens a pull request with a professional description: Summary, Problem, Root Cause, Fix, Verification with the actual test output. Then it calls github_post_comment on the original issue, posting the PR link.

From webhook to merged-ready PR — fully autonomous. The developer opens their phone to a comment saying 'I've fixed this — here's the PR.'"

---

## [3:00 – 3:45] True Autonomy — What Makes It Different

"Most 'agent' systems are scripted. They fail, they die, and a human restarts them. We built three layers of true autonomy.

**Layer one: Dynamic replanning.** If a task hits its retry limit and fails, we don't kill the goal. We call the orchestrator again — with the context of what completed, what failed, and why — and ask it to devise an alternative path. New tasks are inserted into the graph. The goal continues.

**Layer two: spawn_goal.** Any agent, mid-execution, can call the spawn_goal tool. If the researcher discovers a problem that's bigger than its current task — a systemic bug, a missing dependency — it creates a new autonomous goal and hands it off. The system branches without human input.

**Layer three: Self-heal.** We have an error classifier that distinguishes between external failures — rate limits, network errors, auth issues — and developer-side bugs — crashes in our own code. When it detects a bug in omniBox itself, it automatically files a GitHub issue on our repo, then spawns a fix goal: researcher reads the broken file, coder writes the patch, integrator opens the PR. The system debugs and fixes itself."

---

## [3:45 – 4:20] The Stack — Why These Choices

"Quick word on the technical choices, because they're intentional.

**Groq for leaf agents** — LLaMA 4 Maverick for the researcher because speed matters when you're making 10 tool calls in sequence. LLaMA 3.3 70B for writer, coder, integrator — excellent instruction following, fast enough for multi-step tool use.

**Claude for orchestration** — planning a task DAG is a reasoning problem. Claude produces valid, well-structured plans consistently. Groq models are available as fallback when Claude is unavailable.

**SQLite WAL** — single-file, zero operational overhead, supports concurrent reads and atomic writes. For a system that needs to survive restarts and run on any machine without a database server, it's the right choice.

**LiteLLM** — provider-agnostic LLM layer. We support 40 models across Groq, Anthropic, OpenAI, Google, and Mistral. You switch models from the UI — no code changes, no restart.

**React Flow + SSE** — the frontend visualises the task DAG live. Every tool call, every agent message, every status change streams over Server-Sent Events to the dashboard in real time. You watch the agents think."

---

## [4:20 – 4:50] Business Impact — Who Needs This

"The market for this is any engineering team that ships software and files bugs. That's every software company on earth.

The specific pain points we eliminate:

- **Issue-to-PR latency** — from days to minutes, zero developer time.
- **CI/CD setup toil** — 'add a pytest workflow to this repo' becomes a one-sentence instruction instead of an hour of YAML writing.
- **Codebase onboarding** — new engineers ask omniBox to map the architecture. They get a Mermaid diagram and a written explanation based on the actual source code, not stale documentation.
- **Open source maintainer burnout** — hundreds of issues, two maintainers. omniBox triages, fixes the clear bugs, and hands back only the hard ones.

The differentiator is that this isn't a copilot. It's not autocomplete. It's a system that completes entire workflows end-to-end, verifies its own output, recovers from its own failures, and gets smarter about your codebase the more it runs."

---

## [4:50 – 5:00] Close

"omniBox is open source, runs locally with a single make command, supports 40 LLM models, traces every execution through Omium, and just built and submitted this pitch autonomously.

The code is at github.com/viscous106/omniBox.

Thank you."

---

---

# Appendix — Q&A Prep

**Q: How do you prevent agents from doing things they shouldn't?**
> Tool access is scoped per agent — the writer can only read/write files in a sandboxed workspace directory, the researcher can't open PRs, the coder can't post to GitHub. Tool invocations are also logged and idempotency-checked, so even if an agent tries to re-run a side-effect, it won't fire twice.

**Q: What happens if the LLM produces a bad plan?**
> The orchestrator retries up to 5 times. Each failed attempt appends the validation error to the conversation so the model can self-correct. We also auto-fill missing dependency edges from template references, so if the model forgets to declare a dependency it referenced in the inputs, we add it automatically.

**Q: How is this different from LangChain or AutoGen?**
> Those are frameworks — they give you building blocks. omniBox is a complete running system: persistence, crash recovery, idempotency, live UI, SSE streaming, multi-provider LLM fallback, self-healing, and a production-ready API. You don't write any code to use it — you describe goals.

**Q: What's the cost per goal?**
> Entirely depends on the goal complexity and model choice. A typical GitHub fix goal with Groq's free tier costs fractions of a cent — Groq's inference is fast and cheap. For heavy orchestration with Claude, costs are still in the single-digit cents range per goal.

**Q: Can it handle goals it's never seen before?**
> Yes — that's the point. The orchestrator doesn't match against a template library. It reasons about the goal from first principles and decomposes it using the agent descriptions and tool capabilities in its system prompt. We've tested it with goals we never anticipated and it produces valid plans.

**Q: What's next?**
> Memory per repo — agents that accumulate understanding of a codebase across goals. Multi-repo orchestration. A hosted version with team workspaces. And a webhook-first mode where omniBox monitors repos continuously and acts on new issues and PRs without any manual trigger.
