#!/usr/bin/env python3
"""
Prompt Experiment Runner - Test different prompts for PR-Arena issue resolution.

This script allows testing different prompt templates to optimize agent behavior.
Results are organized by repo/issue/model/prompt for easy comparison.

Usage:
    python run_experiment.py --model-name "litellm_proxy/neulab/gemini-2.5-pro" \\
                            --api-key "your-key" \\
                            --github-token "token" \\
                            --repo "JiseungHong/SYCON-Bench" \\
                            --issue-number 33 \\
                            --prompt "basic_prompt"
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

import jinja2
import litellm

# Add parent directories to path to import resolver
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from resolver.resolve_issue import PRArenaIssueResolver
from resolver.secrets import Secrets
from openhands.resolver.issue_handler_factory import IssueHandlerFactory
from openhands.integrations.service_types import ProviderType


def setup_logging(output_dir: Path) -> None:
    """Set up logging to console and file."""
    log_file = output_dir / "experiment.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def cleanup_heavy_artifacts(output_dir: Path) -> None:
    """Remove heavy artifacts (repo/, workspace/, infer_logs/, experiment.log) after experiment.

    Args:
        output_dir: Experiment output directory
    """
    logger = logging.getLogger(__name__)

    artifacts = ['repo', 'workspace', 'infer_logs', 'experiment.log']

    for artifact in artifacts:
        artifact_path = output_dir / artifact
        if artifact_path.exists():
            try:
                if artifact_path.is_dir():
                    shutil.rmtree(artifact_path)
                else:
                    artifact_path.unlink()
                logger.info(f"Cleaned up: {artifact_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up {artifact_path}: {e}")


def filter_binary_files_from_patch(patch: str) -> str:
    """Filter out binary files and .pyc files from git patch.

    Args:
        patch: Git patch content

    Returns:
        Filtered patch without binary files
    """
    if not patch:
        return patch

    lines = patch.split('\n')
    filtered_lines = []
    skip_file = False
    in_file = False

    for i, line in enumerate(lines):
        # Check for new file diff
        if line.startswith('diff --git'):
            # Check if this is a binary file or .pyc
            file_path = line.split()[-1] if len(line.split()) > 2 else ''

            # Look ahead for binary file markers
            skip_file = False
            if file_path.endswith('.pyc') or file_path.endswith('.pyo'):
                skip_file = True
            else:
                # Check next few lines for binary marker
                for j in range(i, min(i + 10, len(lines))):
                    if 'Binary files' in lines[j] or 'GIT binary patch' in lines[j]:
                        skip_file = True
                        break

            in_file = True
            if not skip_file:
                filtered_lines.append(line)
        elif line.startswith('diff --git') == False and in_file:
            if not skip_file:
                filtered_lines.append(line)
        else:
            if not skip_file:
                filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def shorten_issue_body_with_llm(
    issue_title: str,
    issue_body: str,
    model_name: str,
    api_key: str,
    base_url: str
) -> str:
    """Use LLM to shorten the issue body while preserving key information.

    Args:
        issue_title: Issue title
        issue_body: Issue body text
        model_name: LLM model to use
        api_key: API key for the LLM
        base_url: Base URL for the LLM API

    Returns:
        Shortened issue description (title + body)
    """
    logger = logging.getLogger(__name__)

    full_issue = f"{issue_title}\n\n{issue_body}"

    messages = [
        {
            "role": "system",
            "content": "Summarize GitHub issues concisely while preserving critical technical details."
        },
        {
            "role": "user",
            "content": f"""Shorten this GitHub issue while preserving core problem/bug.

Issue:
{full_issue}

