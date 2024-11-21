import pytest
from unittest.mock import MagicMock, patch
from openhands_resolver.send_pull_request import create_pull_request

@pytest.fixture
def mock_github_api():
    with patch("requests.post") as mock_post:
        yield mock_post

def test_create_pull_request_success(mock_github_api):
    mock_github_api.return_value.status_code = 201
    mock_github_api.return_value.json.return_value = {"html_url": "http://github.com/sample-pr"}
    pr_url = create_pull_request(
        owner="test_owner",
        repo="test_repo",
        token="fake_token",
        branch_name="feature_branch",
        title="Test PR",
        body="Fixing some issues"
    )
    assert pr_url == "http://github.com/sample-pr"
    mock_github_api.assert_called_once()

def test_create_pull_request_failure(mock_github_api):
    mock_github_api.return_value.status_code = 400
    with pytest.raises(Exception, match="Failed to create pull request"):
        create_pull_request(
            owner="test_owner",
            repo="test_repo",
            token="fake_token",
            branch_name="feature_branch",
            title="Test PR",
            body="Fixing some issues"
        )
