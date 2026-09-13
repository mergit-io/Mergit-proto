import { useState, useEffect, useCallback, useRef } from "react";
import { Check, Eye, EyeOff, Plus, X, ChevronDown } from "lucide-react";
import { Shell } from "../components/AppNav";
import { api } from "../lib/api";
import type { ModelConfig, ModelOption, ProviderKeyStatus, ProjectContext } from "../lib/api";
import { Micro, Panel, PageHead, Tabs, Notice, Loading } from "../components/ui";

// -- Role metadata

const ROLES = ["orchestrator", "researcher", "writer", "coder", "integrator"] as const;
type Role = (typeof ROLES)[number];

const ROLE_META: Record<Role, { label: string; desc: string }> = {
  orchestrator: { label: "Orchestrator", desc: "Plans the task DAG from your goal" },
  researcher:   { label: "Researcher",   desc: "Searches the web and gathers facts" },
  writer:       { label: "Writer",       desc: "Synthesises research into documents" },
  coder:        { label: "Coder",        desc: "Writes and executes Python code" },
  integrator:   { label: "Integrator",   desc: "Calls APIs and handles webhooks" },
};

// -- Provider detection

function detectProvider(modelId: string): string {
  const id = modelId.toLowerCase();
  if (id.startsWith("groq/")) return "Groq";
  if (id.startsWith("anthropic/")) return "Anthropic";
  return "Custom";
}

function ProviderBadge({ modelId }: { modelId: string }) {
  return <span className="font-mono text-micro uppercase text-dim border border-line px-1.5 py-0.5">{detectProvider(modelId)}</span>;
}

function TierTag({ tier }: { tier: string }) {
  const cls =
    tier === "powerful" ? "text-violet border-violet" :
    tier === "instant"  ? "text-mint border-mint" :
    "text-dim border-line";
  return <span className={`font-mono text-micro uppercase border px-1.5 py-0.5 ${cls}`}>{tier}</span>;
}

// -- Tabs

type Tab = "visual" | "json";

const VIEW_TABS = [
  { id: "visual", label: "Visual" },
  { id: "json", label: "JSON" },
] as const;

// -- Main page

const PROVIDER_LABEL: Record<string, string> = {
  groq: "Groq",
  anthropic: "Anthropic",
  tavily: "Tavily",
  github: "GitHub",
};

