import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, X, Settings, Key, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

function classifyError(error: string): { type: "invalid_key" | "quota" | "rate_limit" | null; provider: string | null } {
  const e = error.toLowerCase();
  const provider =
    e.includes("groq")      ? "groq" :
    e.includes("anthropic") ? "anthropic" :
    null;

  if (/invalid.api.key|invalid_api_key|authentication|unauthorized/.test(e))
    return { type: "invalid_key", provider };
  if (/tokens.per.day|daily.limit|quota|tpd|exceeded/.test(e))
    return { type: "quota", provider };
  if (/rate.limit|tokens.per.minute|tpm|429/.test(e))
    return { type: "rate_limit", provider };
  return { type: null, provider: null };
}

const MESSAGES = {
  invalid_key: {
    title: "Invalid API Key",
    body: "The API key for the configured model is missing or invalid. Go to Models to switch to a different provider.",
  },
  quota: {
    title: "Model quota exceeded",
    body: "You've hit the daily token limit for this model. Switch to a different model to continue.",
  },
  rate_limit: {
    title: "Rate limit hit",
    body: "Too many requests to this model. Switch to a different model or wait a moment.",
  },
};

export function ModelErrorBanner({ error }: { error: string }) {
  const [dismissed, setDismissed] = useState(false);
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [keyVal, setKeyVal] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keySaving, setKeySaving] = useState(false);
  const [keySaved, setKeySaved] = useState(false);
  const [keyErr, setKeyErr] = useState<string | null>(null);
  const nav = useNavigate();
  const { type, provider } = classifyError(error);

  if (!type || dismissed) return null;

  const { title, body } = MESSAGES[type];

  const saveKey = async () => {
    if (!provider || !keyVal.trim()) return;
    setKeySaving(true);
    setKeyErr(null);
    try {
      await api.updateApiKey(provider, keyVal.trim());
      setKeySaved(true);
      setShowKeyInput(false);
      setKeyVal("");
      setTimeout(() => setKeySaved(false), 3000);
    } catch (e) {
      setKeyErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setKeySaving(false);
    }
  };

  return (
    <AnimatePresence>
      {/* Backdrop + centering container */}
      <motion.div
        key="backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-sm flex items-center justify-center"
        onClick={() => setDismissed(true)}
      >
      {/* Modal */}
      <motion.div
        key="modal"
        initial={{ opacity: 0, scale: 0.92, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 8 }}
        transition={{ type: "spring", damping: 22, stiffness: 320 }}
        className="w-[360px] rounded-2xl border border-amber-500/30 bg-[#0e0e0e] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* amber top bar */}
        <div className="h-0.5 bg-gradient-to-r from-amber-500/70 to-orange-500/50" />

        <div className="p-5">
          {/* Header */}
          <div className="flex items-start gap-3 mb-4">
            <div className="mt-0.5 w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-4.5 h-4.5 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">{title}</p>
              <p className="text-xs text-text-muted mt-1 leading-relaxed">{body}</p>
            </div>
            <button
              onClick={() => setDismissed(true)}
              className="text-text-muted hover:text-white transition-colors shrink-0 mt-0.5"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Inline key input */}
          <AnimatePresence>
            {showKeyInput && provider && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-3 overflow-hidden"
              >
                <div className="flex items-center gap-2 rounded-xl border border-white/12 bg-white/3 px-3 py-2">
                  <input
                    type={showKey ? "text" : "password"}
                    value={keyVal}
                    onChange={(e) => setKeyVal(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveKey(); if (e.key === "Escape") setShowKeyInput(false); }}
                    placeholder={`Paste your ${provider.charAt(0).toUpperCase() + provider.slice(1)} API key…`}
                    autoFocus
                    className="flex-1 bg-transparent text-xs text-white font-mono outline-none placeholder:text-text-muted"
                  />
                  <button onClick={() => setShowKey((s) => !s)} className="text-text-muted hover:text-white">
                    {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
                {keyErr && <p className="mt-1 text-[11px] text-danger">{keyErr}</p>}
                <button
                  onClick={saveKey}
                  disabled={keySaving || !keyVal.trim()}
                  className="mt-2 w-full px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-40 transition-all"
                >
                  {keySaving ? "Saving…" : "Save key & retry"}
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {keySaved && (
            <p className="mb-3 text-xs text-emerald-400 text-center">Key saved — restart your goal to retry</p>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDismissed(true)}
              className="flex-1 px-4 py-2 rounded-xl text-xs font-medium text-text-muted hover:text-white border border-white/8 hover:border-white/20 transition-all"
            >
              Dismiss
            </button>
            {provider && type === "invalid_key" && (
              <button
                onClick={() => setShowKeyInput((s) => !s)}
                className="flex-1 px-4 py-2 rounded-xl text-xs font-semibold bg-white/6 hover:bg-white/10 text-white border border-white/10 transition-all flex items-center justify-center gap-1.5"
              >
                <Key className="w-3.5 h-3.5" />
                Add API key
              </button>
            )}
            <button
              onClick={() => nav("/app/models")}
              className="flex-1 px-4 py-2 rounded-xl text-xs font-semibold bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/25 hover:border-amber-500/50 transition-all flex items-center justify-center gap-1.5"
            >
              <Settings className="w-3.5 h-3.5" />
              Change model
            </button>
          </div>
        </div>
      </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
