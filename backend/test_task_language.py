"""A coder asked for one language must not quietly submit another.

Live failure, goal 4ad14cf1 on the deployed build. The task was "Migrate the auth.py file
to Rust, addressing the TODO comment". The coder's only execution tool is `code_exec`, a
PYTHON interpreter, so it cannot run Rust and cannot prove Rust works. It wrote Python
instead, ran that successfully, and submitted:

    {"code": "users = {...}\\n\\ndef login(username, password): ...",
     "path": "auth.py", "output": "Login successful!", "success": True}

Nothing objected. `_self_reported_failure` catches an agent that ADMITS failure —
`success: False`, an empty required field. This is the inverse and the more dangerous
shape: the agent claims success for work it did not do. PR #32 at least told the truth
about itself.

`_language_mismatches` in `github_pr` would have caught Rust arriving under a `.py` path,
but it only guards the COMMIT path, and this goal never reached an integrator. The check
has to happen where the claim is made.
"""
import pytest

from agent_registry import AGENT_REGISTRY
from agent_runner import _submission_problem
from language import requested_language

CODER_REQUIRED = AGENT_REGISTRY["coder"]["output_schema"]["required"]

PYTHON_AUTH = '''users = {
    "admin": "1234",
    "abhinav": "password"
}


def login(username, password):
    if username in users and users[username] == password:
        print("Login successful!")
    else:
        print("Invalid username or password.")
'''

RUST_AUTH = '''use std::collections::HashMap;

fn main() {
    let mut users: HashMap<String, String> = HashMap::new();
    users.insert("admin".to_string(), "1234".to_string());
    println!("Login successful!");
}
'''

MIGRATE_TO_RUST = "Migrate the auth.py file to Rust, addressing the TODO comment"


#: `output` is what the coder claims came out of running the code. For a language the
#: container cannot execute, the honest value says so — see the execution-claim tests.
NOT_RUN = "not executed — code_exec runs Python only"


def _result(code, path="auth.py", output="Login successful!"):
    return {"code": code, "path": path, "output": output, "success": True}


def test_the_exact_submission_that_claimed_a_rust_migration_in_python_is_rejected():
    problem = _submission_problem(_result(PYTHON_AUTH), CODER_REQUIRED, MIGRATE_TO_RUST)
    assert problem is not None
    assert "Rust" in problem and "Python" in problem


def test_the_same_task_answered_in_rust_is_accepted():
    assert _submission_problem(_result(RUST_AUTH, "auth.rs", NOT_RUN), CODER_REQUIRED,
                               MIGRATE_TO_RUST) is None


def test_a_task_that_names_no_language_accepts_any_code():
    assert _submission_problem(_result(PYTHON_AUTH), CODER_REQUIRED,
                               "Fix the bug in the login check") is None


def test_a_task_asking_for_python_accepts_python():
    assert _submission_problem(_result(PYTHON_AUTH), CODER_REQUIRED,
                               "Write the login helper in Python") is None


def test_code_with_no_language_signal_is_not_second_guessed():
    """Silence is not evidence. A snippet too small to identify must pass."""
    assert _submission_problem(_result("# TODO: write this\nX = 1\n", output=NOT_RUN),
                               CODER_REQUIRED, MIGRATE_TO_RUST) is None


def test_a_result_without_a_code_field_is_untouched():
    """The writer and researcher submit prose. Prose is not source and is never scored."""
    required = AGENT_REGISTRY["writer"]["output_schema"]["required"]
    result = {"text": "A report about migrating to Rust.", "title": "Report"}
    assert _submission_problem(result, required, MIGRATE_TO_RUST) is None


def test_the_task_text_is_optional():
    """Every existing caller passes no task text and must behave exactly as before."""
    assert _submission_problem(_result(PYTHON_AUTH), CODER_REQUIRED) is None


# ── Reading the request out of a task description ──────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Migrate the auth.py file to Rust, addressing the TODO comment", "Rust"),
    ("Rewrite the parser in Go", "Go"),
    ("port to golang", "Go"),
    ("Write the login helper in Python", "Python"),
    ("Implement the client in JavaScript", "JavaScript"),
    ("Fix the bug in the login check", None),
    ("Read the file and go through each function", None),
    ("Convert the Python module to Rust", "Rust"),
    ("Rewrite it in Python or in Rust, whichever is cleaner", None),
])
def test_requested_language(text, expected):
    """Only a language introduced by a trigger word counts as the target, so naming the
    SOURCE language in passing does not confuse it. Two competing targets return None."""
    assert requested_language(text) == expected


# ── Claiming a run that cannot have happened ───────────────────────────────────

RUST_WITH_A_TYPO = '''use actix_web::{web, App, HttpResponse, HttpServer, Responder);

async fn login(user: web::Json<User>) -> impl Responder {
    HttpResponse::Ok().body("Login successful")
}
'''


def test_claiming_execution_output_for_a_language_that_cannot_be_run_is_rejected():
    """Live failure, goal b4d3e69a. The wrong-language guard worked — the coder submitted
    real Rust at `auth.rs` this time. It also submitted `output: "Login successful"`, a
    string copied out of its own source, because `code_exec` runs `sys.executable -c` and
    there is no Rust toolchain in the container. The code does not even compile: line 1
    closes a brace with a paren. Nothing ran, and the writer reported the migration as
    successfully completed on the strength of it."""
    result = {"code": RUST_WITH_A_TYPO, "path": "auth.rs",
              "output": "Login successful", "success": True}
    problem = _submission_problem(result, CODER_REQUIRED, MIGRATE_TO_RUST)
    assert problem is not None
    assert "Rust" in problem


def test_saying_plainly_that_it_could_not_be_run_is_accepted():
    """The honest form of the same submission. This is what the guard is asking for."""
    result = {"code": RUST_WITH_A_TYPO, "path": "auth.rs",
              "output": "not executed — code_exec runs Python only, so this Rust was not "
                        "compiled or run", "success": True}
    assert _submission_problem(result, CODER_REQUIRED, MIGRATE_TO_RUST) is None


def test_a_python_task_may_report_real_execution_output():
    """Python is the one language the container can actually run, so its output is
    evidence rather than a claim."""
    result = {"code": "print(1 + 2)\n", "path": "calc.py", "output": "3", "success": True}
    assert _submission_problem(result, CODER_REQUIRED,
                               "Write the calculator in Python") is None


def test_a_task_naming_no_language_is_not_policed_for_execution():
    result = {"code": "print(1 + 2)\n", "path": "calc.py", "output": "3", "success": True}
    assert _submission_problem(result, CODER_REQUIRED, "Fix the calculator") is None
