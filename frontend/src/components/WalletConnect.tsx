import { useState } from "react";
import { Wallet } from "lucide-react";
import { useChainBadge } from "../hooks/useChainBadge";

const STORAGE_KEY = "mergit_wallet_address";

// Deterministic (not random) fake address so the same demo profile always
// reconnects to the same identity — no real wallet, no real Monad network.
function deriveFakeAddress(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  let hex = "";
  let state = hash || 1;
  while (hex.length < 40) {
    state = (state * 1103515245 + 12345) >>> 0;
    hex += state.toString(16).padStart(8, "0");
  }
  return `0x${hex.slice(0, 40)}`;
}

function truncate(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function WalletConnect() {
  // Read once during the initial render rather than in an effect: localStorage is synchronous,
  // and seeding state from an effect costs an extra render for no benefit.
  const [address, setAddress] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const chain = useChainBadge();

  const connect = () => {
    const generated = deriveFakeAddress("mergit-demo-wallet");
    localStorage.setItem(STORAGE_KEY, generated);
    setAddress(generated);
  };

  if (!address) {
    return (
      <button
        onClick={connect}
        className="flex items-center gap-1.5 rounded-[10px] border border-ink/12 bg-white px-3 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-paper-3"
      >
        <Wallet className="w-3.5 h-3.5" />
        Connect Wallet
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-[10px] border border-ink/10 bg-white px-3 py-2 text-[13px] font-medium">
      <span className={`h-1.5 w-1.5 rounded-full ${chain.live ? "bg-proof" : "bg-ink-dim"}`} />
      <span className="text-ink-muted">{chain.label}</span>
      <span className="font-mono text-ink">{truncate(address)}</span>
    </div>
  );
}
