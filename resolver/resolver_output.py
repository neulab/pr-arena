from openhands.resolver.resolver_output import ResolverOutput

class CustomResolverOutput(ResolverOutput):
    # Inherit resolver output fields and define custom ones:
    # # issue: Issue
    # # issue_type: str
    # # instruction: str
    # # base_commit: str
    # # git_patch: str
    # # history: list[dict[str, Any]]
    # # metrics: dict[str, Any] | None
    # # success: bool
    # # comment_success: list[bool] | None
    # # result_explanation: str
    # # error: str | None
    model: str | None = None # Set None default but ensure it gets filled later
    commit_hash: str | None = None
    repo_dir: str | None = None
    branch_name: str | None = None
    default_branch: str | None = None
    base_url: str | None = None
    headers: dict | None = None
    duration: float | None = None