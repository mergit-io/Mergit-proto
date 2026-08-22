import { useEffect, useState } from "react";

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
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

export function WalletConnect() {
  const [address, setAddress] = useState<string | null>(null);

  useEffect(() => {
    setAddress(localStorage.getItem(STORAGE_KEY));
  }, []);

  const connect = () => {
    const generated = deriveFakeAddress("mergit-demo-wallet");
    localStorage.setItem(STORAGE_KEY, generated);
    setAddress(generated);
  };

  if (!address) {
    return (
      <button onClick={connect} className="btn-primary">
        Connect wallet
      </button>
    );
  }

  return (
    <span className="h-9 px-3 border border-line flex items-center gap-2 font-mono text-micro uppercase tabular">
      <span className="w-1.5 h-1.5 bg-mint" />
      {truncate(address)}
    </span>
  );
}
