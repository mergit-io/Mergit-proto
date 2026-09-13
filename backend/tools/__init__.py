from dataclasses import dataclass
from typing import Any, Callable

from tools.code_exec import code_exec
from tools.code_exec import SCHEMA as CODE_EXEC_SCHEMA
from tools.file_ops import file_ops
from tools.file_ops import SCHEMA as FILE_OPS_SCHEMA
from tools.github_pr import github_pr
from tools.github_pr import SCHEMA as GITHUB_PR_SCHEMA
from tools.http_request import http_request
from tools.http_request import SCHEMA as HTTP_REQUEST_SCHEMA
from tools.slack_notify import slack_notify
from tools.slack_notify import SCHEMA as SLACK_NOTIFY_SCHEMA
from tools.wait_webhook import wait_webhook
from tools.wait_webhook import SCHEMA as WAIT_WEBHOOK_SCHEMA
from tools.web_search import web_search
from tools.web_search import SCHEMA as WEB_SEARCH_SCHEMA


@dataclass
class ToolEntry:
    fn: Callable
    schema: dict[str, Any]


TOOL_REGISTRY: dict[str, ToolEntry] = {
    "web_search": ToolEntry(fn=web_search, schema=WEB_SEARCH_SCHEMA),
    "http_request": ToolEntry(fn=http_request, schema=HTTP_REQUEST_SCHEMA),
    "slack_notify": ToolEntry(fn=slack_notify, schema=SLACK_NOTIFY_SCHEMA),
    "file_ops": ToolEntry(fn=file_ops, schema=FILE_OPS_SCHEMA),
    "github_pr": ToolEntry(fn=github_pr, schema=GITHUB_PR_SCHEMA),
    "code_exec": ToolEntry(fn=code_exec, schema=CODE_EXEC_SCHEMA),
    "wait_webhook": ToolEntry(fn=wait_webhook, schema=WAIT_WEBHOOK_SCHEMA),
}
