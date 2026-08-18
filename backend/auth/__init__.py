"""Identity: who the human is, and how that survives a page load.

Three modules, deliberately small and separate:

  `sessions` — mint, load and revoke opaque server-side sessions; build the cookie.
  `oidc`     — the Google sign-in flow, delegated to Authlib.
  `gate`     — the one middleware that decides whether a request may proceed.

Google answers "who is this human?" and nothing else. It cannot authorise anything at
GitHub or Slack — those are separate authorization servers with their own consent, and
each gets its own stored credential under `credentials/`. Identity is the anchor the
per-provider grants hang off, not a substitute for them.
"""
