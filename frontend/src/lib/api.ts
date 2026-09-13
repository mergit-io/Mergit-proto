import { getCsrfToken } from "./auth";

const BASE = "/api";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method ?? "GET").toUpperCase();

  // The session cookie rides along because BASE is relative and the SPA is served
  // same-origin by the same FastAPI app. `same-origin` is fetch's default, but stating it
  // is worth the two words: if this ever moves to a separate origin, the silent failure
  // is "every request is anonymous" rather than an error anyone would notice.
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> | undefined),
  };

  // Unsafe methods carry the synchronizer token from GET /api/auth/me. A cross-site page
  // can make the browser send this request with the cookie, but cannot read that response
  // to learn the token.
  if (!SAFE_METHODS.has(method)) {
    headers["X-Mergit-CSRF"] = getCsrfToken();
  }

  const res = await fetch(`${BASE}${path}`, {
    // NOTE: options is spread FIRST, then headers/credentials override it. The original
    // spread `...options` last, so a caller passing `headers` silently dropped
    // Content-Type — dormant only because no caller did it yet.
    ...options,
    method: options?.method,
    credentials: "same-origin",
    headers,
  });

  if (!res.ok) {
    // Session gone (expired, revoked, or signed out in another tab). Bounce to login
    // rather than surfacing "401: {detail: ...}" in a toast the user cannot act on.
    if (res.status === 401 && !path.startsWith("/auth/")) {
      window.location.href = "/login?expired=1";
    }
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export interface GoalSummary {
  goal_id: string;
  title: string;
  status: string;
  created_at: number;
  updated_at: number;
}

export interface TaskDetail {
  id: string;
  goal_id: string;
  agent_name: string;
  description: string;
  status: string;
  inputs: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  attempt_count: number;
  wait_token: string | null;
  depends_on?: string[];
  created_at: number;
  updated_at: number;
}

export interface GoalDetail {
  goal_id: string;
  title: string;
  goal_text: string;
  status: string;
  output: Record<string, unknown> | null;
  error: string | null;
  plan: unknown;
  tasks: TaskDetail[];
  trace_id: string;
  created_at: number;
  updated_at: number;
}

export interface ProjectContext {
  github_repo: string;
  description: string;
  tech_stack: string;
  notes: string;
}

export interface ProviderKeyStatus {
  env_var: string;
  set: boolean;
  masked: string | null;
}

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  tier: string;
}

export interface ModelConfig {
  models: Record<string, string>;
  available: ModelOption[];
  defaults: Record<string, string>;
}

// Economy view-models — mirror the backend /api/economy/* responses exactly.
export interface Passport {
  role: string;
  did: string;
  token_id: number;
  soulbound: boolean;
  capabilities: string[];
  owner_address: string;
  minted_at: number;
  mint_block: number;
}

export interface RepEntry {
  role: string;
  composite: number;
  success_rate: number;
  speed: number;
  volume: number;
  badge: string;
  updated_at: number;
  rank?: number;
  token_id?: number;
  did?: string;
}

/** Queue state of a proof's on-chain submission. `null` = never enqueued. */
export type SubmissionStatus = "pending" | "submitting" | "confirmed" | "dead_lettered";

export interface Proof {
  task_id: string;
  goal_id: string;
  agent_role: string;
  result_hash: string;
  recorded_at: number;
  /** Position in the local ledger. An ordering key, not a block height. */
  sequence: number;
  submission_status: SubmissionStatus | null;
  /** Real chain values, and null until this proof is confirmed on chain. `tx_hash` stays
   *  null even when confirmed if the result was already recorded by an earlier tx. */
  tx_hash: string | null;
  block_number: number | null;
  chain_id: number | null;
}

export interface AgentDetail {
  passport: Passport;
  reputation: RepEntry | null;
  proofs: Proof[];
}

// ── On-chain proof layer ───────────────────────────────────────────────────────

export type ChainStatus = "ready" | "not_deployed" | "disabled" | "error";

