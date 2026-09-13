import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check, RotateCcw, Save, Cpu, FlaskConical, PenLine,
  Bell, Code2, Plug, Settings2, ChevronDown, AlertCircle,
  Layers, FileJson, Plus, X, Key, Eye, EyeOff, CheckCircle,
  FolderGit2,
} from "lucide-react";
import { AppNav } from "../components/AppNav";
import { AppBackground } from "../components/AppBackground";
import { api } from "../lib/api";
import type { ModelConfig, ModelOption, ProviderKeyStatus, ProjectContext } from "../lib/api";

// -- Role metadata

const ROLES = ["orchestrator", "researcher", "writer", "coder", "integrator"] as const;
type Role = (typeof ROLES)[number];

const ROLE_META: Record<Role, { label: string; desc: string; Icon: React.ComponentType<{ className?: string }> }> = {
  orchestrator: { label: "Orchestrator", desc: "Plans the task DAG from your goal",         Icon: Settings2    },
  researcher:   { label: "Researcher",   desc: "Searches the web and gathers facts",         Icon: FlaskConical },
  writer:       { label: "Writer",       desc: "Synthesises research into documents",         Icon: PenLine      },
  coder:        { label: "Coder",        desc: "Writes and executes Python code",             Icon: Code2        },
  integrator:   { label: "Integrator",   desc: "Calls APIs and handles webhooks",             Icon: Plug         },
};

// -- Provider detection

function detectProvider(modelId: string): { name: string; color: string; bg: string } {
  const id = modelId.toLowerCase();
  if (id.startsWith("groq/"))      return { name: "Groq",      color: "text-emerald-400", bg: "bg-emerald-400/10 border-emerald-400/20" };
  if (id.startsWith("anthropic/")) return { name: "Anthropic", color: "text-violet-400",  bg: "bg-violet-400/10 border-violet-400/20"  };
  return                                   { name: "Custom",   color: "text-white",        bg: "bg-white/6 border-white/10"             };
}

