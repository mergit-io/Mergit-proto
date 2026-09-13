import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import type { ModelConfig } from "../lib/api";
import { Micro } from "./ui";

const ROLE_META: Record<string, { label: string; description: string }> = {
  orchestrator: { label: "Orchestrator", description: "Plans the task DAG from your goal" },
  researcher: { label: "Researcher", description: "Searches the web and gathers facts" },
  writer: { label: "Writer", description: "Synthesises research into documents" },
  coder: { label: "Coder", description: "Writes and executes Python code" },
  integrator: { label: "Integrator", description: "Calls APIs and handles webhooks" },
};

const TIER_LABELS: Record<string, string> = {
  fast: "Fast",
  instant: "Instant",
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

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

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

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 flex items-center justify-center p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Model settings"
        className="panel w-full max-w-lg max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-line shrink-0">
          <div>
            <Micro>Model settings</Micro>
            <p className="text-sm text-dim mt-1.5">Choose which model each agent role uses</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="micro hover:text-text">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 flex-1 overflow-y-auto space-y-0">
          {!config ? (
            <p className="py-8 text-center text-sm text-dim">Loading…</p>
          ) : (
            Object.entries(ROLE_META).map(([role, meta]) => {
              const selected = draft[role] || config.defaults[role];
              return (
                <div
                  key={role}
                  className="flex items-center gap-3 py-3 border-b border-line-soft last:border-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text">{meta.label}</p>
                    <p className="text-xs text-dim truncate">{meta.description}</p>
                  </div>
                  <select
                    value={selected}
                    onChange={(e) => setDraft((d) => ({ ...d, [role]: e.target.value }))}
                    className="field font-mono text-xs w-auto shrink-0"
                  >
                    {config.available.map((opt) => (
                      <option key={opt.id} value={opt.id}>
                        {opt.label} · {TIER_LABELS[opt.tier] ?? opt.tier} · {opt.provider}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })
          )}

          {error && <p className="text-xs text-red px-1 py-2">{error}</p>}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-line flex items-center justify-between gap-3 shrink-0">
          <button
            onClick={() => setDraft(config?.defaults ?? {})}
            disabled={!config}
            className="btn-ghost"
          >
            Reset to defaults
          </button>
          <button onClick={handleSave} disabled={saving || !isDirty} className="btn-primary">
            {saved ? "Saved" : saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
