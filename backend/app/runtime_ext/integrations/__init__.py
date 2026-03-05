"""External sync integration adapters (dry-run entrypoints)."""

from app.runtime_ext.integrations.base_adapter import AdapterBuildResult, ExternalSyncAdapter
from app.runtime_ext.integrations.jira_adapter import JiraAdapter
from app.runtime_ext.integrations.pagerduty_adapter import PagerDutyAdapter

ADAPTERS = {
    "jira": JiraAdapter(),
    "pagerduty": PagerDutyAdapter(),
}

__all__ = [
    "AdapterBuildResult",
    "ExternalSyncAdapter",
    "JiraAdapter",
    "PagerDutyAdapter",
    "ADAPTERS",
]

