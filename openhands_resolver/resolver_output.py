from typing import Any, Optional
from litellm import BaseModel
from openhands_resolver.github_issue import GithubIssue

class ResolverOutput(BaseModel):
    # NOTE: User-specified
    issue: GithubIssue
    issue_type: str
    instruction: str
    base_commit: str
    git_patch: str
    history: list[dict[str, Any]]
    metrics: dict[str, Any] | None
    success: bool
    comment_success: list[bool] | None
    success_explanation: str
    error: str | None
    commit_id: Optional[str] = None
    commit_hash: Optional[str] = None
    repo_dir: Optional[str] = None