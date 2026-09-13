from dataclasses import dataclass
from typing import Any, Callable

from config import settings

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
    github_create_issue, GITHUB_CREATE_ISSUE_SCHEMA,
    github_fork, GITHUB_FORK_SCHEMA,
    github_close_issue, GITHUB_CLOSE_ISSUE_SCHEMA,
    github_add_labels, GITHUB_ADD_LABELS_SCHEMA,
    github_get_pr, GITHUB_GET_PR_SCHEMA,
    github_list_prs, GITHUB_LIST_PRS_SCHEMA,
    github_get_pr_files, GITHUB_GET_PR_FILES_SCHEMA,
    github_review_pr, GITHUB_REVIEW_PR_SCHEMA,
    github_request_review, GITHUB_REQUEST_REVIEW_SCHEMA,
    github_update_pr, GITHUB_UPDATE_PR_SCHEMA,
    github_merge_pr, GITHUB_MERGE_PR_SCHEMA,
)
from tools.github_pr import github_pr
from tools.github_pr import SCHEMA as GITHUB_PR_SCHEMA
from tools.http_request import http_request
from tools.http_request import SCHEMA as HTTP_REQUEST_SCHEMA
from tools.slack_ops import (
    slack_list_channels, SLACK_LIST_CHANNELS_SCHEMA,
    slack_read_channel, SLACK_READ_CHANNEL_SCHEMA,
    slack_read_thread, SLACK_READ_THREAD_SCHEMA,
    slack_post_message, SLACK_POST_MESSAGE_SCHEMA,
    slack_reply_in_thread, SLACK_REPLY_IN_THREAD_SCHEMA,
)
from tools.linear_ops import (
    linear_list_teams, LINEAR_LIST_TEAMS_SCHEMA,
    linear_list_states, LINEAR_LIST_STATES_SCHEMA,
    linear_create_issue, LINEAR_CREATE_ISSUE_SCHEMA,
    linear_get_issue, LINEAR_GET_ISSUE_SCHEMA,
    linear_update_issue, LINEAR_UPDATE_ISSUE_SCHEMA,
    linear_comment, LINEAR_COMMENT_SCHEMA,
)
from tools.notion_ops import (
    notion_search, NOTION_SEARCH_SCHEMA,
    notion_create_page, NOTION_CREATE_PAGE_SCHEMA,
    notion_append_blocks, NOTION_APPEND_BLOCKS_SCHEMA,
    notion_get_page, NOTION_GET_PAGE_SCHEMA,
)
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
    "github_fork":         ToolEntry(fn=github_fork, schema=GITHUB_FORK_SCHEMA),
    "github_read_file":    ToolEntry(fn=github_read_file, schema=GITHUB_READ_FILE_SCHEMA),
    "github_list_dir":     ToolEntry(fn=github_list_dir, schema=GITHUB_LIST_DIR_SCHEMA),
    "github_get_issue":    ToolEntry(fn=github_get_issue, schema=GITHUB_GET_ISSUE_SCHEMA),
    "github_post_comment": ToolEntry(fn=github_post_comment, schema=GITHUB_POST_COMMENT_SCHEMA),
    "github_search_code":  ToolEntry(fn=github_search_code, schema=GITHUB_SEARCH_CODE_SCHEMA),
    "github_create_repo":  ToolEntry(fn=github_create_repo, schema=GITHUB_CREATE_REPO_SCHEMA),
    "github_list_workflows":       ToolEntry(fn=github_list_workflows, schema=GITHUB_LIST_WORKFLOWS_SCHEMA),
    "github_get_branch_protection": ToolEntry(fn=github_get_branch_protection, schema=GITHUB_GET_BRANCH_PROTECTION_SCHEMA),
    "github_set_branch_protection": ToolEntry(fn=github_set_branch_protection, schema=GITHUB_SET_BRANCH_PROTECTION_SCHEMA),
    "github_create_issue":   ToolEntry(fn=github_create_issue, schema=GITHUB_CREATE_ISSUE_SCHEMA),
    "github_close_issue":    ToolEntry(fn=github_close_issue, schema=GITHUB_CLOSE_ISSUE_SCHEMA),
    "github_add_labels":     ToolEntry(fn=github_add_labels, schema=GITHUB_ADD_LABELS_SCHEMA),
    "github_get_pr":         ToolEntry(fn=github_get_pr, schema=GITHUB_GET_PR_SCHEMA),
    "github_list_prs":       ToolEntry(fn=github_list_prs, schema=GITHUB_LIST_PRS_SCHEMA),
    "github_get_pr_files":   ToolEntry(fn=github_get_pr_files, schema=GITHUB_GET_PR_FILES_SCHEMA),
    "github_review_pr":      ToolEntry(fn=github_review_pr, schema=GITHUB_REVIEW_PR_SCHEMA),
    "github_request_review": ToolEntry(fn=github_request_review, schema=GITHUB_REQUEST_REVIEW_SCHEMA),
    "github_update_pr":      ToolEntry(fn=github_update_pr, schema=GITHUB_UPDATE_PR_SCHEMA),
    "github_merge_pr":       ToolEntry(fn=github_merge_pr, schema=GITHUB_MERGE_PR_SCHEMA),

    # ── Slack ────────────────────────────────────────────────────────────────────
    "slack_list_channels":  ToolEntry(fn=slack_list_channels, schema=SLACK_LIST_CHANNELS_SCHEMA),
    "slack_read_channel":   ToolEntry(fn=slack_read_channel, schema=SLACK_READ_CHANNEL_SCHEMA),
    "slack_read_thread":    ToolEntry(fn=slack_read_thread, schema=SLACK_READ_THREAD_SCHEMA),
    "slack_post_message":   ToolEntry(fn=slack_post_message, schema=SLACK_POST_MESSAGE_SCHEMA),
    "slack_reply_in_thread": ToolEntry(fn=slack_reply_in_thread, schema=SLACK_REPLY_IN_THREAD_SCHEMA),
    # ── Linear ───────────────────────────────────────────────────────────────────
    "linear_list_teams":    ToolEntry(fn=linear_list_teams, schema=LINEAR_LIST_TEAMS_SCHEMA),
    "linear_list_states":   ToolEntry(fn=linear_list_states, schema=LINEAR_LIST_STATES_SCHEMA),
    "linear_create_issue":  ToolEntry(fn=linear_create_issue, schema=LINEAR_CREATE_ISSUE_SCHEMA),
    "linear_get_issue":     ToolEntry(fn=linear_get_issue, schema=LINEAR_GET_ISSUE_SCHEMA),
    "linear_update_issue":  ToolEntry(fn=linear_update_issue, schema=LINEAR_UPDATE_ISSUE_SCHEMA),
    "linear_comment":       ToolEntry(fn=linear_comment, schema=LINEAR_COMMENT_SCHEMA),
    # ── Notion ───────────────────────────────────────────────────────────────────
    "notion_search":        ToolEntry(fn=notion_search, schema=NOTION_SEARCH_SCHEMA),
    "notion_create_page":   ToolEntry(fn=notion_create_page, schema=NOTION_CREATE_PAGE_SCHEMA),
    "notion_append_blocks": ToolEntry(fn=notion_append_blocks, schema=NOTION_APPEND_BLOCKS_SCHEMA),
    "notion_get_page":      ToolEntry(fn=notion_get_page, schema=NOTION_GET_PAGE_SCHEMA),
    "spawn_goal":          ToolEntry(fn=spawn_goal, schema=SPAWN_GOAL_SCHEMA),
    "code_exec":           ToolEntry(fn=code_exec, schema=CODE_EXEC_SCHEMA),
    "wait_webhook":        ToolEntry(fn=wait_webhook, schema=WAIT_WEBHOOK_SCHEMA),
}


# `code_exec` runs model-authored Python in a subprocess of the API server. That is
# acceptable on a laptop and not acceptable on a public URL where `POST /api/goals` is
# reachable by anyone, so a public deployment sets DEMO_SAFE_MODE and the tool ceases to
# exist. Unregistering is done here, at import, rather than checked per call — a tool that
# is absent cannot be reached by any path, including a replayed `tool_calls` row.
#
# `agent_registry` performs the matching half: it removes `code_exec` from the coder's
# allowed_tools under the same flag. Both are required. Unregistering alone leaves the
# tool in the schema the model is shown, so it calls a tool that no longer exists, gets
# "Unknown tool: code_exec", and spends its `consecutive_errors` budget discovering that.
if settings.demo_safe_mode:
    TOOL_REGISTRY.pop("code_exec", None)
