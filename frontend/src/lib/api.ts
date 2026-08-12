const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
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

export interface Proof {
  task_id: string;
  goal_id: string;
  agent_role: string;
  result_hash: string;
  tx_hash: string;
  block_number: number;
  recorded_at: number;
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
