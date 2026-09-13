from dataclasses import dataclass
from typing import Any, Callable

from tools.code_exec import code_exec
from tools.code_exec import SCHEMA as CODE_EXEC_SCHEMA
from tools.spawn_goal import spawn_goal
from tools.spawn_goal import SCHEMA as SPAWN_GOAL_SCHEMA
from tools.file_ops import file_ops
from tools.file_ops import SCHEMA as FILE_OPS_SCHEMA
from tools.github_ops import (
    github_read_file, GITHUB_READ_FILE_SCHEMA,
    github_list_dir, GITHUB_LIST_DIR_SCHEMA,
    github_get_issue, GITHUB_GET_ISSUE_SCHEMA,
    github_post_comment, GITHUB_POST_COMMENT_SCHEMA,
    github_search_code, GITHUB_SEARCH_CODE_SCHEMA,
    github_create_repo, GITHUB_CREATE_REPO_SCHEMA,
    github_list_workflows, GITHUB_LIST_WORKFLOWS_SCHEMA,
    github_get_branch_protection, GITHUB_GET_BRANCH_PROTECTION_SCHEMA,
    github_set_branch_protection, GITHUB_SET_BRANCH_PROTECTION_SCHEMA,
)
from tools.github_pr import github_pr
from tools.github_pr import SCHEMA as GITHUB_PR_SCHEMA
from tools.http_request import http_request
from tools.http_request import SCHEMA as HTTP_REQUEST_SCHEMA
from tools.wait_webhook import wait_webhook
from tools.wait_webhook import SCHEMA as WAIT_WEBHOOK_SCHEMA
from tools.web_search import web_search
from tools.web_search import SCHEMA as WEB_SEARCH_SCHEMA


@dataclass
class ToolEntry:
    fn: Callable
    schema: dict[str, Any]


TOOL_REGISTRY: dict[str, ToolEntry] = {
    "web_search":          ToolEntry(fn=web_search, schema=WEB_SEARCH_SCHEMA),
    "http_request":        ToolEntry(fn=http_request, schema=HTTP_REQUEST_SCHEMA),
    "file_ops":            ToolEntry(fn=file_ops, schema=FILE_OPS_SCHEMA),
    "github_pr":           ToolEntry(fn=github_pr, schema=GITHUB_PR_SCHEMA),
    "github_read_file":    ToolEntry(fn=github_read_file, schema=GITHUB_READ_FILE_SCHEMA),
    "github_list_dir":     ToolEntry(fn=github_list_dir, schema=GITHUB_LIST_DIR_SCHEMA),
    "github_get_issue":    ToolEntry(fn=github_get_issue, schema=GITHUB_GET_ISSUE_SCHEMA),
    "github_post_comment": ToolEntry(fn=github_post_comment, schema=GITHUB_POST_COMMENT_SCHEMA),
    "github_search_code":  ToolEntry(fn=github_search_code, schema=GITHUB_SEARCH_CODE_SCHEMA),
    "github_create_repo":  ToolEntry(fn=github_create_repo, schema=GITHUB_CREATE_REPO_SCHEMA),
    "github_list_workflows":       ToolEntry(fn=github_list_workflows, schema=GITHUB_LIST_WORKFLOWS_SCHEMA),
    "github_get_branch_protection": ToolEntry(fn=github_get_branch_protection, schema=GITHUB_GET_BRANCH_PROTECTION_SCHEMA),
    "github_set_branch_protection": ToolEntry(fn=github_set_branch_protection, schema=GITHUB_SET_BRANCH_PROTECTION_SCHEMA),
    "spawn_goal":          ToolEntry(fn=spawn_goal, schema=SPAWN_GOAL_SCHEMA),
    "code_exec":           ToolEntry(fn=code_exec, schema=CODE_EXEC_SCHEMA),
    "wait_webhook":        ToolEntry(fn=wait_webhook, schema=WAIT_WEBHOOK_SCHEMA),
}
