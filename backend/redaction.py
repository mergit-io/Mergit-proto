"""One place that knows what a secret looks like.

Mergit has three sinks a credential must never reach, and they are not the obvious ones:

  1. **Logs.** Expected, and the easiest to fix.
  2. **The `tool_calls` table.** `_execute_tool_idempotent` stores every tool result and
     replays it **straight back into model context** on a cache hit. A token that lands
     there is re-read by the model on every subsequent run of that task, long after the
     call that leaked it.
  3. **`messages`.** The conversation is persisted turn by turn.

So redacting at the log formatter alone leaves two of the three open. `scrub()` is applied
at the DB write sites too — see `agent_runner._execute_tool_idempotent` and `db.save_message`.

This is a backstop, not the control. The control is that `credentials/broker.py` hands
tools a *client*, never a token string, so there is no argument the model can populate
with one and no result field that returns one. This module exists because "no token can
reach the model" is a claim worth enforcing twice.
"""
import logging
import re

#: Ordered longest-prefix-first so a more specific pattern wins. Every entry is a real
#: credential format this deployment can hold.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Slack app-configuration tokens — checked BEFORE the generic xox* rule, because
    # `xoxe.xoxp-` starts with a prefix the generic rule would match and truncate.
    ("slack_config", re.compile(r"xoxe\.xoxp-[A-Za-z0-9-]+")),
    ("slack_refresh", re.compile(r"xoxe-[A-Za-z0-9-]+")),
    # Bot / user / app-level / legacy Slack tokens.
    ("slack", re.compile(r"xox[baprs]-[A-Za-z0-9-]+")),
    # GitHub: PAT (ghp), OAuth (gho), user-to-server (ghu), server-to-server (ghs),
    # refresh (ghr), and fine-grained (github_pat_).
    ("github_pat_fine", re.compile(r"github_pat_[A-Za-z0-9_]+")),
    # NOT length-bounded: GitHub's stateless ghs_ format is ~520 chars and variable.
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9_]+")),
    # LLM providers.
    ("openrouter", re.compile(r"sk-or-v1-[A-Za-z0-9-]+")),
    ("anthropic", re.compile(r"sk-ant-[A-Za-z0-9_-]+")),
    ("groq", re.compile(r"gsk_[A-Za-z0-9]+")),
    ("openai_like", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("tavily", re.compile(r"tvly-[A-Za-z0-9-]+")),
    # PEM private keys — the GitHub App key, and anything else pasted in by mistake.
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                       re.DOTALL)),
    # Bearer headers, in case a tool result ever echoes request headers back.
    ("bearer", re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._~+/-]{16,}=*")),
]


def scrub(text: str) -> str:
    """Replace anything that looks like a credential with a labelled placeholder.

    The label is kept (`[REDACTED:github]` rather than `***`) because an agent that gets an
    opaque error needs to know *which* credential was involved to act on it, and an
    operator reading a log needs to know which key to rotate.
    """
    if not text:
        return text
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED:{label}]", text)
    return text


def scrub_obj(value):
    """Scrub recursively through the JSON-shaped structures tools return.

    Applied before a tool result is persisted, so it must not change the shape — only the
    strings. Dict *keys* are left alone: a key is a field name, and rewriting one would
    silently break a downstream `{{t1.output.field}}` interpolation.
    """
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: scrub_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_obj(v) for v in value]
    return value


class RedactingFilter(logging.Filter):
    """Scrubs the formatted message and every positional arg.

    Both are necessary: `logger.info("token=%s", tok)` keeps the secret in `record.args`
    until formatting, so filtering `record.msg` alone would let it through.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: scrub(v) if isinstance(v, str) else v
                               for k, v in record.args.items()}
            else:
                record.args = tuple(scrub(a) if isinstance(a, str) else a
                                    for a in record.args)
        return True


def install(root: logging.Logger | None = None) -> None:
    """Attach the filter to every existing handler, and to the root logger.

    Handlers are filtered rather than only the logger, because a filter on a logger does
    not apply to records that propagate up from its children — which is most of them.
    """
    root = root or logging.getLogger()
    filt = RedactingFilter()
    root.addFilter(filt)
    for handler in root.handlers:
        handler.addFilter(filt)