Provide ONLY the shortened version, no explanations."""
        }
    ]

    try:
        logger.info(f"Shortening issue body using {model_name}...")
        response = litellm.completion(
            api_key=api_key,
            model=model_name,
            base_url=base_url,
            messages=messages,
            temperature=0.3,
        )

        shortened = response.choices[0].message.content.strip()
        logger.info(f"Original: {len(full_issue)} chars → Shortened: {len(shortened)} chars")
        return shortened

    except Exception as e:
        logger.error(f"Failed to shorten issue body: {e}")
        logger.warning("Using original issue body")
        return full_issue


def create_experiment_args(
    model_name: str,
    api_key: str,
    github_token: str,
    repo: str,
    issue_number: int,
    prompt_dir: Path,
    output_dir: Path
) -> tuple[Namespace, Path, Path]:
    """Create arguments for PRArenaIssueResolver with custom prompt templates.

    Returns:
        tuple: (args, user_prompt_file, conversation_prompt_file)
    """

    # Set up prompt file paths
    user_prompt_file = prompt_dir / "user_instructions.jinja"
    conversation_prompt_file = prompt_dir / "conversation_instructions.jinja"

    if not user_prompt_file.exists():
        raise FileNotFoundError(f"User prompt file not found: {user_prompt_file}")
    if not conversation_prompt_file.exists():
        raise FileNotFoundError(f"Conversation prompt file not found: {conversation_prompt_file}")

    args = Namespace(
        # Repository and issue
        selected_repo=repo,
        issue_number=issue_number,
        comment_id=None,
        issue_type='issue',

        # Authentication
        token=github_token,
        username=os.environ.get('GIT_USERNAME', 'pr-arena-experiment'),

        # Model configuration
        llm_models=f"{model_name}, {model_name}",  # Single model test
        llm_api_key=api_key,
        llm_base_url="https://cmu.litellm.ai",

        # Container settings
        base_container_image=None,
        runtime_container_image=None,
        is_experimental=False,

        # Output settings
        output_dir=str(output_dir),
        max_iterations=80,

        # Note: prompt_file is intentionally not set here
        # We'll manually override the templates after initialization
        prompt_file=None,
        repo_instruction_file=None,
        base_domain=None,
    )

    return args, user_prompt_file, conversation_prompt_file


async def run_experiment(
    model_name: str,
    api_key: str,
    github_token: str,
    repo: str,
    issue_number: int,
    prompt_name: str,
    output_dir: Path
) -> dict[str, Any]:
    """Run a single prompt experiment and return results."""

    logger = logging.getLogger(__name__)

    # Set up environment
    os.environ['LLM_API_KEY'] = api_key
    os.environ['LITELLM_API_KEY'] = api_key
    os.environ['OPENAI_API_KEY'] = api_key
    os.environ['LLM_BASE_URL'] = 'https://cmu.litellm.ai'

    # Mock API key function
    def mock_get_api_key(cls=None):
        return api_key

    # Mock Firebase config function (returns minimal config for local testing)
    def mock_get_firebase_config(cls=None):
        return json.dumps({
            "type": "service_account",
            "project_id": "pr-arena-local-test",
            "private_key_id": "dummy",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEA0dummy\n-----END PRIVATE KEY-----\n",
            "client_email": "test@pr-arena-local.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40pr-arena-local.iam.gserviceaccount.com"
        })

    # Get prompt directory (in prompts/ subdirectory)
    prompt_experiments_dir = Path(__file__).parent.parent
    prompt_dir = prompt_experiments_dir / "prompts" / prompt_name

    if not prompt_dir.exists():
        raise ValueError(f"Prompt directory not found: {prompt_dir}")

    logger.info(f"Using prompt templates from: {prompt_dir}")

    try:
        with patch.object(Secrets, 'get_api_key', classmethod(mock_get_api_key)), \
             patch.object(Secrets, 'get_firebase_config', classmethod(mock_get_firebase_config)):
            Secrets.TOKEN = github_token

            # Create resolver args with custom prompts
            args, user_prompt_file, conversation_prompt_file = create_experiment_args(
                model_name, api_key, github_token, repo, issue_number,
                prompt_dir, output_dir
            )

            logger.info(f"Testing model: {model_name}")
            logger.info(f"Repository: {repo}")
            logger.info(f"Issue: #{issue_number}")
            logger.info(f"Prompt: {prompt_name}")
            logger.info(f"User prompt: {user_prompt_file}")
            logger.info(f"Conversation prompt: {conversation_prompt_file}")

            # Initialize resolver
            resolver = PRArenaIssueResolver(args)

            # Load prompt templates
            with open(user_prompt_file, 'r') as f:
                user_template = f.read()
            with open(conversation_prompt_file, 'r') as f:
                conversation_template = f.read()

            # Override the resolver's prompt templates
            resolver.user_instructions_prompt_template = user_template
            resolver.conversation_instructions_prompt_template = conversation_template

            logger.info("Custom prompt templates loaded successfully")

            # Set up issue handler
            llm_config = resolver.llm_configs[0]
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
            resolver.output_dir = str(output_dir)

            # Handling prompts that require issue body or prompt modification with LLMs.
            # E.g., "shorter_prompt" to shorten long issues.
            shortened_body_for_template = None
            if prompt_name == "shorter_prompt":
                logger.info("Detected 'shorter_prompt' - shortening issue body with LLM")

                # Get the issue
                issues = resolver.issue_handler.get_converted_issues(
                    issue_numbers=[resolver.issue_number],
                    comment_id=resolver.comment_id
                )

                if issues:
                    issue = issues[0]
                    shortened_body = shorten_issue_body_with_llm(
                        issue_title=issue.title,
                        issue_body=issue.body,
                        model_name=model_name,
                        api_key=api_key,
                        base_url='https://cmu.litellm.ai'
                    )

                    # Store shortened body to inject into template
                    shortened_body_for_template = shortened_body
                    logger.info(f"Will use shortened body ({len(shortened_body)} chars) in template")

            # Patch the issue handler's get_instruction method if we have a shortened body
            if shortened_body_for_template:
                try:
                    from openhands.resolver.interfaces.utils import extract_image_urls
                except ImportError:
                    # Fallback if the import path changes
                    def extract_image_urls(text: str) -> list:
                        return []

                def patched_get_instruction(issue, user_tpl, conv_tpl, repo_instr=None):
                    """Patch to override the body variable in jinja rendering."""
                    # Use shortened body instead of original
                    thread_context = ''
                    if issue.thread_comments:
                        thread_context = '\n\nIssue Thread Comments:\n' + '\n---\n'.join(
                            issue.thread_comments
                        )

                    images = []
                    images.extend(extract_image_urls(issue.body))
                    images.extend(extract_image_urls(thread_context))

                    # Render user instructions with SHORTENED body
                    user_instructions_template = jinja2.Template(user_tpl)
                    user_instructions = user_instructions_template.render(
                        body=shortened_body_for_template  # Use shortened version
                    )

                    # Render conversation instructions normally
                    conversation_instructions_template = jinja2.Template(conv_tpl)
                    conversation_instructions = conversation_instructions_template.render(
                        repo_instruction=repo_instr,
                    )

                    return user_instructions, conversation_instructions, images

                resolver.issue_handler.get_instruction = patched_get_instruction
                logger.info("Patched get_instruction to use shortened body")

            # Run resolution
            logger.info("Starting issue resolution...")
            start_time = datetime.now()

            result = await resolver.resolve_issue()

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Prepare result summary
            result_data = {
                'model_name': model_name,
                'repo': repo,
                'issue_number': issue_number,
                'prompt_name': prompt_name,
                'timestamp': start_time.isoformat(),
                'duration_seconds': duration,
                'success': result.success if result else False,
                'has_git_patch': bool(result.git_patch) if result else False,
                'git_patch_length': len(result.git_patch) if (result and result.git_patch) else 0,
                'accumulated_cost': result.accumulated_cost if (result and hasattr(result, 'accumulated_cost')) else None,
                'total_iterations': result.total_iterations if (result and hasattr(result, 'total_iterations')) else None,
                'action_count': result.action_count if (result and hasattr(result, 'action_count')) else None,
                'error': result.error if (result and result.error) else None,
            }

            logger.info(f"Resolution completed in {duration:.2f} seconds")
            logger.info(f"Success: {result_data['success']}")
            logger.info(f"Patch generated: {result_data['has_git_patch']}")

            # Save git patch (filter out binary files and .pyc)
            if result and result.git_patch:
                patch_file = output_dir / "patch.diff"
                filtered_patch = filter_binary_files_from_patch(result.git_patch)
                with open(patch_file, 'w') as f:
                    f.write(filtered_patch)
                logger.info(f"Patch saved to: {patch_file}")

            # Save history only
            if result:
                result_file = output_dir / "result.json"
                result_dict = result.model_dump()
                history_data = {"history": result_dict.get("history", [])}
                with open(result_file, 'w') as f:
                    json.dump(history_data, f, indent=2)
                logger.info(f"History saved to: {result_file}")

            # Save summary
            summary_file = output_dir / "summary.json"
            with open(summary_file, 'w') as f:
                json.dump(result_data, f, indent=2)
            logger.info(f"Summary saved to: {summary_file}")

            # Clean up heavy artifacts
            logger.info("Cleaning up heavy artifacts...")
            cleanup_heavy_artifacts(output_dir)

            return result_data

    except Exception as e:
        logger.error(f"Experiment failed: {str(e)}", exc_info=True)
        # Clean up even on failure
        logger.info("Cleaning up heavy artifacts...")
        cleanup_heavy_artifacts(output_dir)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Run prompt experiments for PR-Arena issue resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--model-name",
        type=str,
        default="litellm_proxy/neulab/gemini-2.5-pro",
        help="LLM model to use (default: litellm_proxy/neulab/gemini-2.5-pro)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get('LLM_API_KEY', 'XXX'),
        help="API key for LLM (default: LLM_API_KEY env var or 'XXX')"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="JiseungHong/SYCON-Bench",
        help="GitHub repository (default: JiseungHong/SYCON-Bench)"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        default=33,
        help="Issue number to resolve (default: 33)"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=os.environ.get('GITHUB_TOKEN', 'XXX'),
        help="GitHub token (default: GITHUB_TOKEN env var or 'XXX')"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="basic_prompt",
        help="Prompt template directory name (default: basic_prompt)"
    )

    args = parser.parse_args()

    # Validate inputs
    if args.api_key == 'XXX':
        print("Warning: Using placeholder API key 'XXX'. Set --api-key or LLM_API_KEY")
    if args.github_token == 'XXX':
        print("Warning: Using placeholder GitHub token 'XXX'. Set --github-token or GITHUB_TOKEN")

    # Extract model short name
    model_short = args.model_name.split('/')[-1]

    # Set up output directory structure: {repo}_{issue}/{model}/{prompt}/
    # Output goes in prompt_experiments/, not scripts/
    repo_safe = args.repo.replace('/', '_')
    prompt_experiments_dir = Path(__file__).parent.parent
    output_base = prompt_experiments_dir / f"{repo_safe}_{args.issue_number}" / model_short / args.prompt
    output_base.mkdir(parents=True, exist_ok=True)

    # Set up logging
    setup_logging(output_base)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Prompt Experiment Runner")
    logger.info("=" * 60)
    logger.info(f"Model: {args.model_name}")
    logger.info(f"Repository: {args.repo}")
    logger.info(f"Issue: #{args.issue_number}")
    logger.info(f"Prompt: {args.prompt}")
    logger.info(f"Output: {output_base}")
    logger.info("=" * 60)

    try:
        # Run experiment
        result = asyncio.run(run_experiment(
            model_name=args.model_name,
            api_key=args.api_key,
            github_token=args.github_token,
            repo=args.repo,
            issue_number=args.issue_number,
            prompt_name=args.prompt,
            output_dir=output_base
        ))

        logger.info("=" * 60)
        logger.info("✅ Experiment completed successfully!")
        logger.info("=" * 60)
        logger.info(f"Success: {result['success']}")
        logger.info(f"Duration: {result['duration_seconds']:.2f}s")
        logger.info(f"Patch generated: {result['has_git_patch']}")
        if result['accumulated_cost']:
            logger.info(f"Cost: ${result['accumulated_cost']:.4f}")
        logger.info(f"Results saved to: {output_base}")

    except KeyboardInterrupt:
        logger.error("\n❌ Experiment interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Experiment failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
