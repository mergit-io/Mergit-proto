"""
Generate the omniBox hackathon submission PDF.
Run: python generate_pdf.py
Output: omniBox_submission.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.graphics import renderPDF

# ── Brand colours ──────────────────────────────────────────────────
BLUE       = HexColor("#0095ff")
PURPLE     = HexColor("#673ae4")
BG_DARK    = HexColor("#0a0a0a")
CARD_BG    = HexColor("#111111")
CARD_EDGE  = HexColor("#1f1f1f")
TEXT_MAIN  = HexColor("#f9fafb")
TEXT_DIM   = HexColor("#9ca3af")
TEXT_MUTED = HexColor("#6b7280")
SUCCESS    = HexColor("#22c55e")
WARNING    = HexColor("#f59e0b")
DANGER     = HexColor("#ef4444")
CYAN       = HexColor("#00d7df")

W, H = A4  # 210 x 297 mm

# ── Doc setup ──────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    "omniBox_submission.pdf",
    pagesize=A4,
    leftMargin=18*mm, rightMargin=18*mm,
    topMargin=14*mm,  bottomMargin=14*mm,
)

styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

DISPLAY = "Helvetica-Bold"
BODY    = "Helvetica"
MONO    = "Courier"

# ── Helper styles ─────────────────────────────────────────────────
sHero  = S("Hero",  fontName=DISPLAY, fontSize=28, textColor=TEXT_MAIN,
           leading=34, alignment=TA_LEFT)
sSub   = S("Sub",   fontName=BODY,    fontSize=11, textColor=TEXT_DIM,
           leading=16, alignment=TA_LEFT)
sH1    = S("H1",    fontName=DISPLAY, fontSize=16, textColor=TEXT_MAIN,
           leading=22, spaceBefore=14, spaceAfter=4)
sH2    = S("H2",    fontName=DISPLAY, fontSize=12, textColor=BLUE,
           leading=18, spaceBefore=10, spaceAfter=2)
sBody  = S("Body",  fontName=BODY,    fontSize=9.5, textColor=TEXT_DIM,
           leading=15, alignment=TA_JUSTIFY, spaceAfter=4)
sBullet= S("Bullet",fontName=BODY,    fontSize=9,  textColor=TEXT_DIM,
           leading=14, leftIndent=12, spaceAfter=2,
           bulletIndent=4)
sMono  = S("Mono",  fontName=MONO,    fontSize=8,  textColor=CYAN,
           leading=12, backColor=HexColor("#0d1117"),
           leftIndent=8, spaceAfter=4)
sCaption=S("Caption",fontName=BODY,   fontSize=8,  textColor=TEXT_MUTED,
           leading=12, alignment=TA_CENTER)
sPageN = S("PageN", fontName=DISPLAY, fontSize=9,  textColor=TEXT_MUTED,
           alignment=TA_CENTER)

def hr(color=CARD_EDGE, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color,
                      spaceAfter=6, spaceBefore=6)

def bullet(text, color=BLUE):
    return Paragraph(f'<font color="#{color.hexval()[2:]}">▸</font>  {text}', sBullet)

def tag(label, color=BLUE, bg=None):
    bg_hex = bg.hexval()[2:] if bg else "0d2040"
    c_hex  = color.hexval()[2:]
    return (
        f'<font color="#{c_hex}" size="8"><b> {label} </b></font>'
    )

def agent_pill(name, color):
    hex = color.hexval()[2:]
    return Paragraph(
        f'<font color="#{hex}" size="9"><b>[ {name} ]</b></font>',
        S(f"pill_{name}", fontName=DISPLAY, fontSize=9, textColor=color,
          alignment=TA_CENTER)
    )

# ── Page background callback ───────────────────────────────────────
def dark_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BG_DARK)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)

    # subtle dot grid
    canvas.setFillColor(HexColor("#1a1a1a"))
    step = 18
    for x in range(0, int(W)+step, step):
        for y in range(0, int(H)+step, step):
            canvas.circle(x, y, 0.6, fill=1, stroke=0)

    # top gradient bar
    canvas.setFillColor(BLUE)
    canvas.rect(0, H-2, W, 2, fill=1, stroke=0)

    # footer
    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont(BODY, 7.5)
    canvas.drawCentredString(W/2, 8*mm, "omniBox  ·  Multi-Agent Autonomy System  ·  Anvil MMXXVI Hackathon")
    canvas.setFillColor(BLUE)
    canvas.drawRightString(W - 18*mm, 8*mm, f"page {doc.page}")
    canvas.restoreState()

# ══════════════════════════════════════════════════════════════════
# BUILD STORY
# ══════════════════════════════════════════════════════════════════
story = []

# ─────────────────────────────────────────────
# PAGE 1 — COVER + BUSINESS USE CASE
# ─────────────────────────────────────────────

# Logo wordmark
story.append(Spacer(1, 6*mm))
story.append(Paragraph(
    '<font color="#0095ff">omni</font><font color="#f9fafb">Box</font>',
    S("Logo", fontName=DISPLAY, fontSize=42, leading=46)
))
story.append(Spacer(1, 1*mm))
story.append(Paragraph(
    "Multi-Agent Autonomy System",
    S("Tagline", fontName=BODY, fontSize=13, textColor=TEXT_DIM, leading=18)
))
story.append(Spacer(1, 1*mm))

# Pill badges
pill_data = [
    [
        Paragraph(tag("Groq  LLaMA 4",  BLUE),   sCaption),
        Paragraph(tag("Claude Opus",     PURPLE),  sCaption),
        Paragraph(tag("GitHub API",      CYAN),    sCaption),
        Paragraph(tag("Anvil MMXXVI",    SUCCESS), sCaption),
    ]
]
pill_tbl = Table(pill_data, colWidths=[W*0.22]*4, rowHeights=[14])
pill_tbl.setStyle(TableStyle([
    ("ALIGN",       (0,0), (-1,-1), "CENTER"),
    ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
    ("BACKGROUND",  (0,0), (0,0),   HexColor("#0d2040")),
    ("BACKGROUND",  (1,0), (1,0),   HexColor("#1a0d3a")),
    ("BACKGROUND",  (2,0), (2,0),   HexColor("#0d2a2b")),
    ("BACKGROUND",  (3,0), (3,0),   HexColor("#0d2a1a")),
    ("ROUNDEDCORNERS", [4]),
    ("LEFTPADDING",  (0,0), (-1,-1), 8),
    ("RIGHTPADDING", (0,0), (-1,-1), 8),
]))
story.append(pill_tbl)
story.append(Spacer(1, 5*mm))
story.append(hr(BLUE, 1))

# One-liner
story.append(Paragraph(
    "Delegate <b>any</b> natural-language goal. An orchestrator decomposes it into a task graph, "
    "assigns specialist AI agents, invokes real tools, and delivers verified results — fully autonomously.",
    S("Oneliner", fontName=BODY, fontSize=10.5, textColor=TEXT_DIM, leading=16, alignment=TA_JUSTIFY)
))
story.append(Spacer(1, 5*mm))

# ── Business Use Case ─────────────────────────────────────────────
story.append(Paragraph("Business Use Case", sH1))
story.append(hr())

story.append(Paragraph(
    "Software teams lose <b>hours every day</b> routing bug reports, writing fix branches, opening PRs, "
    "updating CI pipelines, and chasing code reviews. omniBox eliminates that toil entirely.",
    sBody
))
story.append(Spacer(1, 2*mm))

# Use case table
uc_data = [
    [Paragraph("<b>Scenario</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Without omniBox</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=DANGER)),
     Paragraph("<b>With omniBox</b>",    S("TH", fontName=DISPLAY, fontSize=9, textColor=SUCCESS))],
    [Paragraph("GitHub issue filed",    sBody),
     Paragraph("Dev reads, reproduces, fixes, opens PR — 2–4 h", sBody),
     Paragraph("Agents fix & PR in < 5 min, zero human input", sBody)],
    [Paragraph("Add CI/CD pipeline",    sBody),
     Paragraph("DevOps writes YAML, commits, iterates — 1–2 h", sBody),
     Paragraph("One sentence → working GitHub Actions workflow + PR", sBody)],
    [Paragraph("Architecture review",   sBody),
     Paragraph("Senior engineer spends half a day documenting", sBody),
     Paragraph("Researcher reads repo → Writer produces Mermaid diagram + report", sBody)],
    [Paragraph("Codebase research",     sBody),
     Paragraph("Hours of grep, reading, note-taking", sBody),
     Paragraph("Researcher agent traverses & summarises in seconds", sBody)],
]
uc_tbl = Table(uc_data, colWidths=[42*mm, 65*mm, 65*mm])
uc_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0),  HexColor("#0d1827")),
    ("TEXTCOLOR",    (0,0), (-1,0),  TEXT_MAIN),
    ("FONTNAME",     (0,0), (-1,0),  DISPLAY),
    ("FONTSIZE",     (0,0), (-1,0),  8.5),
    ("BACKGROUND",   (0,1), (-1,-1), HexColor("#0a0a0f")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [HexColor("#0d0d12"), HexColor("#111118")]),
    ("GRID",         (0,0), (-1,-1), 0.4, CARD_EDGE),
    ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ("LEFTPADDING",  (0,0), (-1,-1), 6),
    ("RIGHTPADDING", (0,0), (-1,-1), 6),
    ("TOPPADDING",   (0,0), (-1,-1), 5),
    ("BOTTOMPADDING",(0,0), (-1,-1), 5),
]))
story.append(uc_tbl)
story.append(Spacer(1, 4*mm))

# Target customers
story.append(Paragraph("Target Market", sH2))
customers = [
    "Engineering teams shipping ≥ 5 GitHub repos who want automated issue-to-PR pipelines",
    "Platform / DevOps squads maintaining CI/CD configurations across many repos",
    "CTOs and tech leads who need instant codebase architecture reports",
    "Startups with small teams who can't afford senior DevOps headcount",
    "Open-source maintainers drowning in bug reports and contributor PRs",
]
for c in customers:
    story.append(bullet(c))

story.append(Spacer(1, 3*mm))
story.append(Paragraph("Value Proposition", sH2))
story.append(Paragraph(
    "omniBox is <b>provider-agnostic</b> (40 models across Groq, Anthropic, OpenAI, Google, Mistral), "
    "<b>restart-resumable</b> (SQLite WAL + lease reclaim), <b>self-healing</b> (auto-files issues and "
    "spawns fix goals on developer errors), and <b>fully observable</b> (Omium SDK tracing, live SSE dashboard). "
    "No proprietary lock-in. Deploy anywhere.",
    sBody
))

story.append(PageBreak())

# ─────────────────────────────────────────────
# PAGE 2 — AGENT ARCHITECTURE
# ─────────────────────────────────────────────
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Agent Architecture", sH1))
story.append(hr(BLUE, 1))
story.append(Paragraph(
    "omniBox is built on a <b>generic multi-agent execution engine</b>. The orchestrator (Claude) plans any goal "
    "as a directed acyclic graph (DAG) of tasks. Each task is assigned to a specialist agent that runs a "
    "tool-call loop until it calls <font face='Courier' size='8'>submit_result</font>.",
    sBody
))
story.append(Spacer(1, 3*mm))

# Orchestrator box
story.append(Paragraph("Orchestrator  (Claude / Groq LLaMA 4 Maverick)", sH2))
story.append(Paragraph(
    "Receives the natural-language goal → emits a <b>PlanSchema</b>: a list of TaskSpecs with IDs, agents, "
    "inputs, and dependency edges. Uses forced tool-call (<font face='Courier' size='8'>submit_plan</font>) "
    "with 5-attempt retry + Groq <i>failed_generation</i> salvage. Task IDs are prefixed with the goal UUID "
    "to prevent UNIQUE constraint collisions across concurrent goals.",
    sBody
))

# Agent table
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Specialist Agents", sH2))
ag_data = [
    [Paragraph("<b>Agent</b>",    S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Model</b>",    S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Tools</b>",    S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Output Schema</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN))],
    [Paragraph("researcher", S("A", fontName=DISPLAY, fontSize=9, textColor=BLUE)),
     Paragraph("Groq LLaMA 4 Maverick", sBody),
     Paragraph("web_search · http_request · github_read_file · github_list_dir · github_get_issue · github_search_code · spawn_goal", sBody),
     Paragraph("{summary, key_points, sources, code_context}", sMono)],
    [Paragraph("writer", S("A", fontName=DISPLAY, fontSize=9, textColor=CYAN)),
     Paragraph("Groq LLaMA 3.3 70B", sBody),
     Paragraph("file_ops", sBody),
     Paragraph("{text, title}", sMono)],
    [Paragraph("coder", S("A", fontName=DISPLAY, fontSize=9, textColor=PURPLE)),
     Paragraph("Groq LLaMA 3.3 70B", sBody),
     Paragraph("code_exec · file_ops · web_search · github_read_file", sBody),
     Paragraph("{code, output, success}", sMono)],
    [Paragraph("integrator", S("A", fontName=DISPLAY, fontSize=9, textColor=WARNING)),
     Paragraph("Groq LLaMA 3.3 70B", sBody),
     Paragraph("github_pr · github_post_comment · github_create_repo · github_list_workflows · github_set_branch_protection · http_request · wait_webhook · spawn_goal", sBody),
     Paragraph("{action, result, url}", sMono)],
]
ag_tbl = Table(ag_data, colWidths=[22*mm, 32*mm, 72*mm, 46*mm])
ag_tbl.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  HexColor("#0d1827")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [HexColor("#0d0d12"), HexColor("#111118")]),
    ("GRID",          (0,0), (-1,-1), 0.4, CARD_EDGE),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("LEFTPADDING",   (0,0), (-1,-1), 5),
    ("RIGHTPADDING",  (0,0), (-1,-1), 5),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
]))
story.append(ag_tbl)
story.append(Spacer(1, 4*mm))

# Autonomy features
story.append(Paragraph("Autonomy & Resilience Features", sH2))
auto_feats = [
    ("<b>Dynamic Replanning</b>", "When a task hits max retries, the orchestrator is called again with context of completed tasks + failure reason. It devises an alternative sub-plan and inserts new tasks — the goal continues instead of dying."),
    ("<b>spawn_goal tool</b>", "Any agent can call spawn_goal mid-execution to autonomously create a new goal. Used when the researcher discovers a complex fix that requires the full researcher → coder → integrator pipeline."),
    ("<b>Retry with failure context</b>", "Each retry injects the previous error into the agent's user message, forcing a different approach. Consecutive-error counter nudges the agent to submit with partial results after 3 consecutive failures."),
    ("<b>Self-heal loop</b>", "error_classifier.py detects developer-side bugs vs. external errors. On a developer bug: auto-files a GitHub issue on the omniBox repo, then spawns a fix goal (researcher → coder → integrator) to patch and PR the root cause."),
    ("<b>Tool idempotency</b>", "Every tool call is hashed (task_id + tool + args). Re-runs return the stored result — no duplicate Slack posts, no double PRs, crash-safe."),
    ("<b>Lease reclaim</b>", "Worker reclaims RUNNING tasks with expired leases every 30 s. Restart-resumable from any failure point."),
]
for title, desc in auto_feats:
    story.append(Paragraph(f'<font color="#0095ff">▸</font>  {title} — {desc}', sBullet))
    story.append(Spacer(1, 1*mm))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("LLM Layer & Fallback Chain", sH2))
story.append(Paragraph(
    "LiteLLM wraps all providers. Per-model fallback chains handle hard quota errors (daily limit, resource_exhausted) "
    "by trying the next candidate, and soft rate limits by sleeping the declared retry delay. "
    "Claude 4 models exclude the <font face='Courier' size='8'>temperature</font> parameter (API constraint). "
    "40 models pre-configured; any LiteLLM-compatible string also accepted at runtime.",
    sBody
))

story.append(PageBreak())

# ─────────────────────────────────────────────
# PAGE 3 — OVERALL WORKFLOW
# ─────────────────────────────────────────────
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Overall Workflow", sH1))
story.append(hr(BLUE, 1))

story.append(Paragraph(
    "omniBox follows a <b>plan → execute → observe</b> loop backed by SQLite WAL for full restart-resumability. "
    "Three asyncio workers run concurrently inside the FastAPI process — no separate queue or Redis needed.",
    sBody
))
story.append(Spacer(1, 3*mm))

# Workflow steps as a visual table
wf_data = [
    [Paragraph("<b>Step</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Component</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("<b>Detail</b>", S("TH", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN))],
    [Paragraph("1", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Goal Submission", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("POST /api/goals — inserts row with status=NEW, generates trace_id for Omium", sBody)],
    [Paragraph("2", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Orchestration", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("goal_planner_loop claims NEW goal → calls Claude → emits PlanSchema DAG → inserts task rows (deps=[] → READY, others → PENDING)", sBody)],
    [Paragraph("3", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Task Execution", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("task_executor_loop (Semaphore 5) claims READY tasks → resolves {{t1.output.field}} interpolations → runs agent_runner.run()", sBody)],
    [Paragraph("4", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Agent Loop", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("acompletion() loop: builds messages → calls LLM → for each tool_call checks idempotency → invokes tool → emits SSE events → repeats until submit_result", sBody)],
    [Paragraph("5", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Dependency Promotion", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("On DONE: promote_ready_tasks() SQL query unblocks tasks whose all deps are DONE → they become READY for the executor", sBody)],
    [Paragraph("6", S("N", fontName=DISPLAY, fontSize=11, textColor=BLUE, alignment=TA_CENTER)),
     Paragraph("Goal Completion", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("When terminal task completes → goal.status=COMPLETED, output stored, goal_done SSE event fires → frontend renders output", sBody)],
    [Paragraph("7", S("N", fontName=DISPLAY, fontSize=11, textColor=WARNING, alignment=TA_CENTER)),
     Paragraph("Failure Recovery", S("WS", fontName=DISPLAY, fontSize=9, textColor=TEXT_MAIN)),
     Paragraph("On max_attempts exceeded → try dynamic replan (one chance). On developer error → self-heal: file issue + spawn fix goal. On crash → reclaim_loop restores RUNNING tasks to READY", sBody)],
]
wf_tbl = Table(wf_data, colWidths=[10*mm, 36*mm, 126*mm])
wf_tbl.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  HexColor("#0d1827")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1), [HexColor("#0d0d12"), HexColor("#111118")]),
    ("GRID",          (0,0), (-1,-1), 0.4, CARD_EDGE),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("ALIGN",         (0,0), (0,-1),  "CENTER"),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("RIGHTPADDING",  (0,0), (-1,-1), 6),
    ("TOPPADDING",    (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
]))
story.append(wf_tbl)
story.append(Spacer(1, 4*mm))

# GitHub automation demo flow
story.append(Paragraph("Demo Flow — GitHub Issue → Auto-PR", sH2))
demo_steps = [
    ("GitHub issue opened", "Webhook fires → POST /api/webhooks/github → goal created automatically", BLUE),
    ("Orchestrator plans", "researcher → coder → integrator DAG emitted in < 2 s", PURPLE),
    ("Researcher agent", "github_list_dir explores repo, github_read_file reads relevant files, github_get_issue fetches bug details", CYAN),
    ("Coder agent", "Writes Python fix, executes via code_exec sandbox, captures real output", WARNING),
    ("Integrator agent", "github_pr commits fixed files, opens cross-repo PR with professional body, github_post_comment posts PR link on original issue", SUCCESS),
    ("Live dashboard", "Every tool call, message, and status transition streams via SSE to the React frontend in real time", TEXT_DIM),
]
demo_data = [[
    Paragraph(f'<font color="#{c.hexval()[2:]}">●</font>  <b>{t}</b>', sBullet),
    Paragraph(d, sBody),
] for t, d, c in demo_steps]
demo_tbl = Table(demo_data, colWidths=[52*mm, 120*mm])
demo_tbl.setStyle(TableStyle([
    ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ("LEFTPADDING",  (0,0), (-1,-1), 4),
    ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ("TOPPADDING",   (0,0), (-1,-1), 4),
    ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ("LINEBELOW",    (0,0), (-1,-2), 0.3, CARD_EDGE),
]))
story.append(demo_tbl)
story.append(Spacer(1, 4*mm))

# Tech stack summary
story.append(Paragraph("Technology Stack", sH2))
stack_data = [
    ["Backend",  "FastAPI · SQLite WAL · aiosqlite · LiteLLM · Pydantic v2"],
    ["LLMs",     "Groq (LLaMA 4 Maverick / LLaMA 3.3 70B) · Anthropic Claude · 40 models total"],
    ["Tools",    "Tavily search · PyGithub · httpx · asyncio subprocess (code_exec) · SSE (events.py)"],
    ["Frontend", "React 18 · TypeScript · Vite · Tailwind CSS · Framer Motion · React Flow · Mermaid.js"],
    ["Tracing",  "Omium SDK — goal_trace_context → orchestrator span → task spans → tool spans"],
    ["Auth",     "Firebase Auth (email + Google + GitHub OAuth)"],
]
for row in stack_data:
    story.append(Paragraph(
        f'<font color="#0095ff" face="Helvetica-Bold">{row[0]}</font>'
        f'<font color="#6b7280"> — </font>'
        f'<font color="#9ca3af">{row[1]}</font>',
        S("Stack", fontName=BODY, fontSize=8.5, textColor=TEXT_DIM, leading=14, spaceAfter=3)
    ))

story.append(Spacer(1, 4*mm))
story.append(hr(BLUE, 0.8))
story.append(Paragraph(
    "GitHub: <font color=\"#0095ff\">https://github.com/viscous106/omniBox</font>  ·  "
    "Built for Anvil MMXXVI — Multi-Agent Autonomy Track",
    S("Footer", fontName=BODY, fontSize=8.5, textColor=TEXT_MUTED, alignment=TA_CENTER, leading=14)
))

# ── Build ─────────────────────────────────────────────────────────
doc.build(story, onFirstPage=dark_page, onLaterPages=dark_page)
print("✓  omniBox_submission.pdf  written successfully")
