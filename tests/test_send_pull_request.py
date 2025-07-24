import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, mock_open

# Import the functions and classes we want to test
from resolver.send_pull_request import (
    load_all_resolver_outputs,
    load_single_resolver_output,
    apply_patch,
    initialize_repo,
    make_commit,
    make_commit_with_summary,
    send_pull_request,
    process_single_issue
)
from resolver.resolver_output import CustomResolverOutput
from openhands.integrations.service_types import ProviderType
from openhands.resolver.interfaces.issue import Issue


class TestLoadFunctions(unittest.TestCase):
    """Test cases for loading resolver outputs"""

    def setUp(self):
        """Set up test data"""
        self.test_data = [
            {
                "issue": {"owner": "test", "repo": "test", "number": 1, "title": "Test 1", "body": "Body 1"},
                "issue_type": "issue",
                "instruction": "Test instruction 1",
                "base_commit": "abc123",
                "git_patch": "test patch 1",
                "history": [],
                "metrics": {},
                "success": True,
                "comment_success": None,
                "result_explanation": "Test explanation 1",
                "error": None,
                "model": "test-model",
                "duration": 120.5
            },
            {
                "issue": {"owner": "test", "repo": "test", "number": 2, "title": "Test 2", "body": "Body 2"},
                "issue_type": "issue",
                "instruction": "Test instruction 2",
                "base_commit": "def456",
                "git_patch": "test patch 2",
                "history": [],
                "metrics": {},
                "success": True,
                "comment_success": None,
                "result_explanation": "Test explanation 2",
                "error": None,
                "model": "test-model-2",
                "duration": 95.3
            }
        ]

    def test_load_all_resolver_outputs(self):
        """Test loading all resolver outputs from JSONL file"""
        test_content = '\n'.join(json.dumps(item) for item in self.test_data)
        
        with patch('builtins.open', mock_open(read_data=test_content)):
            outputs = list(load_all_resolver_outputs('test.jsonl'))
            
        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0].issue.number, 1)
        self.assertEqual(outputs[1].issue.number, 2)

    def test_load_single_resolver_output_found(self):
        """Test loading a specific issue number that exists"""
        test_content = '\n'.join(json.dumps(item) for item in self.test_data)
        
        with patch('builtins.open', mock_open(read_data=test_content)):
            output = load_single_resolver_output('test.jsonl', 2)
            
        self.assertEqual(output.issue.number, 2)
        self.assertEqual(output.issue.title, "Test 2")

    def test_load_single_resolver_output_not_found(self):
        """Test loading a specific issue number that doesn't exist"""
        test_content = '\n'.join(json.dumps(item) for item in self.test_data)
        
        with patch('builtins.open', mock_open(read_data=test_content)):
            with self.assertRaises(ValueError) as context:
                load_single_resolver_output('test.jsonl', 999)
            
            self.assertIn("Issue number 999 not found", str(context.exception))


