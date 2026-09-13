# omniBox — Architecture

## System Overview

```mermaid
flowchart TD
    User(["👤 User / GitHub Webhook"])

    subgraph Frontend ["Frontend — React + Vite :3000"]
        Landing["Landing Page\n/"]
        Dashboard["Dashboard\n/app"]
        GoalDetail["Goal Detail\n/app/goals/:id"]
        Models["Models Config\n/app/models"]
        Automate["GitHub Automation\n/app/webhooks"]
        Actions["Actions & Rulesets\n/app/actions"]
        SSEHook["useSSE() hook\nEventSource auto-reconnect"]
    end

    subgraph API ["FastAPI — :8000"]
        GoalsAPI["POST /api/goals\nGET  /api/goals\nGET  /api/goals/:id"]
        StreamAPI["GET /api/goals/:id/stream\nSSE event stream"]
        WebhookAPI["POST /api/webhooks/github\nGitHub event receiver"]
        ModelsAPI["GET/PUT /api/config/models\nGET/PUT /api/config/keys"]
        ActionsAPI["GET /api/actions/workflows\nGET /api/actions/protection\nPOST /api/actions/goal"]
    end

    subgraph Worker ["asyncio Worker Loops"]
        Planner["goal_planner_loop\npoll NEW goals"]
        Executor["task_executor_loop\npoll READY tasks\nSemaphore(5)"]
        Reclaim["reclaim_loop\nevery 30s — restore stale leases"]
    end

    subgraph Orchestrator ["Orchestrator — orchestrator.py"]
        Claude["LLM Call\nGroq / Claude"]
        PlanSchema["PlanSchema\ntasks DAG + terminal"]
        Validate["_validate_plan()\n_auto_fill_deps()"]
    end

    subgraph AgentRunner ["Agent Runner — agent_runner.py"]
        Loop["Tool-call loop\nacompletion()"]
        Idempotency["Idempotency check\nSHA256 hash → tool_calls table"]
        ToolInvoke["Tool invocation"]
        SubmitResult["submit_result\n→ task DONE"]
    end

    subgraph Agents ["Specialist Agents"]
        Researcher["🔍 Researcher\nGroq LLaMA 4 Maverick\nweb_search · github_*\nspawn_goal"]
        Writer["✍️ Writer\nGroq LLaMA 3.3 70B\nfile_ops"]
        Coder["💻 Coder\nGroq LLaMA 3.3 70B\ncode_exec · file_ops\ngithub_read_file"]
        Integrator["🔗 Integrator\nGroq LLaMA 3.3 70B\ngithub_pr · github_post_comment\ngithub_create_repo\ngithub_set_branch_protection\nwait_webhook · spawn_goal"]
    end

    subgraph Tools ["Tool Layer — tools/"]
        WebSearch["web_search\nTavily → DuckDuckGo fallback"]
        HttpReq["http_request\nhttpx"]
        GithubOps["github_ops\nread_file · list_dir · get_issue\npost_comment · search_code\nlist_workflows · get/set protection"]
        GithubPR["github_pr\nPyGithub — fork if no push access"]
        CodeExec["code_exec\nasyncio subprocess 30s"]
        FileOps["file_ops\nworkspace/{goal_id}/ scoped"]
        SpawnGoal["spawn_goal\ncreates sub-goal autonomously"]
        WaitWebhook["wait_webhook\nsuspends to WAITING_WEBHOOK"]
    end

    subgraph DB ["SQLite WAL — omnibox.db"]
        Goals[("goals\nid · status · plan_json\nterminal_task_id · trace_id")]
        Tasks[("tasks\nid · agent_name · inputs\ndepends_on · status\nattempt_count · lease_expires_at")]
        Messages[("messages\nrole · content · sequence")]
        ToolCalls[("tool_calls\ntool_name · args_hash\nresult_json · status")]
    end

    subgraph Resilience ["Resilience & Autonomy"]
        Replanner["Dynamic Replanner\nreplanner.py\nalternative plan on failure"]
        SelfHeal["Self-Heal\nself_heal.py\nauto-file issue + spawn fix goal"]
        ErrClass["Error Classifier\nerror_classifier.py\ndev bug vs external error"]
    end

    subgraph LLM ["LLM Layer — llm.py + LiteLLM"]
        FallbackChain["Provider Fallback Chain\nGroq → Anthropic"]
        SoftLimit["Soft rate limit\nsleep retry-delay"]
        HardLimit["Hard quota\ntry next model"]
    end

    subgraph Tracing ["Tracing — Omium SDK"]
        GoalTrace["goal_trace_context\nexecution_id = trace_id"]
        OrchestratorSpan["orchestrator span"]
        TaskSpan["task spans"]
        ToolSpan["tool spans"]
    end

    User -->|"submit goal / webhook"| API
    Dashboard -->|"POST /api/goals"| GoalsAPI
    GoalDetail --> SSEHook --> StreamAPI
    Models --> ModelsAPI
    Automate --> WebhookAPI
    Actions --> ActionsAPI

    GoalsAPI --> DB
    WebhookAPI -->|"auto-create goal"| DB

    Planner -->|"claim NEW"| Goals
    Planner --> Orchestrator
    Orchestrator --> Claude --> PlanSchema --> Validate
    Validate -->|"insert tasks"| Tasks

    Executor -->|"claim READY"| Tasks
    Executor --> AgentRunner
    AgentRunner --> Loop --> Idempotency --> ToolInvoke --> SubmitResult
    SubmitResult -->|"DONE + output"| Tasks

    Loop --> Agents
    Researcher & Writer & Coder & Integrator --> Tools

    Tools --> DB
    Tools --> GithubOps & GithubPR & WebSearch & CodeExec

    Tasks -->|"promote deps"| Tasks
    Tasks -->|"terminal DONE"| Goals

    Goals & Tasks & Messages & ToolCalls --> DB

    AgentRunner -->|"emit SSE events"| StreamAPI

    Executor -->|"failure at max_attempts"| ErrClass
    ErrClass -->|"dev bug"| SelfHeal
    ErrClass -->|"any failure"| Replanner

    LLM --> FallbackChain --> SoftLimit & HardLimit

    Tracing --> GoalTrace --> OrchestratorSpan --> TaskSpan --> ToolSpan
```

