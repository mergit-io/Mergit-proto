"""Changes nobody asked for, riding along inside a bug fix.

Two live failures, three weeks apart, that no existing guard could see because nothing
about either was false:

* Run `b8800f04` was told "check whether `total()` is correct; if it is already correct,
  say so". `total` returns `sum(numbers)` and is correct. The pipeline opened PR #52
  anyway, adding module-level `assert` statements and a `print` to a library file. Nothing
  in that pull request was a lie. It was work that did not need doing, and the asserts run
  on import for everyone who ever imports `calc`.
* Run `1bf7a52f` fixed the reported bug — `largest` returning 0 for an all-negative list —
  and brought an unrequested `if not numbers: return 0` with it. The diff was `+4 -2` where
  `+2 -2` was the fix. A reviewer cannot tell the fix from the passenger.

The rule these two suggest is not "never change anything extra". It is **say so**. Both
checks refuse only when the pull request body does not account for the extra change, so an
agent that deliberately adds an empty-input guard and writes that down is fine; one that
slips it in silently is not.

Python only, and only for files that parse. A check that guessed at other languages would
refuse real work for the sake of a rule it could not actually apply.
"""
import ast
import re

#: Statements at column zero that DO something when the module is imported, listed rather
#: than inferred by exclusion. Naming what counts is the difference between this guard and
#: one that refuses a pull request for adding a bare name to a file: an expression is only
#: an effect when it CALLS something, and `assert`, loops and `with` all run real code.
#:
#: Everything else at module level — imports, definitions, constants, the `__main__` guard,
#: a stray docstring — is how a library file is supposed to look.
_EFFECTFUL = (ast.Assert, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
              ast.Raise, ast.Delete)


def _parses(source: str) -> ast.Module | None:
    try:
        return ast.parse(source or "")
    except SyntaxError:
        return None


def _is_main_guard(node: ast.stmt) -> bool:
    return (isinstance(node, ast.If)
            and "__name__" in ast.dump(node.test))


def _import_time_effects(tree: ast.Module) -> dict[str, str]:
    """{dumped statement: rendered source} for module-level statements that execute."""
    out = {}
    for node in tree.body:
        if _is_main_guard(node):
            continue
        effectful = isinstance(node, _EFFECTFUL) or (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call))
        if effectful:
            out[ast.dump(node)] = ast.unparse(node)[:120]
    return out


def added_import_time_effects(before: str, after: str, path: str) -> list[str]:
    """Module-level statements the change adds that will run on import.

    PR #52 added `assert total([1, 2, 3]) == 6` and `print("All tests passed.")` at column
    zero of `calc.py`. Every future importer of that module now runs them.
    """
    if not path.endswith(".py"):
        return []
    before_tree, after_tree = _parses(before), _parses(after)
    if before_tree is None or after_tree is None:
        return []

    was = _import_time_effects(before_tree)
    now = _import_time_effects(after_tree)
    return [src for key, src in now.items() if key not in was]


#: A guard clause's trigger, reduced to a word a human would use for it. Only conditions
#: this can name are ever refused: an unrecognised one is left alone, because refusing a
#: change we cannot describe would produce an error message nobody can act on.
_CONCEPTS = (
    ("empty", re.compile(r"^not \w+$|len\(\w+\) *== *0|^\w+ *== *\[\]|^\w+ *== *\(\)|"
                         r"^not len\(\w+\)")),
    ("None",  re.compile(r"is None|^\w+ is not None$")),
)

#: What the description has to say for a concept to count as disclosed.
_DISCLOSED = {
    "empty": re.compile(r"empty|no elements|zero.length|len\(\) *== *0|\[\]", re.I),
    "None":  re.compile(r"\bnone\b|null|missing (?:input|value|argument)", re.I),
}


def _guard_clauses(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    """{dumped If: rendered condition} for early exits at the top of a function body."""
    out = {}
    for node in fn.body:
        if not isinstance(node, ast.If):
            continue
        if all(isinstance(inner, (ast.Return, ast.Raise)) for inner in node.body):
            out[ast.dump(node)] = ast.unparse(node.test)[:80]
    return out


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def added_undisclosed_guards(before: str, after: str, path: str,
                             description: str) -> list[str]:
    """New early-return guards whose trigger the description never mentions.

    Run 1bf7a52f added `if not numbers: return 0` to `largest` while fixing a
    negative-numbers bug, and said nothing about it anywhere. The empty-list case may well
    deserve handling — but it is a second change, and a reviewer reading "fixes largest()
    for all-negative lists" has no reason to look for it.
    """
    if not path.endswith(".py"):
        return []
    before_tree, after_tree = _parses(before), _parses(after)
    if before_tree is None or after_tree is None:
        return []

    old_fns, new_fns = _functions(before_tree), _functions(after_tree)
    problems = []
    for name, fn in new_fns.items():
        if name not in old_fns:
            continue  # a brand-new function is the change, not a passenger on one
        was = _guard_clauses(old_fns[name])
        for key, condition in _guard_clauses(fn).items():
            if key in was:
                continue
            concept = next((c for c, pattern in _CONCEPTS if pattern.search(condition)), "")
            if not concept:
                continue
            if _DISCLOSED[concept].search(description or ""):
                continue
            problems.append(
                f"`{name}` gains a guard for the {concept} case (`{condition}`) that the "
                f"description never mentions")
    return problems


#: A section heading the integrator is required to write. Parsing only that section keeps
#: this from firing on a pull request that fixes bug A while noting bug B is fine.
_ROOT_CAUSE = re.compile(r"##+\s*Root Cause\s*\n(.*?)(?=\n##+\s|\Z)", re.I | re.S)

#: Ways of saying "there was nothing wrong with it".
_NO_DEFECT = re.compile(
    r"no (?:code[- ]level )?(?:issue|bug|defect|problem|error)s? (?:was |were )?(?:found|"
    r"identified|present|detected)|no issues? in|already correct|nothing to fix|"
    r"there (?:is|are) no (?:issue|bug|defect|problem)", re.I)


def declares_no_defect(body: str) -> str:
    """The sentence where this pull request says the code was fine, or "".

    Run b8800f04 was asked to check `total()` and say so if it was already correct. It
    opened PR #53 whose Root Cause section reads "No code-level issue was found in the
    `total()` function" — and then changed the file anyway. The agent had already reached
    the right answer and shipped a pull request instead of reporting it.

    Only the Root Cause section is read. A pull request that fixes one thing while
    observing that another is fine is ordinary and must not be refused for it.
    """
    section = _ROOT_CAUSE.search(body or "")
    if not section:
        return ""
    match = _NO_DEFECT.search(section.group(1))
    return match.group(0) if match else ""


def unrequested_changes(before_after: list[tuple[str, str, str]],
                        description: str) -> list[str]:
    """Everything in this change that the description does not account for."""
    problems: list[str] = []
    admission = declares_no_defect(description)
    if admission:
        problems.append(
            f"the description states there is no defect — \"{admission}\" — and then "
            f"changes the code anyway")
    for path, before, after in before_after:
        problems += [f"`{path}` gains `{src}`, which runs whenever the module is imported"
                     for src in added_import_time_effects(before, after, path)]
        problems += added_undisclosed_guards(before, after, path, description)
    return problems
