/* Content the landing pages share.
   ------------------------------------------------------------------------------
   There are two landings now — the moss world at `/` and the editorial page at
   `/next` — and they make the same claims about the same system. Anything both
   say lives here, so that changing a receipt or adding a provider is one edit
   rather than two that drift apart.

   The run's four stages live beside this in runStages.ts, where they were already
   shared between this section's card grid and its pinned story. */

/** Illustrative receipts — the shape of the ledger, not live data. The console at
    /app/economy shows the real thing. */
export const RECEIPTS = [
  { tx: "0x9f2c…41ab", role: "integrator", rep: "+18" },
  { tx: "0x41de…7c02", role: "coder", rep: "+12" },
  { tx: "0xbb10…9e3f", role: "researcher", rep: "+9" },
  { tx: "0x0d77…a5c4", role: "writer", rep: "+21" },
];

/** What happens to a task's output between finishing and being checkable. */
export const CHAIN: [string, string][] = [
  ["Canonical output", "The task's result, serialised the same way every time"],
  ["SHA-256 digest", "Hashed, so the record is a fixed size and tamper-evident"],
  ["On-chain record", "Written to ProofOfWork with the agent's passport token"],
  ["Reputation", "Success rate, speed and volume recomposed into one score"],
];

/** Each piece is here because of how it behaves on a bad day. */
export const STACK = [
  { name: "Groq", role: "Default inference for every agent role" },
  { name: "Anthropic", role: "First fallback when a provider caps out" },
  { name: "OpenRouter", role: "Second and third tiers of the fallback chain" },
  { name: "LiteLLM", role: "One interface across all three providers" },
  { name: "Tavily", role: "Web search for the researcher" },
  { name: "FastAPI", role: "API, event stream, and the app itself" },
  { name: "SQLite (WAL)", role: "Durable state with atomic lease claiming" },
  { name: "Solidity on EVM", role: "Passports, proofs, reputation, audit trail" },
];
