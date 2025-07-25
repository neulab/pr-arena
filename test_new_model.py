#!/usr/bin/env python3
"""
Test script for evaluating new LLM models with PR-Arena issue resolution.

This script allows testing a specific model against a GitHub issue to evaluate
its performance before adding it to the main model list.

Usage:
    python test_new_model.py --model-name "gpt-4o" --api-key "your-key" --github-token "github-token"
    
Example:
    python test_new_model.py \
        --model-name "claude-3-5-sonnet-20241022" \
        --api-key "sk-ant-..." \
        --github-token "ghp_..." \
        --repo "JiseungHong/web-hosting-gravisu" \
        --issue-number 78
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from argparse import Namespace

# Import the resolver classes
from resolver.resolve_issue import PRArenaIssueResolver
from resolver.secrets import Secrets
from openhands.resolver.issue_handler_factory import IssueHandlerFactory
from openhands.integrations.service_types import ProviderType


def setup_logging(model_name: str) -> str:
    """Set up logging to a separate file for the model test."""
    # Create logs directory if it doesn't exist
    logs_dir = Path("model_test_logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Create log filename with model name and date
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{model_name.replace('/', '_')}_{timestamp}.log"
    log_path = logs_dir / log_filename
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout)  # Also log to console
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting model test for: {model_name}")
    logger.info(f"Log file: {log_path}")
    
    return str(log_path)


def create_test_args(model_name: str, api_key: str, github_token: str, 
                    repo: str, issue_number: int, github_username: str) -> Namespace:
    """Create the arguments namespace for PRArenaIssueResolver."""
    
    # Set up output directory for this test
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output_{model_name.replace('/', '_')}_{timestamp}"
    
    args = Namespace(
        # Repository and issue settings
        selected_repo=repo,
        issue_number=issue_number,
        comment_id=None,
        issue_type='issue',
        
        # Authentication
        token=github_token,
        username=github_username,
        
        # Model configuration
        llm_models=f"{model_name}, {model_name}",  # Single model for testing
        llm_api_key=api_key,
        llm_base_url="https://cmu.litellm.ai",  # Use default
        
        # Container settings (use defaults)
        base_container_image=None,
        runtime_container_image=None,
        is_experimental=False,
        
        # Output settings
        output_dir=output_dir,
        max_iterations=50,
        
        # Optional settings
        prompt_file=None,
        repo_instruction_file=None,
        base_domain=None,
    )
    
    return args


async def test_model_resolution(model_name: str, api_key: str, github_token: str,
                               repo: str, issue_number: int, github_username: str) -> None:
    """Test a specific model's ability to resolve a GitHub issue."""
    
    logger = logging.getLogger(__name__)
    
    try:
        # Set up the GitHub token for repository access
        Secrets.TOKEN = github_token
        
        # Mock the get_api_key method to return our provided API key
        # This bypasses the Firebase Function call for testing
        def mock_get_api_key(cls):
            return api_key
        
        # Replace the class method with our mock
        setattr(Secrets, 'get_api_key', classmethod(mock_get_api_key))
        
        # Also set environment variable as fallback
        os.environ['LLM_API_KEY'] = api_key
        
        # Create test arguments
        args = create_test_args(model_name, api_key, github_token, repo, issue_number, github_username)
        
        logger.info(f"Testing model: {model_name}")
        logger.info(f"Repository: {repo}")
        logger.info(f"Issue number: {issue_number}")
        logger.info(f"Output directory: {args.output_dir}")
        
        # Initialize the resolver
        logger.info("Initializing PRArenaIssueResolver...")
        resolver = PRArenaIssueResolver(args)
        
        # Set up the issue handler (required for resolve_issue)
        logger.info("Setting up issue handler...")
        llm_config = resolver.llm_configs[0]  # Use first available model
        resolver.llm_config = llm_config
        
        factory = IssueHandlerFactory(
            owner=resolver.owner,
            repo=resolver.repo,
            token=resolver.token,
            username=resolver.username,
            platform=ProviderType.GITHUB,
            base_domain='github.com',
            issue_type=resolver.issue_type,
            llm_config=llm_config,
        )
        resolver.issue_handler = factory.create()
        resolver.output_dir = args.output_dir
        
        # Run the resolution test
        logger.info("Starting issue resolution...")
        start_time = datetime.now()
        
        # Use resolve_issue() instead of resolve_issues_with_random_models()
        # since we want to test a single specific model
        result = await resolver.resolve_issue()
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Log results
        logger.info(f"Resolution completed in {duration}")
        logger.info(f"Success: {result.success if result else 'Unknown'}")
        
        if result:
            logger.info(f"Result explanation: {result.result_explanation}")
            logger.info(f"Git patch generated: {'Yes' if result.git_patch else 'No'}")
            if result.git_patch:
                logger.info(f"Patch length: {len(result.git_patch)} characters")
            
            # Log any errors
            if result.error:
                logger.warning(f"Error occurred: {result.error}")
        else:
            logger.error("No result returned from resolver")
            
    except Exception as e:
        logger.error(f"Test failed with exception: {str(e)}", exc_info=True)
        raise


