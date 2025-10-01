#!/usr/bin/env python3
"""
Test script for evaluating new LLM models with PR-Arena issue resolution.

This script allows testing a specific model against a GitHub issue to evaluate
its performance before adding it to the main model list.

Usage:
    python test_new_model.py --model-name "gpt-4o" --api-key "your-key" --github-token "github-token"
    
Example:
    python test_new_model.py\
        --model-name litellm_proxy/azure/gpt-5\
        --api-key sk-...\
        --github-token github_pat_...\
        --repo "JiseungHong/SYCON-Bench"\
        --issue-number 33
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from argparse import Namespace
from typing import Any
from unittest.mock import patch

# Import the resolver classes
from resolver.resolve_issue import PRArenaIssueResolver
from resolver.secrets import Secrets
from openhands.resolver.issue_handler_factory import IssueHandlerFactory
from openhands.integrations.service_types import ProviderType


def setup_logging(model_name: str) -> tuple[str, Path]:
    """Set up comprehensive logging and tracing for the model test."""
    # Create logs directory if it doesn't exist
    logs_dir = Path("model_test_logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Create log filename with model name and date
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model_name = model_name.replace('/', '_').replace('\\', '_')
    log_filename = f"{safe_model_name}_{timestamp}.log"
    log_path = logs_dir / log_filename
    
    # Create trace directory for this test run
    trace_dir = logs_dir / f"{safe_model_name}_{timestamp}_traces"
    trace_dir.mkdir(exist_ok=True)
    
    # Clear any existing root handlers to avoid conflicts
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Configure comprehensive logging with detailed format
    logging.basicConfig(
        level=logging.DEBUG,  # Enable debug level for comprehensive tracing
        format='%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_path, mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ],
        force=True  # Force reconfiguration
    )
    
    # Set up OpenHands specific logging
    openhands_logger = logging.getLogger('openhands')
    openhands_logger.setLevel(logging.DEBUG)
    
    # Enable detailed event logging
    # os.environ['DEBUG'] = 'true'
    # os.environ['LOG_ALL_EVENTS'] = 'true'
    # os.environ['LOG_LEVEL'] = 'DEBUG'
    # os.environ['DEBUG_RUNTIME'] = 'true'
    # os.environ['LOG_JSON'] = 'true'
    
    logger = logging.getLogger(__name__)
    logger.info("Starting comprehensive model test for: %s", model_name)
    logger.info("Log file: %s", log_path)
    logger.info("Trace directory: %s", trace_dir)
    logger.info("OpenHands debug mode enabled for detailed tracing")
    
    return str(log_path), trace_dir


def create_test_args(model_name: str, api_key: str, github_token: str, 
                    repo: str, issue_number: int, github_username: str, trace_dir: Path) -> Namespace:
    """Create the arguments namespace for PRArenaIssueResolver."""
    
    # Set up output directory for this test (use trace_dir parent for consistency)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model_name = model_name.replace('/', '_').replace('\\', '_')
    output_dir = f"test_output_{safe_model_name}_{timestamp}"
    
    # Store trace directory for later use
    trace_dir_str = str(trace_dir)
    
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
        trace_dir=trace_dir_str,  # Add trace directory
        
        # Optional settings
        prompt_file=None,
        repo_instruction_file=None,
        base_domain=None,
    )
    
    return args


def save_detailed_traces(output_dir: str, trace_dir: Path, model_name: str, 
                        issue_number: int, result: Any) -> None:
    """Save detailed execution traces and artifacts."""
    logger = logging.getLogger(__name__)
    
    try:
        # Copy all output files to trace directory
        output_path = Path(output_dir)
        if output_path.exists():
            print(f"Copying output artifacts from {output_path} to {trace_dir}")
            
            # Copy the entire output directory structure
            shutil.copytree(output_path, trace_dir / "output", dirs_exist_ok=True)
            
            # Create a comprehensive trace summary
            trace_summary = {
                "model_name": model_name,
                "issue_number": issue_number,
                "timestamp": datetime.now().isoformat(),
                "success": result.success if result else False,
                "output_directory": output_dir,
                "trace_directory": str(trace_dir),
                "artifacts": {
                    "output_jsonl": str(trace_dir / "output" / "output.jsonl") if (trace_dir / "output" / "output.jsonl").exists() else None,
                    "repo_clone": str(trace_dir / "output" / "repo") if (trace_dir / "output" / "repo").exists() else None,
                    "inference_logs": str(trace_dir / "output" / "infer_logs") if (trace_dir / "output" / "infer_logs").exists() else None,
                }
            }
            
            if result:
                trace_summary.update({
                    "git_patch_length": len(result.git_patch) if result.git_patch else 0,
                    "has_git_patch": bool(result.git_patch),
                    "duration": result.duration if hasattr(result, 'duration') else None,
                    "accumulated_cost": result.accumulated_cost if hasattr(result, 'accumulated_cost') else None,
                    "result_explanation": result.result_explanation if hasattr(result, 'result_explanation') else None,
                    "error": result.error if hasattr(result, 'error') else None,
                })
            
            # Save trace summary
            with open(trace_dir / "trace_summary.json", 'w') as f:
                json.dump(trace_summary, f, indent=2)
            
            print(f"Trace summary saved to {trace_dir / 'trace_summary.json'}")
            
            # Extract and save conversation history if available
            if result and hasattr(result, 'history'):
                history_file = trace_dir / "conversation_history.jsonl"
                with open(history_file, 'w') as f:
                    for event in result.history:
                        f.write(json.dumps(event) + '\n')
                print(f"Conversation history saved to {history_file}")
            
            # Save git patch separately if it exists
            if result and hasattr(result, 'git_patch') and result.git_patch:
                patch_file = trace_dir / "git_patch.diff"
                with open(patch_file, 'w') as f:
                    f.write(result.git_patch)
                print(f"Git patch saved to {patch_file}")
                
            # Also save git patch to a clearly visible JSON file in the trace directory
            if result and hasattr(result, 'git_patch') and result.git_patch:
                visible_output = {
                    "model_name": model_name,
                    "issue_number": issue_number,
                    "timestamp": datetime.now().isoformat(),
                    "success": result.success if result else False,
                    "git_patch": result.git_patch,
                    "result_explanation": result.result_explanation if hasattr(result, 'result_explanation') else None,
                    "error": result.error if hasattr(result, 'error') else None
                }
                
                visible_file = trace_dir / "result_output.json"
                with open(visible_file, 'w') as f:
                    json.dump(visible_output, f, indent=2)
                print(f"Visible result output saved to {visible_file}")
                
        else:
            logger.warning(f"Output directory {output_path} does not exist - no artifacts to save")
            
    except Exception as e:
        logger.error(f"Failed to save detailed traces: {str(e)}", exc_info=True)


async def test_model_resolution(model_name: str, api_key: str, github_token: str,
                               repo: str, issue_number: int, github_username: str, trace_dir: Path) -> None:
    """Test a specific model's ability to resolve a GitHub issue."""

    logger = logging.getLogger(__name__)

    # Set environment variables BEFORE any imports or initialization
    # These will be inherited by the Docker container
    os.environ['LLM_API_KEY'] = api_key
    os.environ['LITELLM_API_KEY'] = api_key
    os.environ['OPENAI_API_KEY'] = api_key  # OpenHands might use this

    # Also set the base URL
    os.environ['LLM_BASE_URL'] = 'https://cmu.litellm.ai'

    # Mock function that returns the API key
    def mock_get_api_key(cls=None):
        logger.debug(f"Mock get_api_key called, returning API key: {api_key[:10]}...")
        return api_key

    try:
        # Patch Secrets.get_api_key BEFORE creating the resolver
        # This ensures the mock is active throughout the entire lifecycle
        with patch.object(Secrets, 'get_api_key', classmethod(mock_get_api_key)):
            # Set up the GitHub token for repository access
            Secrets.TOKEN = github_token

            logger.info(f"API key mock is active: {api_key[:10]}...")

            # Create test arguments
            args = create_test_args(model_name, api_key, github_token, repo, issue_number, github_username, trace_dir)

            print(f"Testing model: {model_name}")
            print(f"Repository: {repo}")
            print(f"Issue number: {issue_number}")
            print(f"Output directory: {args.output_dir}")

            # Initialize the resolver (now with patched Secrets.get_api_key)
            print("Initializing PRArenaIssueResolver...")
            resolver = PRArenaIssueResolver(args)

            # Set up the issue handler (required for resolve_issue)
            print("Setting up issue handler...")
            llm_config = resolver.llm_configs[0]  # Use first available model
            resolver.llm_config = llm_config

            # Verify API key is set in llm_config
            if hasattr(llm_config, 'api_key') and llm_config.api_key:
                logger.info(f"LLM Config API key: {str(llm_config.api_key)[:20]}...")
            else:
                logger.warning("LLM Config has no API key set!")

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
            print("Starting issue resolution...")
            start_time = datetime.now()

            # Use resolve_issue() instead of resolve_issues_with_random_models()
            # since we want to test a single specific model
            result = await resolver.resolve_issue()

            end_time = datetime.now()
            duration = end_time - start_time

            # Log results
            print(f"Resolution completed in {duration}")
            print(f"Success: {result.success if result else 'Unknown'}")

            if result:
                print(f"Result explanation: {result.result_explanation}")
                print(f"Git patch generated: {'Yes' if result.git_patch else 'No'}")
                if result.git_patch:
                    print(f"Patch length: {len(result.git_patch)} characters")
                    # Log first few lines of patch for quick preview
                    patch_lines = result.git_patch.split('\n')[:10]
                    print(f"Patch preview (first 10 lines):\n{chr(10).join(patch_lines)}")

                # Log cost information if available
                if hasattr(result, 'accumulated_cost') and result.accumulated_cost:
                    print(f"Total cost: ${result.accumulated_cost:.4f}")

                # Log token usage if available
                if hasattr(result, 'token_usage') and result.token_usage:
                    print(f"Token usage: {result.token_usage}")

                # Log any errors
                if result.error:
                    print(f"Error occurred: {result.error}")
            else:
                print("No result returned from resolver")

            # Persist the resolver output for later inspection
            resolver_output_file = Path(args.output_dir) / "resolver_output.txt"
            try:
                resolver_output_file.parent.mkdir(parents=True, exist_ok=True)
                with resolver_output_file.open("w", encoding="utf-8") as f:
                    if result:
                        json.dump(result.model_dump(), f, indent=2)
                    else:
                        f.write("Resolver returned no result.\n")
                print(f"Resolver output saved to {resolver_output_file}")
            except Exception as write_err:
                print(
                    f"Failed to write resolver output to {resolver_output_file}: {write_err}",
                )

            # Save detailed traces and artifacts
            print("Saving detailed execution traces...")
            save_detailed_traces(args.output_dir, trace_dir, model_name, issue_number, result)
            print(f"All traces and artifacts saved to: {trace_dir}")

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
        default="JiseungHong/SYCON-Bench",
        help="GitHub repository in format 'owner/repo' (default: JiseungHong/SYCON-Bench)"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        default=33,
        help="Issue number to test resolution on (default: 33)"
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
    
    # Set up comprehensive logging and tracing
    log_file, trace_dir = setup_logging(args.model_name)
    
    # Create .gitignore entries
    create_gitignore()
    
    print(f"Starting model test for: {args.model_name}")
    print(f"Repository: {args.repo}")
    print(f"Issue: #{args.issue_number}")
    print(f"Logs will be written to: {log_file}")
    print(f"Traces and artifacts will be saved to: {trace_dir}")
    print("-" * 50)
    
    try:
        # Run the async test
        asyncio.run(test_model_resolution(
            model_name=args.model_name,
            api_key=args.api_key,
            github_token=args.github_token,
            repo=args.repo,
            issue_number=args.issue_number,
            github_username=github_username,
            trace_dir=trace_dir
        ))
        
        print("-" * 50)
        print("✅ Model test completed successfully!")
        print(f"Check the log file for detailed results: {log_file}")
        print(f"Check the trace directory for execution artifacts: {trace_dir}")
        print("\nTrace contents:")
        if trace_dir.exists():
            for item in sorted(trace_dir.iterdir()):
                if item.is_file():
                    print(f"  📄 {item.name}")
                elif item.is_dir():
                    print(f"  📁 {item.name}/")
        
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        print(f"Check the log file for details: {log_file}")
        print(f"Check the trace directory for debugging info: {trace_dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()