export interface ChainStatusInfo {
  key: string;
  name: string;
  chainId: number;
  explorer: string | null;
  currency: string;
  isLocal: boolean;
  status: ChainStatus;
  contracts: Record<string, string>;
  sender: string | null;
  error: string | null;
  /** Submission queue depth by status: pending / submitting / confirmed / … */
  outbox: Record<string, number>;
}

/** Full audit trail for one task — every value needed to redo the check by hand. */
export interface ProofVerification {
  task_id: string;
  goal_id: string;
  agent_role: string;
  task_status: string;
  canonical_output: string;
  computed_hash: string;
  hash_algorithm: string;
  task_key_algorithm: string;
  onchain_hash: string | null;
  tx_hash: string | null;
  block_number: number | null;
  chain_id: number | null;
  explorer_url: string | null;
  /** true = matches chain, false = tampered, null = nothing on chain to compare against */
  verified: boolean | null;
  reason: string | null;
  submission_status?: string;
}

// ── Self-heal ──────────────────────────────────────────────────────────────────

export interface HealAttempt {
  id: string;
  fingerprint: string;
  goal_id: string;
  task_id: string | null;
  agent_name: string;
  error: string;
  error_summary: string;
  classification: string;
  status: string;
  issue_number: number | null;
  issue_url: string | null;
  issue_body: string | null;
  fix_goal_id: string | null;
  outcome: string | null;
  recurrence_count: number;
  created_at: number;
  updated_at: number;
}

export interface HealStats {
  total: number;
  recurrences: number;
  by_status: Record<string, number>;
  by_outcome: Record<string, number>;
  fixed: number;
}

export interface ChainInfo {
  chainId: number;
  network: string;
  explorer: string;
  contracts: Record<string, string>;
}

export const api = {
  submitGoal: (goal: string) =>
    request<{ goal_id: string; status: string; created_at: number }>("/goals", {
      method: "POST",
      body: JSON.stringify({ goal }),
    }),

  listGoals: (status?: string) =>
    request<{ goals: GoalSummary[]; total: number }>(
      `/goals${status ? `?status=${status}` : ""}`
    ),

  getGoal: (id: string) => request<GoalDetail>(`/goals/${id}`),

  triggerWebhook: (token: string, payload: unknown) =>
    request<{ ok: boolean; task_id: string }>(`/webhooks/${token}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getModelConfig: () => request<ModelConfig>("/config/models"),

  updateModelConfig: (models: Record<string, string>) =>
    request<{ models: Record<string, string>; ok: boolean }>("/config/models", {
      method: "PUT",
      body: JSON.stringify({ models }),
    }),

  getApiKeys: () =>
    request<Record<string, ProviderKeyStatus>>("/config/keys"),

  updateApiKey: (provider: string, key: string) =>
    request<{ ok: boolean; masked: string; resumed_tasks?: number }>("/config/keys", {
      method: "PUT",
      body: JSON.stringify({ provider, key }),
    }),

  getModelHealth: () =>
    request<{ unhealthy: Record<string, number>; all_healthy: boolean }>("/config/model-health"),

  getContext: () => request<ProjectContext>("/config/context"),

  updateContext: (ctx: ProjectContext) =>
    request<{ ok: boolean } & ProjectContext>("/config/context", {
      method: "PUT",
      body: JSON.stringify(ctx),
    }),

  getPassports: () => request<Passport[]>("/economy/passports"),

  getLeaderboard: () => request<RepEntry[]>("/economy/leaderboard"),

  getProofs: (limit = 50) => request<Proof[]>(`/economy/proofs?limit=${limit}`),

  getAgentDetail: (role: string) => request<AgentDetail>(`/economy/agents/${role}`),

  getChain: () => request<ChainInfo>("/economy/chain"),

  getChainStatus: () => request<ChainStatusInfo>("/economy/chain/status"),

  verifyProof: (taskId: string) =>
    request<ProofVerification>(`/economy/verify/${encodeURIComponent(taskId)}`),

  getHealAttempts: (limit = 100) => request<HealAttempt[]>(`/heal/attempts?limit=${limit}`),

  getHealStats: () => request<HealStats>("/heal/stats"),
};
