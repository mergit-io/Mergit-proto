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
};
