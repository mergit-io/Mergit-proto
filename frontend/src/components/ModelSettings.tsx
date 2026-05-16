import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Check, ChevronDown, FlaskConical, PenLine, Bell, Code2, Plug, Settings2 } from "lucide-react";
import { api } from "../lib/api";
import type { ModelConfig } from "../lib/api";

const ROLE_META: Record<string, { label: string; description: string; Icon: React.ComponentType<{ className?: string }> }> = {
  orchestrator: { label: "Orchestrator", description: "Plans the task DAG from your goal", Icon: Settings2 },
  researcher:   { label: "Researcher",   description: "Searches the web and gathers facts", Icon: FlaskConical },
  writer:       { label: "Writer",       description: "Synthesises research into documents", Icon: PenLine },
  notifier:     { label: "Notifier",     description: "Sends HTTP notifications to endpoints", Icon: Bell },
  coder:        { label: "Coder",        description: "Writes and executes Python code", Icon: Code2 },
  integrator:   { label: "Integrator",   description: "Calls APIs and handles webhooks", Icon: Plug },
};

const PROVIDER_COLORS: Record<string, string> = {
  Groq:      "text-emerald-400",
  Anthropic: "text-violet-400",
};

const TIER_LABELS: Record<string, string> = {
  fast:     "Fast",
  instant:  "Instant",
  powerful: "Powerful",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ModelSettings({ open, onClose }: Props) {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const c = await api.getModelConfig();
      setConfig(c);
      setDraft(c.models);
    } catch {
      setError("Failed to load model config");
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await api.updateModelConfig(draft);
      setDraft(res.models);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const isDirty = config && JSON.stringify(draft) !== JSON.stringify(config.models);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div
              className="pointer-events-auto w-full max-w-lg rounded-2xl border border-white/10 bg-[#111] shadow-2xl overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
                <div>
                  <h2 className="text-sm font-semibold text-white">Model Settings</h2>
                  <p className="text-xs text-text-muted mt-0.5">Choose which model each agent role uses</p>
                </div>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-text-muted hover:text-white hover:bg-white/8 transition-all"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="px-6 py-4 max-h-[60vh] overflow-y-auto space-y-3">
                {!config ? (
                  <div className="py-8 text-center text-text-muted text-sm">Loading…</div>
                ) : (
                  Object.entries(ROLE_META).map(([role, meta]) => {
                    const { label, description, Icon } = meta;
                    const selected = draft[role] || config.defaults[role];
                    return (
                      <div key={role} className="flex items-center gap-3 p-3 rounded-xl bg-white/3 border border-white/6 hover:border-white/10 transition-all">
                        <div className="w-8 h-8 rounded-lg bg-white/6 flex items-center justify-center shrink-0">
                          <Icon className="w-4 h-4 text-text-muted" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-white">{label}</div>
                          <div className="text-[10px] text-text-muted truncate">{description}</div>
                        </div>
                        <div className="shrink-0">
                          <ModelSelect
                            value={selected}
                            options={config.available}
                            onChange={(v) => setDraft((d) => ({ ...d, [role]: v }))}
                          />
                        </div>
                      </div>
                    );
                  })
                )}

                {error && (
                  <p className="text-xs text-red-400 px-1">{error}</p>
                )}
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-white/8 flex items-center justify-between gap-3">
                <button
                  onClick={() => { setDraft(config?.defaults ?? {}); }}
                  className="text-xs text-text-muted hover:text-white transition-colors"
                  disabled={!config}
                >
                  Reset to defaults
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !isDirty}
                  className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    saved
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : isDirty
                      ? "bg-accent text-white hover:bg-accent/90"
                      : "bg-white/6 text-text-muted cursor-not-allowed"
                  }`}
                >
                  {saved ? (
                    <><Check className="w-3.5 h-3.5" /> Saved</>
                  ) : saving ? (
                    "Saving…"
                  ) : (
                    "Save changes"
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function ModelSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { id: string; label: string; provider: string; tier: string }[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.id === value);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 pl-2.5 pr-2 py-1.5 rounded-lg bg-white/6 border border-white/10 hover:border-white/20 text-xs text-white transition-all min-w-[140px]"
      >
        <span className={`${PROVIDER_COLORS[selected?.provider ?? ""] ?? "text-white"} font-medium truncate`}>
          {selected?.label ?? value}
        </span>
        <span className="text-[10px] text-text-muted ml-auto">{TIER_LABELS[selected?.tier ?? ""] ?? ""}</span>
        <ChevronDown className="w-3 h-3 text-text-muted shrink-0" />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.97 }}
              transition={{ duration: 0.12 }}
              className="absolute right-0 top-full mt-1 z-20 w-52 rounded-xl border border-white/12 bg-[#1a1a1a] shadow-xl overflow-hidden"
            >
              {options.map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => { onChange(opt.id); setOpen(false); }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-white/6 transition-colors text-left ${
                    opt.id === value ? "bg-white/4" : ""
                  }`}
                >
                  <span className={`font-medium ${PROVIDER_COLORS[opt.provider] ?? "text-white"}`}>
                    {opt.label}
                  </span>
                  <span className="text-text-muted ml-auto">{opt.provider}</span>
                  {opt.id === value && <Check className="w-3 h-3 text-accent shrink-0" />}
                </button>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