function ApiKeysSection() {
  const [keys, setKeys] = useState<Record<string, ProviderKeyStatus> | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [inputVal, setInputVal] = useState("");
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setKeys(await api.getApiKeys()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const startEdit = (provider: string) => {
    setEditing(provider);
    setInputVal("");
    setShow(false);
    setErr(null);
  };

  const save = async (provider: string) => {
    if (!inputVal.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      await api.updateApiKey(provider, inputVal.trim());
      setSavedKey(provider);
      setTimeout(() => setSavedKey(null), 2500);
      setEditing(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Key could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (!keys) return null;

  return (
    <Panel title="API keys" className="mt-6">
      <p className="px-4 pt-3 text-xs text-dim">Keys are saved to backend/.env and take effect immediately.</p>
      <ul className="mt-1">
        {Object.entries(keys).map(([provider, status]) => {
          const label = PROVIDER_LABEL[provider] ?? provider;
          const isEditing = editing === provider;
          const isSaved = savedKey === provider;

          return (
            <li key={provider} className="px-4 py-3 border-b border-line-soft last:border-0">
              <div className="flex items-center gap-3">
                <span className="font-mono text-micro uppercase text-dim w-24 shrink-0">{label}</span>
                <code className="text-xs text-faint font-mono flex-1">{status.env_var}</code>
                {status.set ? (
                  <span className="text-xs text-mint font-mono">{status.masked}</span>
                ) : (
                  <span className="text-xs text-dim font-mono">Not set</span>
                )}
                <button
                  onClick={() => (isEditing ? setEditing(null) : startEdit(provider))}
                  className="btn-ghost h-7 px-3"
                >
                  {isEditing ? "Cancel" : isSaved ? "Key saved" : status.set ? "Update" : "Add key"}
                </button>
              </div>

              {isEditing && (
                <div className="mt-3 flex items-center gap-2">
                  <div className="flex-1 flex items-center gap-2 border border-line px-3 h-9 focus-within:border-violet transition-colors duration-150">
                    <input
                      type={show ? "text" : "password"}
                      value={inputVal}
                      onChange={(e) => setInputVal(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") save(provider); if (e.key === "Escape") setEditing(null); }}
                      placeholder={`Paste your ${label} API key`}
                      autoFocus
                      className="flex-1 bg-transparent text-xs font-mono text-text outline-none"
                    />
                    <button onClick={() => setShow((s) => !s)} className="text-dim hover:text-text transition-colors" aria-label={show ? "Hide key" : "Show key"}>
                      {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  <button
                    onClick={() => save(provider)}
                    disabled={saving || !inputVal.trim()}
                    className="btn-primary"
                  >
                    {saving ? "Saving" : "Save key"}
                  </button>
                </div>
              )}
              {isEditing && err && <p className="mt-1.5 text-xs text-red">{err}</p>}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

const CONTEXT_FIELDS = [
  { key: "github_repo" as const, label: "GitHub repo", placeholder: "owner/repo", mono: true },
  { key: "description" as const, label: "Project description", placeholder: "What does this project do?", mono: false },
  { key: "tech_stack" as const, label: "Tech stack", placeholder: "e.g. Python, FastAPI, React, PostgreSQL", mono: false },
  { key: "notes" as const, label: "Notes for agents", placeholder: "Any special instructions, conventions, or context", mono: false },
];

function ProjectContextSection() {
  const EMPTY: ProjectContext = { github_repo: "", description: "", tech_stack: "", notes: "" };
  const [ctx, setCtx] = useState<ProjectContext>(EMPTY);
  const [draft, setDraft] = useState<ProjectContext>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const c = await api.getContext();
      setCtx(c);
      setDraft(c);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(ctx);

  const handleSave = async () => {
    setSaving(true);
    setErr(null);
    try {
      const res = await api.updateContext(draft);
      const saved = { github_repo: res.github_repo, description: res.description, tech_stack: res.tech_stack, notes: res.notes };
      setCtx(saved);
      setDraft(saved);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Changes could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel title="Project context" className="mt-6">
      <div className="p-4 space-y-4">
        <p className="text-xs text-dim -mt-1">
          Sent to the orchestrator and every agent, so they understand your project.
        </p>

        {CONTEXT_FIELDS.map(({ key, label, placeholder, mono }) => (
          <div key={key}>
            <Micro>{label}</Micro>
            {key === "notes" ? (
              <textarea
                value={draft[key]}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                placeholder={placeholder}
                rows={3}
                className="field mt-1.5 resize-none leading-relaxed"
              />
            ) : (
              <input
                type="text"
                value={draft[key]}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                placeholder={placeholder}
                className={`field mt-1.5 ${mono ? "font-mono" : ""}`}
              />
            )}
          </div>
        ))}

        {err && <Notice>{err}</Notice>}

        <div className="flex items-center justify-end gap-3 pt-1">
          {saved && <span className="micro text-mint">Changes saved</span>}
          <button onClick={handleSave} disabled={saving || !isDirty} className="btn-primary">
            {saving ? "Saving" : <><Check className="w-3.5 h-3.5" /> Save changes</>}
          </button>
        </div>
      </div>
    </Panel>
  );
}


export function Models() {
  const [config, setConfig]   = useState<ModelConfig | null>(null);
  const [draft, setDraft]     = useState<Record<string, string>>({});
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [tab, setTab]         = useState<Tab>("visual");
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  // Sync draft → jsonText when switching to JSON tab or draft changes
  useEffect(() => {
    if (tab === "json") {
      setJsonText(JSON.stringify(draft, null, 2));
      setJsonError(null);
    }
  }, [tab, draft]);

  const load = useCallback(async () => {
    try {
      const c = await api.getModelConfig();
      setConfig(c);
      setDraft(c.models);
      setJsonText(JSON.stringify(c.models, null, 2));
    } catch {
      setLoadErr("Model configuration could not be loaded. Refresh to try again.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);


  const handleJsonChange = (val: string) => {
    setJsonText(val);
    try {
      const parsed = JSON.parse(val);
      if (typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Must be a JSON object");
      for (const [k, v] of Object.entries(parsed)) {
        if (!ROLES.includes(k as Role)) throw new Error(`Unknown role: "${k}"`);
        if (typeof v !== "string" || !v.trim()) throw new Error(`Value for "${k}" must be a non-empty string`);
      }
      setDraft(parsed as Record<string, string>);
      setJsonError(null);
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : "Invalid JSON");
    }
  };

  const handleSave = async () => {
    if (jsonError) return;
    setSaving(true);
    setSaveErr(null);
    try {
      const res = await api.updateModelConfig(draft);
      setConfig((prev) => prev ? { ...prev, models: res.models } : prev);
      setDraft(res.models);
      setJsonText(JSON.stringify(res.models, null, 2));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : "Changes could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!config) return;
    setDraft(config.defaults);
    setJsonText(JSON.stringify(config.defaults, null, 2));
    setJsonError(null);
  };

  const isDirty = config && JSON.stringify(draft) !== JSON.stringify(config.models);

  return (
    <Shell>
      <PageHead marker="CONFIG — MODELS" title="Choose your AI models">
        Assign a model to each agent role. Changes take effect on the next goal execution.
      </PageHead>

      {loadErr && (
        <div className="mb-6">
          <Notice>{loadErr}</Notice>
        </div>
      )}

      <Panel
        title="Model roles"
        right={<Tabs value={tab} onChange={setTab} options={VIEW_TABS} />}
      >
        {tab === "visual" ? (
          !config ? (
            <Loading label="Loading roles" />
          ) : (
            <ul>
              {ROLES.map((role) => {
                const { label, desc } = ROLE_META[role];
                const value = draft[role] ?? config.defaults[role];
                return (
                  <li key={role} className="flex items-center gap-4 px-4 py-3 border-b border-line-soft last:border-0">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text">{label}</p>
                      <p className="text-xs text-dim truncate">{desc}</p>
                    </div>
                    <ModelPicker
                      value={value}
                      options={config.available}
                      onChange={(v) => setDraft((d) => ({ ...d, [role]: v }))}
                    />
                  </li>
                );
              })}
            </ul>
          )
        ) : (
          <div className="p-4">
            <p className="text-xs text-dim mb-3">
              Edit the role-to-model mapping directly. Use any LiteLLM-compatible model ID, e.g.{" "}
              <code className="font-mono text-violet">groq/llama-3.3-70b-versatile</code> or{" "}
              <code className="font-mono text-violet">anthropic/claude-sonnet-4-6</code>.
            </p>

            <div className={`flex border ${jsonError ? "border-red" : "border-line"}`}>
              <LineNumbers text={jsonText} />
              <textarea
                value={jsonText}
                onChange={(e) => handleJsonChange(e.target.value)}
                spellCheck={false}
                className="flex-1 bg-transparent text-sm font-mono text-text p-4 resize-none outline-none leading-6 min-h-[280px]"
                style={{ tabSize: 2 }}
              />
            </div>

            {jsonError && (
              <div className="mt-2">
                <Notice>{jsonError}</Notice>
              </div>
            )}

            <div className="mt-4 border border-line-soft p-4">
              <Micro>Available roles</Micro>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {ROLES.map((r) => (
                  <span key={r} className="px-2 py-0.5 border border-line text-xs text-dim font-mono">
                    {r}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-4 py-3 border-t border-line flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={handleReset}
              disabled={!config}
              className="btn-ghost"
            >
              Reset to defaults
            </button>
            {saveErr && <span className="text-xs text-red">{saveErr}</span>}
            {saved && <span className="micro text-mint">Changes saved</span>}
          </div>

          <button
            onClick={handleSave}
            disabled={saving || !isDirty || !!jsonError}
            className="btn-primary"
          >
            {saving ? "Saving" : <><Check className="w-3.5 h-3.5" /> Save changes</>}
          </button>
        </div>
      </Panel>

      <ApiKeysSection />

      <ProjectContextSection />

      {config && (
        <Panel title="Available models" className="mt-6">
          <p className="px-4 pt-3 pb-1 text-xs text-dim">Suggested models — any LiteLLM-compatible ID also works.</p>
          <table className="dtable mt-2">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model ID</th>
                <th>Label</th>
                <th className="text-right">Tier</th>
              </tr>
            </thead>
            <tbody>
              {config.available.map((m) => (
                <tr key={m.id}>
                  <td><ProviderBadge modelId={m.id} /></td>
                  <td className="font-mono text-xs">{m.id}</td>
                  <td className="text-xs text-dim">{m.label}</td>
                  <td className="text-right"><TierTag tier={m.tier} /></td>
                </tr>
              ))}
              <tr>
                <td><span className="font-mono text-micro uppercase text-dim border border-line px-1.5 py-0.5">Custom</span></td>
                <td className="font-mono text-xs text-dim">provider/model-name</td>
                <td className="text-xs text-dim">Any LiteLLM-compatible provider</td>
                <td className="text-right"><TierTag tier="any" /></td>
              </tr>
            </tbody>
          </table>
        </Panel>
      )}
    </Shell>
  );
}

// -- ModelPicker

function ModelPicker({
  value,
  options,
  onChange,
}: {
  value: string;
  options: ModelOption[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen]         = useState(false);
  const [custom, setCustom]     = useState(false);
  const [customVal, setCustomVal] = useState("");
  const inputRef                = useRef<HTMLInputElement>(null);

  const knownOption = options.find((o) => o.id === value);
  const isCustom    = !knownOption;

  useEffect(() => {
    if (isCustom && !custom) setCustomVal(value);
  }, [value, isCustom, custom]);

  const commit = (v: string) => {
    if (v.trim()) onChange(v.trim());
    setCustom(false);
    setOpen(false);
  };

  if (custom) {
    return (
      <div className="flex items-center gap-1.5 min-w-[220px]">
        <input
          ref={inputRef}
          autoFocus
          value={customVal}
          onChange={(e) => setCustomVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(customVal);
            if (e.key === "Escape") { setCustom(false); setCustomVal(""); }
          }}
          placeholder="provider/model-id"
          className="field flex-1 h-9 font-mono text-xs"
        />
        <button onClick={() => commit(customVal)} className="btn-ghost h-9 w-9 px-0" aria-label="Confirm model">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button onClick={() => { setCustom(false); setCustomVal(""); }} className="btn-ghost h-9 w-9 px-0" aria-label="Cancel">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 pl-3 pr-2 h-9 border border-line hover:border-faint text-xs text-text transition-colors duration-150 min-w-[200px]"
      >
        <span className="font-mono text-text truncate max-w-[130px]">
          {knownOption ? knownOption.label : value}
        </span>
        <ProviderBadge modelId={value} />
        <ChevronDown className="w-3 h-3 text-dim ml-auto shrink-0" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1.5 z-20 w-64 border border-line bg-slab overflow-y-auto max-h-72">
            {/* Group by provider */}
            {["Groq", "Anthropic", "OpenAI", "Google", "Mistral"].map((prov) => {
              const group = options.filter((o) => o.provider === prov);
              if (!group.length) return null;
              return (
                <div key={prov}>
                  <p className="px-3 pt-2.5 pb-1 micro">{prov}</p>
                  {group.map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => { onChange(opt.id); setOpen(false); }}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-raise transition-colors text-left ${opt.id === value ? "bg-raise" : ""}`}
                    >
                      <span className="font-medium font-mono text-text flex-1 truncate">{opt.label}</span>
                      <TierTag tier={opt.tier} />
                      {opt.id === value && <Check className="w-3 h-3 text-violet shrink-0" />}
                    </button>
                  ))}
                </div>
              );
            })}

            {/* Custom entry */}
            <div className="border-t border-line-soft p-2">
              <button
                onClick={() => { setOpen(false); setCustomVal(isCustom ? value : ""); setCustom(true); setTimeout(() => inputRef.current?.focus(), 50); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-dim hover:text-text hover:bg-raise transition-colors text-left"
              >
                <Plus className="w-3.5 h-3.5" />
                Custom model ID
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// -- Line numbers for JSON editor

function LineNumbers({ text }: { text: string }) {
  const lines = text.split("\n").length;
  return (
    <div className="select-none bg-raise text-right pr-3 pl-4 py-4 text-faint font-mono text-sm leading-6 border-r border-line min-w-[3rem]">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  );
}
