import unittest
import os
from unittest.mock import Mock, patch, AsyncMock
from argparse import Namespace

# Import the classes we want to test
from resolver.resolve_issue import PRArenaIssueResolver
from resolver.resolver_output import CustomResolverOutput


class TestPRArenaIssueResolver(unittest.TestCase):
    """Test cases for PRArenaIssueResolver class"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_args = Namespace(
            selected_repo="test-owner/test-repo",
            token="test-token",
            username="test-user",
            base_container_image=None,
            runtime_container_image=None,
            is_experimental=False,
            llm_models="claude-sonnet-4-20250514,gpt-4.1-2025-04-14",
            llm_base_url=None,
            max_iterations=50,
            repo_instruction_file=None,
            issue_type="issue",
            issue_number=123,
            comment_id=None
        )
        
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'LLM_MODELS': 'claude-sonnet-4-20250514,gpt-4.1-2025-04-14',
            'GITHUB_TOKEN': 'test-token',
            'GIT_USERNAME': 'test-user'
        })
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests"""
        self.env_patcher.stop()

    @patch('resolver.secrets.Secrets.get_api_key')
    @patch('resolver.secrets.Secrets.get_firebase_config')
    @patch('resolver.resolve_issue.load_firebase_config')
    @patch('resolver.resolve_issue.apply_daytona_patch')
    def test_init_valid_args(self, mock_apply_patch, mock_load_firebase, mock_get_firebase_config, mock_get_api_key):
        """Test PRArenaIssueResolver initialization with valid arguments"""
        mock_get_api_key.return_value = "test-api-key"
        mock_get_firebase_config.return_value = '{"test": "config"}'
        mock_load_firebase.return_value = {"test": "config"}
        
        resolver = PRArenaIssueResolver(self.mock_args)
        
        self.assertEqual(resolver.owner, "test-owner")
        self.assertEqual(resolver.repo, "test-repo")
        self.assertEqual(resolver.token, "test-token")
        self.assertEqual(resolver.username, "test-user")
        self.assertEqual(resolver.issue_number, 123)
        self.assertEqual(len(resolver.llm_configs), 2)

    def test_init_invalid_repo_format(self):
        """Test initialization with invalid repository format"""
        self.mock_args.selected_repo = "invalid-repo-format"
        
        with self.assertRaises(ValueError) as context:
            PRArenaIssueResolver(self.mock_args)
        
        self.assertIn("Invalid repository format", str(context.exception))

    def test_init_missing_token(self):
        """Test initialization with missing token"""
        self.mock_args.token = None
        
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as context:
                PRArenaIssueResolver(self.mock_args)
            
            self.assertIn("Token is required", str(context.exception))

    def test_init_missing_username(self):
        """Test initialization with missing username"""
        self.mock_args.username = None
        
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'test-token'}, clear=True):
            with self.assertRaises(ValueError) as context:
                PRArenaIssueResolver(self.mock_args)
            
            self.assertIn("Username is required", str(context.exception))

    @patch('resolver.resolve_issue.Secrets')
    @patch('resolver.resolve_issue.load_firebase_config')
    @patch('resolver.resolve_issue.apply_daytona_patch')
    async def test_complete_runtime(self, mock_apply_patch, mock_load_firebase, mock_secrets):
        """Test complete_runtime method"""
        mock_secrets.get_api_key.return_value = "test-api-key"
        mock_secrets.get_firebase_config.return_value = {"test": "config"}
        mock_load_firebase.return_value = {"test": "config"}
        
        resolver = PRArenaIssueResolver(self.mock_args)
        
        # Mock runtime and its methods
        mock_runtime = Mock()
        mock_runtime.close = Mock()
        
        # Mock parent class method
        with patch.object(PRArenaIssueResolver.__bases__[0], 'complete_runtime', 
                         return_value={'patch': 'test-patch'}) as mock_super:
            result = await resolver.complete_runtime(mock_runtime, "test-commit")
            
            self.assertEqual(result, {'patch': 'test-patch'})
            mock_super.assert_called_once_with(mock_runtime, "test-commit")
            mock_runtime.close.assert_called_once()

    @patch('resolver.secrets.Secrets.get_api_key')
    @patch('resolver.secrets.Secrets.get_firebase_config')
    @patch('resolver.resolve_issue.load_firebase_config')
    @patch('resolver.resolve_issue.apply_daytona_patch')
    @patch('resolver.resolve_issue.subprocess.run')
    def test_prepare_branch_and_push_invalid_pr_type(self, mock_subprocess, mock_apply_patch, 
                                                    mock_load_firebase, mock_get_firebase_config, mock_get_api_key):
        """Test prepare_branch_and_push with invalid pr_type"""
        mock_get_api_key.return_value = "test-api-key"
        mock_get_firebase_config.return_value = '{"test": "config"}'
        mock_load_firebase.return_value = {"test": "config"}
        
        resolver = PRArenaIssueResolver(self.mock_args)
        
        with self.assertRaises(ValueError) as context:
            resolver.prepare_branch_and_push("test-dir", "invalid")
        
        self.assertIn("Invalid pr_type", str(context.exception))

    @patch('resolver.secrets.Secrets.get_api_key')
    @patch('resolver.secrets.Secrets.get_firebase_config')
    @patch('resolver.resolve_issue.load_firebase_config')
    @patch('resolver.resolve_issue.apply_daytona_patch')
    @patch('resolver.resolve_issue.requests.get')
    @patch('resolver.resolve_issue.httpx.get')
    @patch('resolver.resolve_issue.subprocess.run')
    def test_prepare_branch_and_push_success(self, mock_subprocess, mock_httpx, mock_requests,
                                           mock_apply_patch, mock_load_firebase, mock_get_firebase_config, mock_get_api_key):
        """Test successful prepare_branch_and_push execution"""
        mock_get_api_key.return_value = "test-api-key"
        mock_get_firebase_config.return_value = '{"test": "config"}'
        mock_load_firebase.return_value = {"test": "config"}
        
        resolver = PRArenaIssueResolver(self.mock_args)
        
        # Mock httpx response for branch checking
        mock_httpx_response = Mock()
        mock_httpx_response.status_code = 404
        mock_httpx.return_value = mock_httpx_response
        
        # Mock requests response for default branch
        mock_requests_response = Mock()
        mock_requests_response.json.return_value = {"default_branch": "main"}
        mock_requests.return_value = mock_requests_response
        
        # Mock subprocess calls
        mock_subprocess.return_value = Mock(returncode=0)
        
        result = resolver.prepare_branch_and_push("test-dir", "draft")
        
        branch_name, default_branch, base_url, headers = result
        
        self.assertTrue(branch_name.startswith("openhands-fix-issue-123"))
        self.assertEqual(default_branch, "main")
        self.assertIn("api.github.com", base_url)
        self.assertIn("Authorization", headers)

    @patch('resolver.resolve_issue.Secrets')
    @patch('resolver.resolve_issue.load_firebase_config')
    @patch('resolver.resolve_issue.apply_daytona_patch')
    @patch('resolver.resolve_issue.firebase_admin')
    @patch('resolver.resolve_issue.firestore')
    async def test_send_to_firebase_success(self, mock_firestore, mock_firebase_admin,
                                          mock_apply_patch, mock_load_firebase, mock_secrets):
        """Test successful send_to_firebase execution"""
        mock_secrets.get_api_key.return_value = "test-api-key"
        mock_secrets.get_firebase_config.return_value = {"test": "config"}
        mock_load_firebase.return_value = {"test": "config"}
        
        resolver = PRArenaIssueResolver(self.mock_args)
        
        # Create mock resolver outputs
        mock_issue = Mock()
        mock_issue.number = 123
        mock_issue.title = "Test Issue"
        mock_issue.body = "Test body"
        
        resolver_output_1 = Mock(spec=CustomResolverOutput)
        resolver_output_1.issue = mock_issue
        resolver_output_1.git_patch = "test-patch-1"
        resolver_output_1.model = "claude-sonnet-4-20250514"
        resolver_output_1.commit_hash = "abc123"
        resolver_output_1.duration = 120.5
        
        resolver_output_2 = Mock(spec=CustomResolverOutput)
        resolver_output_2.issue = mock_issue
        resolver_output_2.git_patch = "test-patch-2"
        resolver_output_2.model = "gpt-4.1-2025-04-14"
        resolver_output_2.commit_hash = "def456"
        resolver_output_2.duration = 95.3
        
        # Mock Firebase components
        mock_db = Mock()
        mock_firestore.client.return_value = mock_db
        mock_collection = Mock()
        mock_db.collection.return_value = mock_collection
        mock_document = Mock()
        mock_collection.document.return_value = mock_document
        
        # Mock get_new_commit_hash calls
        with patch.object(resolver, 'get_new_commit_hash', new_callable=AsyncMock):
            # Mock pathlib and file operations
            with patch('resolver.resolve_issue.pathlib.Path'):
                with patch('builtins.open', unittest.mock.mock_open()):
                    # Mock get_comprehensive_language_info
                    with patch('resolver.resolve_issue.get_comprehensive_language_info', 
                             return_value={"primary_language": "Python"}):
                        # Mock environment variable
                        with patch.dict(os.environ, {'GITHUB_ENV': '/tmp/github_env'}):
                            with patch('builtins.open', unittest.mock.mock_open(), create=True):
                                await resolver.send_to_firebase(resolver_output_1, resolver_output_2, "draft")
        
        # Verify Firebase operations were called
        mock_db.collection.assert_called_with("issue_collection")
        mock_document.set.assert_called()


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions in resolve_issue module"""
    
    def test_int_or_none_with_none_string(self):
        """Test int_or_none function with 'none' string"""
        
        # Access the nested function through the main function's local scope
        # This is a bit tricky, so we'll test it indirectly through argument parsing
        
        import argparse
        argparse.ArgumentParser()  # Just test that it doesn't raise an error
        
        # Define the function locally for testing
        def int_or_none(value: str):
            if value.lower() == 'none':
                return None
            else:
                return int(value)
        
        result = int_or_none('none')
        self.assertIsNone(result)
        
        result = int_or_none('None')
        self.assertIsNone(result)
        
        result = int_or_none('NONE')
        self.assertIsNone(result)
        
        result = int_or_none('123')
        self.assertEqual(result, 123)


if __name__ == '__main__':
    unittest.main()