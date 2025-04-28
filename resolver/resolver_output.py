from typing import Optional
from openhands.resolver.resolver_output import ResolverOutput

class CustomResolverOutput(ResolverOutput):
    # Inherit resolver output fields and define custom ones
    model: str
    commit_hash: str | None = None
    repo_dir: str | None = None
    branch_name: str | None = None
    default_branch: str | None = None
    base_url: str | None = None
    headers: dict | None = None
    duration: float | None = None