import { useNavigate } from "react-router-dom";
import type { Passport } from "../../lib/api";
import { Hash, Micro } from "../ui";

export function PassportCard({ passport }: { passport: Passport }) {
  const nav = useNavigate();

  return (
    <button
      onClick={() => nav(`/app/economy/agents/${passport.role}`)}
      className="panel text-left w-full p-5 hover:border-faint transition-colors"
    >
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <p className="font-display font-semibold text-sm uppercase tracking-tight">
            {passport.role}
          </p>
          <p className="font-mono text-micro text-dim mt-0.5">Passport #{passport.token_id}</p>
        </div>
        {passport.soulbound && <Micro className="border border-line px-2 py-1">Soulbound</Micro>}
      </div>

      <dl className="space-y-1.5 mb-4">
        <div className="flex items-center justify-between gap-3">
          <dt className="micro">DID</dt>
          <dd>
            <Hash value={passport.did} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="micro">Owner</dt>
          <dd>
            <Hash value={passport.owner_address} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="micro">Mint block</dt>
          <dd className="font-mono text-xs tabular text-dim">
            #{passport.mint_block.toLocaleString()}
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-1.5">
        {passport.capabilities.slice(0, 6).map((cap) => (
          <span
            key={cap}
            className="font-mono text-micro px-1.5 py-0.5 border border-line-soft text-dim"
          >
            {cap}
          </span>
        ))}
        {passport.capabilities.length === 0 && <span className="micro">No tools registered</span>}
      </div>
    </button>
  );
}