class TestApplyPatch(unittest.TestCase):
    """Test cases for apply_patch function"""

    def setUp(self):
        """Set up temporary directory for testing"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.test_dir)

    @patch('resolver.send_pull_request.parse_patch')
    @patch('resolver.send_pull_request.apply_diff')
    def test_apply_patch_new_file(self, mock_apply_diff, mock_parse_patch):
        """Test applying patch that creates a new file"""
        # Mock patch parsing
        mock_diff = Mock()
        mock_diff.header.old_path = None
        mock_diff.header.new_path = 'b/new_file.txt'
        mock_diff.changes = [{'type': 'add', 'content': 'new content'}]
        mock_parse_patch.return_value = [mock_diff]
        mock_apply_diff.return_value = ['line1', 'line2']
        
        patch_content = "diff --git a/new_file.txt b/new_file.txt"
        
        apply_patch(self.test_dir, patch_content)
        
        mock_parse_patch.assert_called_once_with(patch_content)
        mock_apply_diff.assert_called_once()

    @patch('resolver.send_pull_request.parse_patch')
    def test_apply_patch_delete_file(self, mock_parse_patch):
        """Test applying patch that deletes a file"""
        # Create a test file
        test_file = os.path.join(self.test_dir, 'delete_me.txt')
        with open(test_file, 'w') as f:
            f.write('content to delete')
        
        # Mock patch parsing for deletion
        mock_diff = Mock()
        mock_diff.header.old_path = 'a/delete_me.txt'
        mock_diff.header.new_path = '/dev/null'
        mock_diff.changes = None
        mock_parse_patch.return_value = [mock_diff]
        
        patch_content = "diff --git a/delete_me.txt b/delete_me.txt"
        
        apply_patch(self.test_dir, patch_content)
        
        self.assertFalse(os.path.exists(test_file))

    @patch('resolver.send_pull_request.parse_patch')
    @patch('resolver.send_pull_request.apply_diff')
    def test_apply_patch_modify_file(self, mock_apply_diff, mock_parse_patch):
        """Test applying patch that modifies an existing file"""
        # Create a test file
        test_file = os.path.join(self.test_dir, 'modify_me.txt')
        with open(test_file, 'w') as f:
            f.write('original content\n')
        
        # Mock patch parsing for modification
        mock_diff = Mock()
        mock_diff.header.old_path = 'a/modify_me.txt'
        mock_diff.header.new_path = 'b/modify_me.txt'
        mock_diff.changes = [{'type': 'modify'}]
        mock_parse_patch.return_value = [mock_diff]
        mock_apply_diff.return_value = ['modified content']
        
        patch_content = "diff --git a/modify_me.txt b/modify_me.txt"
        
        apply_patch(self.test_dir, patch_content)
        
        mock_parse_patch.assert_called_once_with(patch_content)
        mock_apply_diff.assert_called_once()


class TestInitializeRepo(unittest.TestCase):
    """Test cases for initialize_repo function"""

    def setUp(self):
        """Set up temporary directories for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.temp_dir, 'output')
        self.repo_dir = os.path.join(self.output_dir, 'repo')
        os.makedirs(self.repo_dir)
        
        # Create a test file in repo
        with open(os.path.join(self.repo_dir, 'test.txt'), 'w') as f:
            f.write('test content')

    def tearDown(self):
        """Clean up temporary directories"""
        shutil.rmtree(self.temp_dir)

    def test_initialize_repo_success(self):
        """Test successful repository initialization"""
        dest_dir = initialize_repo(self.output_dir, 123, 'issue')
        
        expected_dest = os.path.join(self.output_dir, 'patches', 'issue_123')
        self.assertEqual(dest_dir, expected_dest)
        self.assertTrue(os.path.exists(expected_dest))
        self.assertTrue(os.path.exists(os.path.join(expected_dest, 'test.txt')))

    def test_initialize_repo_nonexistent_source(self):
        """Test initialization with nonexistent source directory"""
        with self.assertRaises(ValueError) as context:
            initialize_repo('/nonexistent', 123, 'issue')
        
        self.assertIn("does not exist", str(context.exception))

    @patch('resolver.send_pull_request.subprocess.run')
    def test_initialize_repo_with_base_commit(self, mock_subprocess):
        """Test initialization with base commit checkout"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        dest_dir = initialize_repo(self.output_dir, 123, 'issue', 'abc123')
        
        expected_dest = os.path.join(self.output_dir, 'patches', 'issue_123')
        self.assertEqual(dest_dir, expected_dest)
        mock_subprocess.assert_called_once()

    @patch('resolver.send_pull_request.subprocess.run')
    def test_initialize_repo_checkout_failure(self, mock_subprocess):
        """Test initialization with failed commit checkout"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "commit not found"
        mock_subprocess.return_value = mock_result
        
        with self.assertRaises(RuntimeError) as context:
            initialize_repo(self.output_dir, 123, 'issue', 'invalid_commit')
        
        self.assertIn("Failed to check out commit", str(context.exception))


class TestMakeCommit(unittest.TestCase):
    """Test cases for make_commit function"""

    def setUp(self):
        """Set up test data"""
        self.mock_issue = Mock(spec=Issue)
        self.mock_issue.number = 123
        self.mock_issue.title = "Test Issue"

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_success(self, mock_subprocess):
        """Test successful commit creation"""
        # Mock subprocess calls - need to use a single side_effect generator function
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args):
                return Mock(returncode=0, stdout="")
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="M file.txt")
            elif 'commit' in str(args):
                return Mock(returncode=0)
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        make_commit("/test/repo", self.mock_issue, "issue")
        
        # Verify git commands were called
        self.assertGreaterEqual(mock_subprocess.call_count, 4)

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_no_changes(self, mock_subprocess):
        """Test commit creation when no changes exist"""
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args):
                return Mock(returncode=0, stdout="openhands")
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="")  # No changes
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        with self.assertRaises(RuntimeError) as context:
            make_commit("/test/repo", self.mock_issue, "issue")
        
        self.assertIn("Openhands failed to make code changes", str(context.exception))

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_with_git_config(self, mock_subprocess):
        """Test commit creation with git user configuration"""
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args) and 'config user.email' not in str(args):
                return Mock(returncode=0, stdout="")  # Empty username
            elif 'config user.name' in str(args) and 'config user.email' in str(args):
                return Mock(returncode=0)  # git config setup
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="M file.txt")
            elif 'commit' in str(args):
                return Mock(returncode=0)
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        make_commit("/test/repo", self.mock_issue, "issue")
        
        self.assertGreaterEqual(mock_subprocess.call_count, 4)


