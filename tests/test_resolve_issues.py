import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from openhands_resolver.resolve_issues import (
    create_git_patch,
    initialize_runtime,
    complete_runtime,
    process_issue,
)
from openhands_resolver.github_issue import GithubIssue
from openhands.core.config import LLMConfig
from openhands.events.action import CmdRunAction
from openhands.events.observation import CmdOutputObservation
from openhands_resolver.resolver_output import ResolverOutput

@pytest.fixture
def mock_output_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = os.path.join(temp_dir, "repo")
        os.makedirs(repo_path)
        os.system(f"git init {repo_path}")
        readme_path = os.path.join(repo_path, "README.md")
        with open(readme_path, "w") as f:
            f.write("hello world")
        os.system(f"git -C {repo_path} add README.md")
        os.system(f"git -C {repo_path} commit -m 'Initial commit'")
        yield temp_dir

def test_create_git_patch(mock_output_dir):
    workspace = os.path.join(mock_output_dir, "repo")
    with patch("subprocess.check_output", return_value=b"commit_hash"),          patch("builtins.open", MagicMock()) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = "patch content"
        git_id, patch_content = create_git_patch(workspace, "main", "feature_branch", "123.patch")
        assert git_id == "commit_hash"
        assert patch_content == "patch content"

@pytest.mark.asyncio
async def test_complete_runtime():
    mock_runtime = MagicMock()
    mock_runtime.run_action.side_effect = [
        CmdOutputObservation(exit_code=0, content="", command_id=1, command="cd /workspace"),
        CmdOutputObservation(exit_code=0, content="git diff content", command_id=2, command="git diff"),
    ]
    result = await complete_runtime(mock_runtime, "base_commit_hash")
    assert result["git_patch"] == "git diff content"
    assert mock_runtime.run_action.call_count == 2

@pytest.mark.asyncio
async def test_process_issue(mock_output_dir):
    mock_runtime = MagicMock()
    issue = GithubIssue(owner="test_owner", repo="test_repo", number=1, title="Test Issue", body="Fix this issue")
    llm_config = LLMConfig(model="test-model", api_key="api-key")
    handler = MagicMock()
    handler.get_instruction.return_value = "Test instruction"
    handler.issue_type = "issue"

    with patch("openhands_resolver.resolve_issues.create_runtime", MagicMock()):
        result = await process_issue(
            issue, "base_commit", 5, llm_config, mock_output_dir, "image:latest", "template", handler
        )
        assert isinstance(result, ResolverOutput)
        assert result.issue == issue