function ProviderBadge({ modelId }: { modelId: string }) {
  const p = detectProvider(modelId);
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${p.bg} ${p.color}`}>
      {p.name}
    </span>
  );
}

// -- Tabs

type Tab = "visual" | "json";

// -- Main page

const PROVIDER_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  groq:      { label: "Groq",      color: "text-emerald-400", bg: "bg-emerald-400/8",  border: "border-emerald-400/20" },
  anthropic: { label: "Anthropic", color: "text-violet-400",  bg: "bg-violet-400/8",   border: "border-violet-400/20"  },
  tavily:    { label: "Tavily",    color: "text-cyan-400",    bg: "bg-cyan-400/8",      border: "border-cyan-400/20"    },
  github:    { label: "GitHub",    color: "text-white",       bg: "bg-white/8",         border: "border-white/20"       },
  omium:     { label: "Omium",     color: "text-violet-400",  bg: "bg-violet-400/8",    border: "border-violet-400/20"  },
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
      setErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!keys) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="mt-6 rounded-2xl border border-white/10 bg-[#0e0e0e] overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-white/6 flex items-center gap-3">
        <Key className="w-4 h-4 text-text-muted" />
        <div>
          <h2 className="text-xs font-semibold text-white uppercase tracking-widest">API Keys</h2>
          <p className="text-[11px] text-text-muted mt-0.5">Keys are saved to backend/.env and take effect immediately</p>
        </div>
      </div>

      <div className="divide-y divide-white/4">
        {Object.entries(keys).map(([provider, status]) => {
          const meta = PROVIDER_META[provider] ?? { label: provider, color: "text-white", bg: "bg-white/6", border: "border-white/10" };
          const isEditing = editing === provider;
          const isSaved = savedKey === provider;

          return (
            <div key={provider} className="px-6 py-3">
              <div className="flex items-center gap-3">
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold border ${meta.bg} ${meta.border} ${meta.color} min-w-[70px] justify-center`}>
                  {meta.label}
                </span>
                <code className="text-[11px] text-text-muted font-mono flex-1">{status.env_var}</code>
                {status.set ? (
                  <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                    <CheckCircle className="w-3 h-3" />
                    {status.masked}
                  </span>
                ) : (
                  <span className="text-[11px] text-danger/70">Not set</span>
                )}
                <button
                  onClick={() => isEditing ? setEditing(null) : startEdit(provider)}
                  className="text-[11px] px-2.5 py-1 rounded-lg border border-white/10 text-text-muted hover:text-white hover:border-white/20 transition-all"
                >
                  {isEditing ? "Cancel" : isSaved ? "Saved ✓" : status.set ? "Update" : "Add key"}
                </button>
              </div>

              <AnimatePresence>
                {isEditing && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-3 overflow-hidden"
                  >
                    <div className="flex items-center gap-2">
                      <div className="flex-1 flex items-center gap-2 rounded-xl border border-white/12 bg-white/3 px-3 py-2">
                        <input
                          type={show ? "text" : "password"}
                          value={inputVal}
                          onChange={(e) => setInputVal(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") save(provider); if (e.key === "Escape") setEditing(null); }}
                          placeholder={`Paste your ${meta.label} API key…`}
                          autoFocus
                          className="flex-1 bg-transparent text-xs text-white font-mono outline-none placeholder:text-text-muted"
                        />
                        <button onClick={() => setShow((s) => !s)} className="text-text-muted hover:text-white transition-colors">
                          {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      <button
                        onClick={() => save(provider)}
                        disabled={saving || !inputVal.trim()}
                        className="px-4 py-2 rounded-xl text-xs font-semibold bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                      >
                        {saving ? "Saving…" : "Save"}
                      </button>
                    </div>
                    {err && <p className="mt-1.5 text-xs text-danger">{err}</p>}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

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
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="mt-6 rounded-2xl border border-white/10 bg-[#0e0e0e] overflow-hidden"
    >
      <div className="px-6 py-4 border-b border-white/6 flex items-center gap-3">
        <FolderGit2 className="w-4 h-4 text-text-muted" />
        <div>
          <h2 className="text-xs font-semibold text-white uppercase tracking-widest">Project Context</h2>
          <p className="text-[11px] text-text-muted mt-0.5">
            Injected into the orchestrator and every agent so they understand your project
          </p>
        </div>
      </div>

      <div className="p-6 space-y-4">
        {[
          { key: "github_repo" as const, label: "GitHub Repo", placeholder: "owner/repo", mono: true },
          { key: "description" as const, label: "Project Description", placeholder: "What does this project do?", mono: false },
          { key: "tech_stack" as const, label: "Tech Stack", placeholder: "e.g. Python, FastAPI, React, PostgreSQL", mono: false },
          { key: "notes" as const, label: "Notes for Agents", placeholder: "Any special instructions, conventions, or context…", mono: false },
        ].map(({ key, label, placeholder, mono }) => (
          <div key={key}>
            <label className="block text-[11px] font-medium text-text-muted mb-1.5 uppercase tracking-widest">
              {label}
            </label>
            {key === "notes" ? (
              <textarea
                value={draft[key]}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                placeholder={placeholder}
                rows={3}
                className="w-full bg-white/3 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white outline-none focus:border-accent/50 placeholder:text-text-muted resize-none font-sans leading-relaxed"
              />
            ) : (
              <input
                type="text"
                value={draft[key]}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                placeholder={placeholder}
                className={`w-full bg-white/3 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white outline-none focus:border-accent/50 placeholder:text-text-muted ${mono ? "font-mono" : "font-sans"}`}
              />
            )}
          </div>
        ))}

        {err && (
          <p className="flex items-center gap-1.5 text-xs text-danger">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {err}
          </p>
        )}

        <div className="flex justify-end pt-1">
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-semibold transition-all ${
              saved
                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                : isDirty
                ? "bg-accent text-white hover:bg-accent/90 shadow-[0_0_16px_rgba(59,130,246,0.3)]"
                : "bg-white/6 text-text-muted cursor-not-allowed"
            }`}
          >
            {saved ? (
              <><Check className="w-3.5 h-3.5" /> Saved</>
            ) : saving ? "Saving…" : (
              <><Save className="w-3.5 h-3.5" /> Save context</>
            )}
          </button>
        </div>
      </div>
    </motion.div>
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
      setLoadErr("Failed to load model configuration.");
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
      setSaveErr(e instanceof Error ? e.message : "Save failed");
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
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AppBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
      <AppNav />

      <main className="flex-1 max-w-4xl mx-auto w-full px-6 py-10">

        {/* Page header */}
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="mb-10"
        >
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-accent/25 bg-accent/8 mb-4">
            <Cpu className="w-3.5 h-3.5 text-accent" />
            <span className="text-xs font-medium text-accent">Model Configuration</span>
          </div>
          <h1 className="font-display font-bold text-white mb-3" style={{ fontSize: "clamp(1.8rem, 4vw, 2.6rem)" }}>
            Choose your{" "}
            <span className="text-gradient-blue">AI models</span>
          </h1>
          <p className="text-text-dim text-sm max-w-xl leading-relaxed">
            Assign any LLM to each agent role. Changes take effect on the next goal execution.
          </p>
        </motion.div>

        {loadErr && (
          <div className="mb-6 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-danger shrink-0" />
            <p className="text-sm text-red-400">{loadErr}</p>
          </div>
        )}


        {/* Main card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="rounded-2xl border border-white/10 bg-[#0e0e0e] overflow-hidden"
        >
          {/* Tab bar */}
          <div className="flex items-center gap-0 border-b border-white/8 px-6 pt-4">
            {([ ["visual", Layers, "Visual Editor"], ["json", FileJson, "JSON Editor"] ] as const).map(([id, Icon, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-lg border-b-2 transition-all -mb-px ${
                  tab === id
                    ? "border-accent text-accent bg-accent/5"
                    : "border-transparent text-text-muted hover:text-white"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          {/* Tab body */}
          <AnimatePresence mode="wait">
            {tab === "visual" ? (
              <motion.div
                key="visual"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                transition={{ duration: 0.15 }}
                className="p-6 space-y-3"
              >
                {!config ? (
                  <div className="py-12 text-center text-text-muted text-sm">Loading…</div>
                ) : (
                  ROLES.map((role, i) => {
                    const { label, desc, Icon } = ROLE_META[role];
                    const value = draft[role] ?? config.defaults[role];
                    return (
                      <motion.div
                        key={role}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.04 }}
                        className="flex items-center gap-4 p-4 rounded-xl border bg-white/3 border-white/6 hover:border-white/10 transition-all"
                      >
                        <div className="w-9 h-9 rounded-xl border bg-white/6 border-white/8 flex items-center justify-center shrink-0">
                          <Icon className="w-4 h-4 text-text-muted" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white">{label}</p>
                          <p className="text-[11px] text-text-muted truncate">{desc}</p>
                        </div>
                        <ModelPicker
                          value={value}
                          options={config.available}
                          onChange={(v) => setDraft((d) => ({ ...d, [role]: v }))}
                        />
                      </motion.div>
                    );
                  })
                )}
              </motion.div>
            ) : (
              <motion.div
                key="json"
                initial={{ opacity: 0, x: 6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 6 }}
                transition={{ duration: 0.15 }}
                className="p-6"
              >
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-xs text-text-muted">
                    Edit the role→model mapping directly. Use any LiteLLM-compatible model ID (e.g.{" "}
                    <code className="text-accent/80 bg-accent/5 px-1 rounded">groq/llama-3.3-70b-versatile</code>,{" "}
                    <code className="text-accent/80 bg-accent/5 px-1 rounded">anthropic/claude-sonnet-4-6</code>).
                  </p>
                </div>

                <div className={`relative rounded-xl border overflow-hidden ${jsonError ? "border-danger/50" : "border-white/10"}`}>
                  {/* Line numbers gutter */}
                  <div className="flex">
                    <LineNumbers text={jsonText} />
                    <textarea
                      value={jsonText}
                      onChange={(e) => handleJsonChange(e.target.value)}
                      spellCheck={false}
                      className="flex-1 bg-[#0a0a0a] text-sm font-mono text-white/90 p-4 pl-2 resize-none outline-none leading-6 min-h-[280px]"
                      style={{ tabSize: 2 }}
                    />
                  </div>
                </div>

                <AnimatePresence>
                  {jsonError && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="mt-2 flex items-center gap-2 text-xs text-danger"
                    >
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      {jsonError}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Schema reference */}
                <div className="mt-4 rounded-xl border border-white/6 bg-white/2 p-4">
                  <p className="text-[11px] font-medium text-text-muted mb-2 uppercase tracking-widest">Available Roles</p>
                  <div className="flex flex-wrap gap-1.5">
                    {ROLES.map((r) => (
                      <span key={r} className="px-2 py-0.5 rounded bg-white/5 border border-white/8 text-[11px] text-text-muted font-mono">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-white/8 flex items-center justify-between gap-3 bg-white/1">
            <div className="flex items-center gap-3">
              <button
                onClick={handleReset}
                disabled={!config}
                className="flex items-center gap-1.5 text-xs text-text-muted hover:text-white transition-colors disabled:opacity-40"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset to defaults
              </button>
              {saveErr && (
                <span className="text-xs text-danger flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> {saveErr}
                </span>
              )}
            </div>

            <button
              onClick={handleSave}
              disabled={saving || !isDirty || !!jsonError}
              className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-semibold transition-all ${
                saved
                  ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                  : isDirty && !jsonError
                  ? "bg-accent text-white hover:bg-accent/90 shadow-[0_0_16px_rgba(59,130,246,0.3)]"
                  : "bg-white/6 text-text-muted cursor-not-allowed"
              }`}
            >
              {saved ? (
                <><Check className="w-3.5 h-3.5" /> Saved</>
              ) : saving ? (
                "Saving…"
              ) : (
                <><Save className="w-3.5 h-3.5" /> Save changes</>
              )}
            </button>
          </div>
        </motion.div>

        {/* API Keys */}
        <ApiKeysSection />

        {/* Project Context */}
        <ProjectContextSection />

        {/* Reference table */}
        {config && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="mt-6 rounded-2xl border border-white/8 bg-[#0e0e0e] overflow-hidden"
          >
            <div className="px-6 py-4 border-b border-white/6">
              <h2 className="text-xs font-semibold text-white uppercase tracking-widest">Available Models</h2>
              <p className="text-[11px] text-text-muted mt-0.5">Suggested models — any LiteLLM-compatible ID also works</p>
            </div>
            <div className="divide-y divide-white/4">
              {config.available.map((m) => (
                <div key={m.id} className="flex items-center gap-3 px-6 py-3 hover:bg-white/2 transition-colors">
                  <ProviderBadge modelId={m.id} />
                  <code className="text-xs text-white/80 font-mono flex-1">{m.id}</code>
                  <span className="text-[11px] text-text-muted">{m.label}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    m.tier === "powerful" ? "text-violet-400 bg-violet-400/8 border-violet-400/20" :
                    m.tier === "instant"  ? "text-emerald-400 bg-emerald-400/8 border-emerald-400/20" :
                    "text-blue-400 bg-blue-400/8 border-blue-400/20"
                  }`}>{m.tier}</span>
                </div>
              ))}
              <div className="px-6 py-3 flex items-center gap-3">
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-white/6 border-white/10 text-white">Custom</span>
                <code className="text-xs text-text-muted font-mono flex-1">provider/model-name</code>
                <span className="text-[11px] text-text-muted">Any LiteLLM-compatible provider</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded border text-text-muted bg-white/4 border-white/8">any</span>
              </div>
            </div>
          </motion.div>
        )}
      </main>
      </div>
    </div>
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
  const provider    = detectProvider(value);

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
          className="flex-1 bg-white/6 border border-white/15 text-xs font-mono text-white rounded-lg px-2.5 py-1.5 outline-none focus:border-accent/50 placeholder:text-text-muted"
        />
        <button onClick={() => commit(customVal)} className="p-1.5 rounded-lg bg-accent/10 text-accent hover:bg-accent/20 transition-all">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button onClick={() => { setCustom(false); setCustomVal(""); }} className="p-1.5 rounded-lg text-text-muted hover:text-white hover:bg-white/6 transition-all">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-xl bg-white/5 border border-white/10 hover:border-white/20 text-xs text-white transition-all min-w-[200px] group"
      >
        <span className={`${provider.color} font-mono font-medium truncate max-w-[130px]`}>
          {knownOption ? knownOption.label : value}
        </span>
        <ProviderBadge modelId={value} />
        <ChevronDown className="w-3 h-3 text-text-muted ml-auto shrink-0 group-hover:text-white transition-colors" />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.97 }}
              transition={{ duration: 0.13 }}
              className="absolute right-0 top-full mt-1.5 z-20 w-64 rounded-2xl border border-white/12 bg-[#161616] shadow-2xl overflow-y-auto max-h-72"
            >
              {/* Group by provider */}
              {["Groq", "Anthropic", "OpenAI", "Google", "Mistral"].map((prov) => {
                const group = options.filter((o) => o.provider === prov);
                if (!group.length) return null;
                return (
                  <div key={prov}>
                    <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold text-text-muted uppercase tracking-widest">{prov}</p>
                    {group.map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => { onChange(opt.id); setOpen(false); }}
                        className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-white/6 transition-colors text-left ${opt.id === value ? "bg-white/4" : ""}`}
                      >
                        <span className={`font-medium font-mono ${detectProvider(opt.id).color} flex-1 truncate`}>{opt.label}</span>
                        <span className={`text-[10px] px-1 py-0.5 rounded border ${
                          opt.tier === "powerful" ? "text-violet-400 border-violet-400/20 bg-violet-400/6" :
                          opt.tier === "instant"  ? "text-emerald-400 border-emerald-400/20 bg-emerald-400/6" :
                          "text-blue-400 border-blue-400/20 bg-blue-400/6"
                        }`}>{opt.tier}</span>
                        {opt.id === value && <Check className="w-3 h-3 text-accent shrink-0" />}
                      </button>
                    ))}
                  </div>
                );
              })}

              {/* Custom entry */}
              <div className="border-t border-white/6 p-2">
                <button
                  onClick={() => { setOpen(false); setCustomVal(isCustom ? value : ""); setCustom(true); setTimeout(() => inputRef.current?.focus(), 50); }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-text-muted hover:text-white hover:bg-white/6 transition-colors text-left"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Custom model ID…
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// -- Line numbers for JSON editor

function LineNumbers({ text }: { text: string }) {
  const lines = text.split("\n").length;
  return (
    <div className="select-none bg-[#0a0a0a] text-right pr-3 pl-4 py-4 text-text-muted font-mono text-sm leading-6 border-r border-white/6 min-w-[3rem]">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  );
}