def create_gitignore():
    """Create or update .gitignore to exclude test directories."""
    gitignore_path = Path(".gitignore")
    
    entries_to_add = [
        "# Model testing directories",
        "model_test_logs/",
        "test_output_*/",
    ]
    
    # Read existing gitignore
    existing_lines = []
    if gitignore_path.exists():
        existing_lines = gitignore_path.read_text().splitlines()
    
    # Add new entries if they don't exist
    lines_to_add = []
    for entry in entries_to_add:
        if entry not in existing_lines:
            lines_to_add.append(entry)
    
    if lines_to_add:
        with gitignore_path.open("a") as f:
            if existing_lines and not existing_lines[-1].strip():
                pass  # Already has blank line
            else:
                f.write("\n")
            f.write("\n".join(lines_to_add) + "\n")
        print(f"Updated .gitignore with {len(lines_to_add)} new entries")


def main():
    parser = argparse.ArgumentParser(
        description="Test a new LLM model's performance on GitHub issue resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required arguments
    parser.add_argument(
        "--model-name",
        type=str,
        required=True,
        help="Name of the LLM model to test (e.g., 'claude-3-5-sonnet-20241022')"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get('LLM_API_KEY'),
        help="API key for the LLM model (can also use LLM_API_KEY environment variable)"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=os.environ.get('GITHUB_TOKEN'),
        help="GitHub token with repository access permissions (can also use GITHUB_TOKEN environment variable)"
    )
    
    # Optional arguments with defaults
    parser.add_argument(
        "--repo",
        type=str,
        default="JiseungHong/web-hosting-gravisu",
        help="GitHub repository in format 'owner/repo' (default: JiseungHong/web-hosting-gravisu)"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        default=78,
        help="Issue number to test resolution on (default: 78)"
    )
    parser.add_argument(
        "--github-username",
        type=str,
        help="GitHub username (will be inferred from token if not provided)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.model_name or not args.model_name.strip():
        print("Error: Model name cannot be empty")
        sys.exit(1)
    
    if not args.api_key or not args.api_key.strip():
        print("Error: API key is required. Provide via --api-key or LLM_API_KEY environment variable")
        sys.exit(1)
        
    if not args.github_token or not args.github_token.strip():
        print("Error: GitHub token is required. Provide via --github-token or GITHUB_TOKEN environment variable")
        sys.exit(1)
    
    # Default username if not provided
    github_username = args.github_username or "pr-arena-tester"
    
    # Set up logging
    log_file = setup_logging(args.model_name)
    
    # Create .gitignore entries
    create_gitignore()
    
    print(f"Starting model test for: {args.model_name}")
    print(f"Repository: {args.repo}")
    print(f"Issue: #{args.issue_number}")
    print(f"Logs will be written to: {log_file}")
    print("-" * 50)
    
    try:
        # Run the async test
        asyncio.run(test_model_resolution(
            model_name=args.model_name,
            api_key=args.api_key,
            github_token=args.github_token,
            repo=args.repo,
            issue_number=args.issue_number,
            github_username=github_username
        ))
        
        print("-" * 50)
        print("✅ Model test completed successfully!")
        print(f"Check the log file for detailed results: {log_file}")
        
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        print(f"Check the log file for details: {log_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()