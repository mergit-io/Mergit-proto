import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ChainStatusInfo } from "../lib/api";

export interface ChainBadge {
  label: string;
  live: boolean;
}

/** Fallback used before the request resolves, or if the backend is unreachable. */
const UNKNOWN: ChainBadge = { label: "Proof of Work on Monad", live: false };

/**
 * Describes the chain the backend is *actually* connected to.
 *
 * The badge used to hard-code "Live on Monad Testnet (simulated)", which was both a
 * manual lie to maintain and self-undermining. Reading the real status means it says
 * something true on a local chain and upgrades itself the moment contracts are deployed
 * to Monad — no code edit, no chance of claiming a network we are not on.
 */
export function describeChain(status: ChainStatusInfo | null): ChainBadge {
  if (!status || status.status === "disabled") return UNKNOWN;

  if (status.status === "not_deployed") {
    return { label: `${status.name} · not deployed`, live: false };
  }
  if (status.status === "error") {
    return { label: `${status.name} · unavailable`, live: false };
  }
  if (status.isLocal) {
    return { label: `Local EVM · chainId ${status.chainId}`, live: true };
  }
  return { label: `Live on ${status.name} · chainId ${status.chainId}`, live: true };
}

export function useChainBadge(): ChainBadge {
  const [badge, setBadge] = useState<ChainBadge>(UNKNOWN);

  useEffect(() => {
    let cancelled = false;
    api
      .getChainStatus()
      .then((status) => {
        if (!cancelled) setBadge(describeChain(status));
      })
      .catch(() => {
        /* keep the neutral fallback — never claim a chain we cannot confirm */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return badge;
}
