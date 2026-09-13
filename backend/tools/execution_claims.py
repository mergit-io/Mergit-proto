"""Did this run actually execute the thing the pull request says it executed?

The third question a pull request body can be wrong about, after `grounding` (is the prose
true of the diff) and `scope_creep` (does the prose account for the diff). This one is
about the body claiming *work that happened outside the diff* — and it is the one the
deployed demo shipped.

Run on 2026-09-13, live on Render, opened `mergit-e2e-sandbox#67` with a correct fix and
this body:

    ## Verification
    Ran the following commands:
    ```
    from calc import largest
    print(largest([-5, -2, -9]))  # Output: -2
    ```
    All outputs are as expected.

Nothing was run. `DEMO_SAFE_MODE` unregisters `code_exec` on that deployment, and the
coder's own prompt tells it to say the fix was not executed. Every tool returned
`ok: true`, the diff was right, and both existing body guards passed — because neither
asks about a claim whose subject is not the code. A reviewer reads "all outputs are as
expected" and believes the change was tested.

Two rules keep this from refusing honest bodies, and the second matters more than it
looks:

* **Prose only.** Fenced blocks and inline code are stripped first. `# Output: -2` inside
  a transcript is the quoted artifact, not the assertion; the assertion is the sentence
  around it.
* **A negated sentence is not a claim.** "The fix was not executed" is precisely what an
  agent under `DEMO_SAFE_MODE` is instructed to write, and a guard that refused that would
  be punishing the honest answer — which is the one behaviour this project cannot afford.
"""
import re

#: What a verb has to be about for running it to be evidence. Without this, "the nightly
#: reporting job ran and returned 0" — a sentence describing the *bug*, which is exactly
#: what a Problem section is for — reads as a claim to have run something.
_EVIDENCE = (r"(?:tests?|suites?|commands?|scripts?|snippets?|code|checks?|pytest|unittest"
             r"|npm|make|repro\w*|it|them|this|these|the above|the following)")

#: Sentences making the claim. Each is past tense or asserted-present: a body saying what
#: *will* run, or telling a reader how to run something, is not claiming anything.
_CLAIMS: tuple[tuple[str, re.Pattern], ...] = (
    ("says it ran something", re.compile(rf"\bran\b(?=[^.]{{0,40}}\b{_EVIDENCE}\b)", re.I)),
    ("says something was executed",
     re.compile(rf"\bexecut(?:ed|ing)\b(?=[^.]{{0,40}}\b{_EVIDENCE}\b)"
                rf"|\b{_EVIDENCE}\b[^.]{{0,40}}\bwas executed\b", re.I)),
    ("says it tested the change", re.compile(r"\b(?:tested|re-?tested) (?:it|this|them|the \w+|locally|manually)\b", re.I)),
    ("claims tests pass", re.compile(r"\b(?:all )?(?:tests?|checks?|suites?) (?:pass|passed|passes|passing)\b", re.I)),
    ("claims the output matched", re.compile(
        r"\b(?:all )?(?:outputs?|results?|values?) (?:are|were|is|was) (?:as expected|correct)\b", re.I)),
    ("claims verification by running", re.compile(r"\bverif(?:ied|ication)[^.]{0,20}\b(?:running|executing)\b", re.I)),
)

#: A sentence carrying one of these is reporting an absence, not an execution. `not` is
#: deliberately broad: "was not executed", "did not run", "could not be verified".
_NEGATED = re.compile(r"\bnot\b|n't\b|\bcannot\b|\bunable\b|\bwithout\b|\bno (?:tests?|output)\b", re.I)

#: Fenced blocks, then inline spans. A transcript is evidence being quoted; the claim is
#: the prose that introduces it.
_FENCED = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_INLINE = re.compile(r"`[^`\n]*`")

#: Sentence-ish: the unit a negation applies to. Bullets and headings end one too, because
#: "## Verification\nRan the tests" has no full stop in it.
_SENTENCE = re.compile(r"[^.!?\n]+")

#: Tools whose success means this run really did execute something. Kept as a set rather
#: than a single name because the question is "did anything run", and a second execution
#: tool must not silently make every body a false claim.
EXECUTION_TOOLS: frozenset[str] = frozenset({"code_exec"})


def prose(body: str) -> str:
    """The body with code removed — what a claim can legitimately be read out of."""
    return _INLINE.sub(" ", _FENCED.sub(" ", body or ""))


def claims(body: str) -> list[str]:
    """Every sentence of `body` asserting that something was run, described in English.

    Returns the description and the sentence, so a refusal can quote the words back rather
    than asking the agent to guess which line offended.
    """
    found = []
    for sentence in _SENTENCE.findall(prose(body)):
        text = sentence.strip()
        if not text or _NEGATED.search(text):
            continue
        for label, pattern in _CLAIMS:
            if pattern.search(text):
                found.append(f'{label}: "{text[:120]}"')
                break
    return found


async def executed_in_goal(goal_id: str | None) -> bool:
    """True when some task in this goal ran an execution tool and it succeeded.

    Scoped to the goal rather than the task on purpose: the coder runs the tests and the
    integrator opens the pull request, so a per-task check would call every honest body a
    lie. Any failure to read is answered `True` — the guard must not refuse a pull request
    because the database hiccuped.
    """
    if not goal_id:
        return True
    try:
        import db
        names = tuple(EXECUTION_TOOLS)
        placeholders = ",".join("?" for _ in names)
        async with db.get_conn() as conn:
            row = await (
                await conn.execute(
                    f"""SELECT 1 FROM tool_calls tc
                          JOIN tasks t ON t.id = tc.task_id
                         WHERE t.goal_id = ? AND tc.status = 'SUCCESS'
                           AND tc.tool_name IN ({placeholders})
                         LIMIT 1""",
                    (goal_id, *names),
                )
            ).fetchone()
        return row is not None
    except Exception:
        return True