---

## Request Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant DB as SQLite
    participant W as Worker
    participant O as Orchestrator
    participant AR as AgentRunner
    participant T as Tools
    participant GH as GitHub

    U->>API: POST /api/goals {"goal": "..."}
    API->>DB: INSERT goal (status=NEW)
    API-->>U: 202 {goal_id}

    W->>DB: claim NEW goal
    W->>O: plan(goal)
    O->>O: Claude → PlanSchema DAG
    O->>DB: INSERT tasks (READY / PENDING)
    DB-->>W: goal status=RUNNING
    W-->>U: SSE goal_status RUNNING

    loop For each READY task
        W->>DB: claim READY task (atomic UPDATE)
        W->>AR: run(task, resolved_inputs)
        AR->>AR: build messages (system+user+retry context)
        loop Tool-call loop
            AR->>AR: acompletion() → tool_calls
            AR->>DB: idempotency check
            AR->>T: invoke tool
            T->>GH: github API / web / code_exec
            GH-->>T: result
            T-->>AR: result
            AR->>DB: store tool result
            AR-->>U: SSE tool_call + tool_result
        end
        AR->>DB: submit_result → task DONE
        AR-->>U: SSE task_done
        W->>DB: promote_ready_tasks()
    end

    W->>DB: terminal task DONE → goal COMPLETED
    W-->>U: SSE goal_done + output