class TestMakeCommitWithSummary(unittest.TestCase):
    """Test cases for make_commit_with_summary function"""

    def setUp(self):
        """Set up test data"""
        self.mock_issue = Mock(spec=Issue)
        self.mock_issue.number = 123
        self.mock_issue.title = "Test Issue"
        
        self.mock_resolver_output = Mock(spec=CustomResolverOutput)
        self.mock_resolver_output.result_explanation = '["Fixed bug A", "Added feature B"]'
        self.mock_resolver_output.duration = 120.5

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_with_summary_success(self, mock_subprocess):
        """Test successful commit with summary"""
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args):
                return Mock(returncode=0, stdout="openhands")
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="M file.txt")
            elif 'commit' in str(args):
                return Mock(returncode=0)
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        make_commit_with_summary("/test/repo", self.mock_issue, "issue", 
                               self.mock_resolver_output, "test-branch", "output1")
        
        # Verify commit was called with enhanced message
        # Find the commit call
        commit_calls = [call for call in mock_subprocess.call_args_list if 'commit' in str(call)]
        self.assertGreater(len(commit_calls), 0)
        
        # Check if the commit message contains expected content
        commit_call = commit_calls[-1]
        commit_message = commit_call[0][0][-1]  # Last argument of git commit command
        
        self.assertIn("Fix issue #123 with 1st Model", commit_message)
        self.assertIn("Summary of Changes:", commit_message)
        self.assertIn("Duration: 2m 0s", commit_message)

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_with_summary_invalid_model(self, mock_subprocess):
        """Test commit with invalid model number"""
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args):
                return Mock(returncode=0, stdout="openhands")
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="M file.txt")
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        with self.assertRaises(ValueError) as context:
            make_commit_with_summary("/test/repo", self.mock_issue, "issue", 
                                   self.mock_resolver_output, "test-branch", "output3")
        
        self.assertIn("Invalid model number", str(context.exception))

    @patch('resolver.send_pull_request.subprocess.run')
    def test_make_commit_with_summary_json_explanation(self, mock_subprocess):
        """Test commit with JSON explanation"""
        def mock_subprocess_calls(*args, **kwargs):
            if 'config user.name' in str(args):
                return Mock(returncode=0, stdout="openhands")
            elif 'add .' in str(args):
                return Mock(returncode=0)
            elif 'status --porcelain' in str(args):
                return Mock(returncode=0, stdout="M file.txt")
            elif 'commit' in str(args):
                return Mock(returncode=0)
            else:
                return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_subprocess_calls
        
        self.mock_resolver_output.result_explanation = '["Fixed authentication bug", "Updated UI components"]'
        
        make_commit_with_summary("/test/repo", self.mock_issue, "issue", 
                               self.mock_resolver_output, "test-branch", "output2")
        
        # Find the commit call
        commit_calls = [call for call in mock_subprocess.call_args_list if 'commit' in str(call)]
        self.assertGreater(len(commit_calls), 0)
        
        commit_call = commit_calls[-1]
        commit_message = commit_call[0][0][-1]
        
        self.assertIn("1. Fixed authentication bug", commit_message)
        self.assertIn("2. Updated UI components", commit_message)


