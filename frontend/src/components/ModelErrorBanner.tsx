import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Micro } from "./ui";

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
    title: "Invalid API key",
    body: "The API key for the configured model is missing or invalid. Switch to a different provider below.",
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
    <div className="border-l-2 border-red border-y border-r border-line bg-slab p-4 mt-4">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <Micro className="text-red">{title}</Micro>
          <p className="text-sm text-dim mt-1.5 leading-relaxed">{body}</p>
        </div>
        <button onClick={() => setDismissed(true)} aria-label="Dismiss" className="micro hover:text-text shrink-0">
          ✕
        </button>
      </div>

      {showKeyInput && provider && (
        <div className="mt-3">
          <div className="flex items-center gap-2">
            <input
              type={showKey ? "text" : "password"}
              value={keyVal}
              onChange={(e) => setKeyVal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveKey();
                if (e.key === "Escape") setShowKeyInput(false);
              }}
              placeholder={`Paste your ${provider.charAt(0).toUpperCase() + provider.slice(1)} API key…`}
              autoFocus
              className="field font-mono text-xs"
            />
            <button
              type="button"
              onClick={() => setShowKey((s) => !s)}
              className="micro hover:text-text shrink-0"
            >
              {showKey ? "Hide" : "Show"}
            </button>
          </div>
          {keyErr && <p className="mt-1.5 text-xs text-red">{keyErr}</p>}
          <button onClick={saveKey} disabled={keySaving || !keyVal.trim()} className="btn-primary w-full mt-2">
            {keySaving ? "Saving…" : "Save key & retry"}
          </button>
        </div>
      )}

      {keySaved && <p className="mt-3 text-xs text-mint">Key saved — restart your goal to retry</p>}

      <div className="flex items-center gap-2 mt-3">
        {provider && type === "invalid_key" && (
          <button onClick={() => setShowKeyInput((s) => !s)} className="btn-ghost">
            Add API key
          </button>
        )}
        <button onClick={() => nav("/app/models")} className="btn-ghost">
          Change model
        </button>
      </div>
    </div>
  );
}
