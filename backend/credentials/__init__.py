"""Per-user delegated authority: the vault, the broker, and the provider clients.

The rule this package exists to enforce: **a token never leaves it.** The broker hands
callers a configured client or a scoped callable, never a credential string. Tools receive
those, so there is no tool argument a model can populate with a token and no tool result
that can return one — which makes prompt-injection exfiltration structurally impossible
rather than merely discouraged.
"""