class TestSendPullRequest(unittest.TestCase):
    """Test cases for send_pull_request function"""

    def setUp(self):
        """Set up test data"""
        self.mock_issue = Mock(spec=Issue)
        self.mock_issue.owner = "test-owner"
        self.mock_issue.repo = "test-repo"
        self.mock_issue.number = 123
        self.mock_issue.title = "Test Issue"
        
        self.mock_resolver_output = Mock(spec=CustomResolverOutput)
        self.mock_resolver_output.branch_name = "test-branch"
        self.mock_resolver_output.result_explanation = "Test explanation"

    def test_send_pull_request_invalid_pr_type(self):
        """Test send_pull_request with invalid pr_type"""
        with self.assertRaises(ValueError) as context:
            send_pull_request(
                self.mock_issue, "token", "user", ProviderType.GITHUB,
                self.mock_resolver_output, "invalid_type"
            )
        
        self.assertIn("Invalid pr_type", str(context.exception))

    @patch('resolver.send_pull_request.ServiceContextIssue')
    @patch('resolver.send_pull_request.GithubIssueHandler')
    def test_send_pull_request_success(self, mock_github_handler, mock_service_context):
        """Test successful pull request creation"""
        # Mock handler and its methods
        mock_handler_instance = Mock()
        mock_github_handler.return_value = mock_handler_instance
        
        mock_service_instance = Mock()
        mock_service_context.return_value = mock_service_instance
        mock_service_instance.get_default_branch_name.return_value = "main"
        mock_service_instance.create_pull_request.return_value = {
            'html_url': 'https://github.com/test/test/pull/1',
            'number': 1
        }
        
        result = send_pull_request(
            self.mock_issue, "token", "user", ProviderType.GITHUB,
            self.mock_resolver_output, "draft"
        )
        
        self.assertEqual(result, 'https://github.com/test/test/pull/1')
        mock_service_instance.create_pull_request.assert_called_once()

    @patch('resolver.send_pull_request.ServiceContextIssue')
    @patch('resolver.send_pull_request.GithubIssueHandler')
    def test_send_pull_request_with_reviewer(self, mock_github_handler, mock_service_context):
        """Test pull request creation with reviewer"""
        mock_handler_instance = Mock()
        mock_github_handler.return_value = mock_handler_instance
        
        mock_service_instance = Mock()
        mock_service_context.return_value = mock_service_instance
        mock_service_instance.get_default_branch_name.return_value = "main"
        mock_service_instance.create_pull_request.return_value = {
            'html_url': 'https://github.com/test/test/pull/1',
            'number': 1
        }
        
        send_pull_request(
            self.mock_issue, "token", "user", ProviderType.GITHUB,
            self.mock_resolver_output, "ready", reviewer="reviewer-user"
        )
        
        mock_service_instance.request_reviewers.assert_called_once_with("reviewer-user", 1)


class TestProcessSingleIssue(unittest.TestCase):
    """Test cases for process_single_issue function"""

    def setUp(self):
        """Set up test data"""
        self.mock_issue = Mock(spec=Issue)
        self.mock_issue.owner = "test-owner"
        self.mock_issue.repo = "test-repo"
        self.mock_issue.number = 123
        self.mock_issue.title = "Test Issue"
        
        self.mock_resolver_output = Mock(spec=CustomResolverOutput)
        self.mock_resolver_output.issue = self.mock_issue
        self.mock_resolver_output.issue_type = "issue"
        self.mock_resolver_output.success = True
        self.mock_resolver_output.branch_name = "test-branch"
        self.mock_resolver_output.result_explanation = "Test explanation"

    def test_process_single_issue_invalid_type(self):
        """Test process_single_issue with invalid issue type"""
        self.mock_resolver_output.issue_type = "pr"
        
        with self.assertRaises(ValueError) as context:
            process_single_issue(
                "output1", self.mock_resolver_output, "token", "user",
                ProviderType.GITHUB, "draft", None, None, False
            )
        
        self.assertIn("Invalid issue type", str(context.exception))

    @patch('resolver.send_pull_request.send_pull_request')
    def test_process_single_issue_success(self, mock_send_pr):
        """Test successful single issue processing"""
        mock_send_pr.return_value = "https://github.com/test/test/pull/1"
        
        process_single_issue(
            "output1", self.mock_resolver_output, "token", "user",
            ProviderType.GITHUB, "draft", None, None, False
        )
        
        mock_send_pr.assert_called_once()

    def test_process_single_issue_failed_no_send(self):
        """Test processing failed issue without send_on_failure"""
        self.mock_resolver_output.success = False
        
        with patch('resolver.send_pull_request.send_pull_request') as mock_send_pr:
            process_single_issue(
                "output1", self.mock_resolver_output, "token", "user",
                ProviderType.GITHUB, "draft", None, None, False
            )
            
            mock_send_pr.assert_not_called()

    @patch('resolver.send_pull_request.send_pull_request')
    def test_process_single_issue_failed_with_send(self, mock_send_pr):
        """Test processing failed issue with send_on_failure=True"""
        self.mock_resolver_output.success = False
        mock_send_pr.return_value = "https://github.com/test/test/pull/1"
        
        process_single_issue(
            "output1", self.mock_resolver_output, "token", "user",
            ProviderType.GITHUB, "draft", None, None, True
        )
        
        mock_send_pr.assert_called_once()


if __name__ == '__main__':
    unittest.main()