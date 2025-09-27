from typing import Any
from pydantic import Field
from openhands.resolver.resolver_output import ResolverOutput

class CustomResolverOutput(ResolverOutput):
    # Inherit resolver output fields and define custom ones:
    # Override parent fields with defaults for testing compatibility
    instruction: str = Field(default="")
    base_commit: str = Field(default="")
    git_patch: str | None = Field(default=None)
    history: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] | None = Field(default=None)
    success: bool = Field(default=True)
    comment_success: list[bool] | None = Field(default=None)
    result_explanation: str = Field(default="")
    error: str | None = Field(default=None)
    
    # Custom fields for PR-Arena
    model: str | None = Field(default=None) # Set None default but ensure it gets filled later
    commit_hash: str | None = Field(default=None)
    repo_dir: str | None = Field(default=None)
    branch_name: str | None = Field(default=None)
    default_branch: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    headers: dict | None = Field(default=None)
    duration: float | None = Field(default=None)
    
    # Cost tracking fields
    accumulated_cost: float | None = Field(default=None)
    token_usage: dict[str, Any] | None = Field(default=None)
    cost_per_input_token: float | None = Field(default=None)
    cost_per_output_token: float | None = Field(default=None)
    
    # Iteration tracking fields
    total_iterations: int | None = Field(default=None)
    action_count: int | None = Field(default=None)
    iteration_number: int | None = Field(default=None)
