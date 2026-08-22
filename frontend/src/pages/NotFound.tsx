import { Link } from "react-router-dom";
import { Micro } from "../components/ui";

/** Anything the router does not match.
 *
 *  Without this the app rendered an empty document: `<Routes>` matched nothing, so the
 *  page was blank with no navigation and no way back except editing the URL. A stale
 *  link, a typo, or `/app/audit` (linked from Connections but never built) all landed
 *  there. The server serves the SPA shell for unknown paths, so this is the only place
 *  the case can be handled. */
export function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center px-5">
      <div className="panel px-8 py-10 max-w-lg w-full">
        <Micro>Error 404 — no such page</Micro>
        <h1 className="font-display font-bold tracking-tightest leading-[0.95] mt-4 mb-4 text-[clamp(2rem,5vw,3rem)]">
          That page
          <br />
          does not exist.
        </h1>
        <p className="text-sm text-dim leading-relaxed mb-8">
          The address may be mistyped, or it may point at something that has moved.
        </p>
        <div className="flex flex-wrap gap-px">
          <Link to="/app" className="btn-primary h-10 px-5">
            Go to the console →
          </Link>
          <Link to="/" className="btn-ghost h-10 px-5">
            Back to the home page
          </Link>
        </div>
      </div>
    </div>
  );
}