```

---

## GitHub Automation Pipeline

```mermaid
flowchart LR
    Issue(["GitHub Issue\nopened"])
    Webhook["POST /api/webhooks/github\ngithub_webhook.py"]
    Goal["Goal created\nauto: Fix issue #N in owner/repo"]

    subgraph R ["Task 1 — Researcher"]
        R1["github_list_dir\nexplore repo structure"]
        R2["github_get_issue\nfetch bug details"]
        R3["github_read_file\nread relevant source files"]
        R4["github_search_code\nfind affected functions"]
        R1 --> R2 --> R3 --> R4
    end

    subgraph C ["Task 2 — Coder"]
        C1["Receive code_context\nfrom researcher output"]
        C2["Write fix in Python"]
        C3["code_exec\nrun + verify output"]
        C1 --> C2 --> C3
    end

    subgraph I ["Task 3 — Integrator"]
        I1["github_pr\ncommit fixed files\nopen PR with pro body"]
        I2["github_post_comment\npost PR link on issue"]
        I1 --> I2
    end

    PR(["✅ Pull Request\nopened on GitHub"])
    Comment(["💬 Comment posted\non original issue"])

    Issue --> Webhook --> Goal --> R --> C --> I --> PR
    I --> Comment
```

---

## Agent Registry

| Agent | Model | Tools | Output |
|-------|-------|-------|--------|
| **researcher** | `groq/meta-llama/llama-4-maverick-17b-128e-instruct` | web_search, http_request, github_read_file, github_list_dir, github_get_issue, github_search_code, github_list_workflows, github_get_branch_protection, spawn_goal | `{summary, key_points, sources, code_context}` |
| **writer** | `groq/llama-3.3-70b-versatile` | file_ops | `{text, title}` |
| **coder** | `groq/llama-3.3-70b-versatile` | code_exec, file_ops, web_search, github_read_file | `{code, output, success}` |
| **integrator** | `groq/llama-3.3-70b-versatile` | github_pr, github_post_comment, github_read_file, github_create_repo, github_list_workflows, github_get_branch_protection, github_set_branch_protection, http_request, wait_webhook, spawn_goal | `{action, result, url}` |

---

## Database Schema

```mermaid
erDiagram
    goals {
        TEXT id PK
        TEXT title
        TEXT goal_text
        TEXT status
        TEXT output
        TEXT error
        TEXT plan_json
        TEXT terminal_task_id FK
        TEXT trace_id
        INTEGER created_at
        INTEGER updated_at
    }
    tasks {
        TEXT id PK
        TEXT goal_id FK
        TEXT agent_name
        TEXT description
        TEXT inputs
        TEXT depends_on
        TEXT status
        TEXT output
        TEXT error
        INTEGER attempt_count
        INTEGER max_attempts
        TEXT worker_id
        INTEGER lease_expires_at
        TEXT wait_token
        TEXT trace_id
    }
    messages {
        TEXT id PK
        TEXT task_id FK
        TEXT role
        TEXT content
        TEXT tool_call_id
        INTEGER sequence
    }
    tool_calls {
        TEXT id PK
        TEXT task_id FK
        TEXT tool_name
        TEXT args_json
        TEXT args_hash
        TEXT result_json
        TEXT status
        TEXT idempotency_key
    }

    goals ||--o{ tasks : "has"
    tasks ||--o{ messages : "has"
    tasks ||--o{ tool_calls : "has"
```

---

## Autonomy & Resilience

```mermaid
flowchart TD
    TaskFail["Task fails\nat max_attempts"]

    ErrClass{"error_classifier\ndev bug?"}
    Replan["replanner.attempt_replan()\nOrchestrator called with\nfailed context + completed tasks\n→ new task sub-graph inserted"]
    SelfHeal["self_heal.trigger()\n1. File GitHub issue on omniBox repo\n2. Spawn fix goal:\n   researcher→coder→integrator"]

    ReplanOK{"Replan\nsucceeded?"}
    GoalFail["Goal FAILED"]
    GoalContinues["Goal continues\nwith new tasks"]
    FixGoal["New autonomous goal:\nfix the developer bug\nand open a PR"]

    TaskFail --> ErrClass
    ErrClass -->|"yes — our code"| SelfHeal
    ErrClass -->|"any failure"| Replan
    Replan --> ReplanOK
    ReplanOK -->|"yes"| GoalContinues
    ReplanOK -->|"no"| GoalFail
    SelfHeal --> FixGoal

    SpawnGoal["Agent calls spawn_goal tool\nmid-execution"]
    SubGoal["New autonomous sub-goal\ncreated in DB\nexecuted independently"]
    SpawnGoal --> SubGoal
```

---

## File Structure

```
omniBox/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, router registration
│   ├── config.py                # pydantic-settings, .env loading
│   ├── db.py                    # SQLite WAL, schema DDL, all async queries
│   ├── models.py                # Pydantic request/response schemas
│   ├── state.py                 # GoalRow, TaskRow dataclasses
│   ├── orchestrator.py          # LLM → PlanSchema, _validate_plan, replanning
│   ├── worker.py                # 3 asyncio loops: planner, executor, reclaim
│   ├── agent_registry.py        # AGENT_REGISTRY, get_agent_config()
│   ├── agent_runner.py          # Generic tool-call loop, idempotency, retry context
│   ├── llm.py                   # LiteLLM acompletion, fallback chains
│   ├── interpolation.py         # {{task_id.output.field[0]}} resolver
│   ├── model_config.py          # Per-role model store, model_config.json
│   ├── error_classifier.py      # Dev bug vs external error detection
│   ├── replanner.py             # Dynamic replan on task failure
│   ├── self_heal.py             # Auto-file issue + spawn fix goal
│   ├── events.py                # asyncio.Queue per goal for SSE
│   ├── tracing.py               # Omium SDK wrappers, no-op fallback
│   ├── context.py               # Per-goal context store
│   ├── tools/
│   │   ├── __init__.py          # TOOL_REGISTRY
│   │   ├── web_search.py        # Tavily + DuckDuckGo fallback
│   │   ├── http_request.py      # httpx outbound
│   │   ├── file_ops.py          # workspace-scoped file I/O
│   │   ├── github_pr.py         # PyGithub PR creation, auto-fork
│   │   ├── github_ops.py        # read_file, list_dir, get_issue, post_comment,
│   │   │                        # search_code, list_workflows, get/set protection
│   │   ├── code_exec.py         # asyncio subprocess, 30s timeout
│   │   ├── spawn_goal.py        # agent-initiated sub-goal creation
│   │   └── wait_webhook.py      # suspend task to WAITING_WEBHOOK
│   └── api/
│       ├── goals.py             # CRUD for goals
│       ├── tasks.py             # task detail endpoints
│       ├── stream.py            # SSE /goals/:id/stream
│       ├── webhooks.py          # /webhooks/:token resume
│       ├── github_webhook.py    # /webhooks/github receiver
│       ├── actions.py           # /actions/* — workflows + protection + goal
│       ├── keys.py              # /config/keys — API key management
│       └── health.py            # /health
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── Landing.tsx      # Public marketing page
    │   │   ├── Login.tsx        # Firebase auth (email + OAuth)
    │   │   ├── Dashboard.tsx    # Goal list + submission
    │   │   ├── GoalDetail.tsx   # DAG + task panels + live log + output
    │   │   ├── Models.tsx       # Model config + API keys
    │   │   ├── Webhooks.tsx     # GitHub Automation setup + simulator
    │   │   └── Actions.tsx      # CI/CD workflows + branch protection
    │   ├── components/
    │   │   ├── AppNav.tsx       # Sticky nav bar for /app pages
    │   │   ├── AppBackground.tsx # Shared dot-grid + ambient orb background
    │   │   ├── GoalInput.tsx    # Animated placeholder textarea
    │   │   ├── GoalCard.tsx     # Goal row with status + live glow
    │   │   ├── TaskDAG.tsx      # React Flow DAG visualization
    │   │   ├── TaskPanel.tsx    # Expandable task detail (messages, tools)
    │   │   ├── StatusBadge.tsx  # Animated status pill
    │   │   ├── AgentBadge.tsx   # Colored agent type pill
    │   │   ├── LiveLog.tsx      # SSE event feed (monospace scroll)
    │   │   ├── OutputDisplay.tsx # Markdown + Mermaid diagram renderer
    │   │   └── ModelErrorBanner.tsx # Modal on quota/key errors
    │   └── lib/
    │       ├── api.ts           # fetch wrappers for all endpoints
    │       ├── sse.ts           # useSSE() EventSource hook
    │       └── firebase.ts      # Firebase app + auth providers
    └── tailwind.config.js       # Design tokens: colors, fonts, shadows
```
