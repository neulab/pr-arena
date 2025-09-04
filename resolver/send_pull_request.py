import argparse
import json
import os
import shutil
import subprocess
from typing import Iterable

import jinja2

from resolver.daytona_patch import apply_daytona_patch
from resolver.resolver_output import CustomResolverOutput

# Apply daytona compatibility patch before any openhands imports
apply_daytona_patch()

from openhands.core.config import LLMConfig  # noqa: E402
from openhands.core.logger import openhands_logger as logger  # noqa: E402
from openhands.integrations.service_types import ProviderType  # noqa: E402
from openhands.llm.llm import LLM  # noqa: E402
from openhands.resolver.interfaces.github import GithubIssueHandler  # noqa: E402
from openhands.resolver.interfaces.issue import Issue  # noqa: E402
from openhands.resolver.interfaces.issue_definitions import ServiceContextIssue  # noqa: E402
from openhands.resolver.patching import apply_diff, parse_patch  # noqa: E402


def load_all_resolver_outputs(
    output_jsonl: str,
) -> Iterable[CustomResolverOutput]:
    """Load all resolver outputs from a JSONL file.

    Args:
        output_jsonl: Path to the JSONL file containing resolver outputs

    Yields:
        CustomResolverOutput: Each resolver output from the file
    """
    with open(output_jsonl, "r") as f:
        for line in f:
            yield CustomResolverOutput.model_validate(json.loads(line))


def load_single_resolver_output(
    output_jsonl: str, issue_number: int
) -> CustomResolverOutput:
    """Load a single resolver output for a specific issue number.

    Args:
        output_jsonl: Path to the JSONL file containing resolver outputs
        issue_number: Issue number to find

    Returns:
        CustomResolverOutput: The resolver output for the specified issue

    Raises:
        ValueError: If the issue number is not found in the file
    """
    for resolver_output in load_all_resolver_outputs(output_jsonl):
        if resolver_output.issue.number == issue_number:
            return resolver_output
    raise ValueError(f"Issue number {issue_number} not found in {output_jsonl}")


def apply_patch(repo_dir: str, patch: str) -> None:
    """Apply a patch to a repository.

    Args:
        repo_dir: The directory containing the repository
        patch: The patch to apply
    """
    diffs = parse_patch(patch)
    for diff in diffs:
        if not diff.header.new_path:
            logger.warning("Could not determine file to patch")
            continue

        # Remove both "a/" and "b/" prefixes from paths
        old_path = (
            os.path.join(
                repo_dir, diff.header.old_path.removeprefix("a/").removeprefix("b/")
            )
            if diff.header.old_path and diff.header.old_path != "/dev/null"
            else None
        )
        new_path = os.path.join(
            repo_dir, diff.header.new_path.removeprefix("a/").removeprefix("b/")
        )

        # Check if the file is being deleted
        if diff.header.new_path == "/dev/null":
            assert old_path is not None
            if os.path.exists(old_path):
                os.remove(old_path)
                logger.info(f"Deleted file: {old_path}")
            continue

        # Handle file rename
        if old_path and new_path and "rename from" in patch:
            # Create parent directory of new path
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            try:
                # Try to move the file directly
                shutil.move(old_path, new_path)
            except shutil.SameFileError:
                # If it's the same file (can happen with directory renames), copy first then remove
                shutil.copy2(old_path, new_path)
                os.remove(old_path)

            # Try to remove empty parent directories
            old_dir = os.path.dirname(old_path)
            while old_dir and old_dir.startswith(repo_dir):
                try:
                    os.rmdir(old_dir)
                    old_dir = os.path.dirname(old_dir)
                except OSError:
                    # Directory not empty or other error, stop trying to remove parents
                    break
            continue

        if old_path:
            # Open the file in binary mode to detect line endings
            with open(old_path, "rb") as f:
                original_content = f.read()

            # Detect line endings
            if b"\r\n" in original_content:
                newline = "\r\n"
            elif b"\n" in original_content:
                newline = "\n"
            else:
                newline = None  # Let Python decide

            try:
                with open(old_path, "r", newline=newline) as f:
                    split_content = [x.strip(newline) for x in f.readlines()]
            except UnicodeDecodeError as e:
                logger.error(f"Error reading file {old_path}: {e}")
                split_content = []
        else:
            newline = "\n"
            split_content = []

        if diff.changes is None:
            logger.warning(f"No changes to apply for {old_path}")
            continue

        new_content = apply_diff(diff, split_content)

        # Ensure the directory exists before writing the file
        os.makedirs(os.path.dirname(new_path), exist_ok=True)

        # Write the new content using the detected line endings
        with open(new_path, "w", newline=newline) as f:
            for line in new_content:
                print(line, file=f)

    logger.info("Patch applied successfully")


def initialize_repo(
    output_dir: str, issue_number: int, issue_type: str, base_commit: str | None = None
) -> str:
    """Initialize the repository.

    Args:
        output_dir: The output directory to write the repository to
        issue_number: The issue number to fix
        issue_type: The type of the issue
        base_commit: The base commit to checkout (if issue_type is pr)
    """
    src_dir = os.path.join(output_dir, "repo")
    dest_dir = os.path.join(output_dir, "patches", f"{issue_type}_{issue_number}")

    if not os.path.exists(src_dir):
        raise ValueError(f"Source directory {src_dir} does not exist.")

    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)

    shutil.copytree(src_dir, dest_dir)
    logger.info(f"Copied repository to {dest_dir}")

    # Checkout the base commit if provided
    if base_commit:
        result = subprocess.run(
            f"git -C {dest_dir} checkout {base_commit}",
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.info(f"Error checking out commit: {result.stderr}")
            raise RuntimeError("Failed to check out commit")

    return dest_dir


def make_commit(repo_dir: str, issue: Issue, issue_type: str) -> None:
    """Make a commit with the changes to the repository.

    Args:
        repo_dir: The directory containing the repository
        issue: The issue to fix
        issue_type: The type of the issue
    """
    # Check if git username is set
    result = subprocess.run(
        f"git -C {repo_dir} config user.name",
        shell=True,
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        # If username is not set, configure git
        subprocess.run(
            f'git -C {repo_dir} config user.name "openhands" && '
            f'git -C {repo_dir} config user.email "openhands@all-hands.dev" && '
            f'git -C {repo_dir} config alias.git "git --no-pager"',
            shell=True,
            check=True,
        )
        logger.info("Git user configured as openhands")

    # Add all changes to the git index
    result = subprocess.run(
        f"git -C {repo_dir} add .", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"Error adding files: {result.stderr}")
        raise RuntimeError("Failed to add files to git")

    # Check the status of the git index
    status_result = subprocess.run(
        f"git -C {repo_dir} status --porcelain",
        shell=True,
        capture_output=True,
        text=True,
    )

    # If there are no changes, raise an error
    if not status_result.stdout.strip():
        logger.warning(
            f"No changes to commit for issue #{issue.number}. Empty patch detected."
        )
        raise RuntimeError("ERROR: Openhands failed to make code changes.")

    # Prepare the commit message
    commit_message = f"Fix {issue_type} #{issue.number}: {issue.title}"

    # Commit the changes
    result = subprocess.run(
        ["git", "-C", repo_dir, "commit", "-m", commit_message],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to commit changes: {result}")


def make_commit_with_summary(
    repo_dir: str,
    issue: Issue,
    issue_type: str,
    resolver_output: CustomResolverOutput,
    branch_name: str | None = None,
    output_dir: str | None = None,
) -> None:
    """Make a commit with the changes to the repository.

    Args:
        repo_dir: The directory containing the repository
        issue: The issue to fix
        issue_type: The type of the issue
        resolver_output: The resolver output containing result explanation (optional)
        branch_name: The branch name to use for the commit (optional)
        output_dir: The output directory to use for the commit (optional)
    """
    # Check if git username is set
    result = subprocess.run(
        f"git -C {repo_dir} config user.name",
        shell=True,
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        # If username is not set, configure git
        subprocess.run(
            f'git -C {repo_dir} config user.name "openhands" && '
            f'git -C {repo_dir} config user.email "openhands@all-hands.dev" && '
            f'git -C {repo_dir} config alias.git "git --no-pager"',
            shell=True,
            check=True,
        )
        logger.info("Git user configured as openhands")

    # Add all changes to the git index
    result = subprocess.run(
        f"git -C {repo_dir} add .", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"Error adding files: {result.stderr}")
        raise RuntimeError("Failed to add files to git")

    # Check the status of the git index
    status_result = subprocess.run(
        f"git -C {repo_dir} status --porcelain",
        shell=True,
        capture_output=True,
        text=True,
    )

    # If there are no changes, raise an error
    if not status_result.stdout.strip():
        logger.warning(
            f"No changes to commit for issue #{issue.number}. Empty patch detected."
        )
        raise RuntimeError("ERROR: Openhands failed to make code changes.")

    tail_str = "Model"

    model_number = output_dir[-1] if output_dir else ""
    if model_number == "1":
        tail_str = "Model A"
    elif model_number == "2":
        tail_str = "Model B"
    else:
        raise ValueError(f"Invalid model number: {model_number}")

    # Prepare the commit message with branch name if available
    commit_message = f"Fix {issue_type} #{issue.number} with {tail_str}"

    # Append result explanation if available
    if resolver_output and resolver_output.result_explanation:
        # Clean up the explanation text for commit message
        explanation = resolver_output.result_explanation.strip()

        # Add summary section
        commit_message += "\n\nSummary of Changes:"

        # If the explanation is JSON, try to format it nicely
        try:
            explanations = json.loads(explanation)
            if isinstance(explanations, list):
                # Format as numbered list
                for i, item in enumerate(explanations, 1):
                    commit_message += f"\n{i}. {item}"
            else:
                # Single explanation
                commit_message += f"\n{str(explanations)}"
        except json.JSONDecodeError:
            # Not JSON, use as plain text with numbering
            commit_message += f"\n{explanation}"

    # Add duration if available
    if (
        resolver_output
        and hasattr(resolver_output, "duration")
        and resolver_output.duration
    ):
        duration_mins = int(resolver_output.duration // 60)
        duration_secs = int(resolver_output.duration % 60)
        commit_message += f"\n\nDuration: {duration_mins}m {duration_secs}s"

    # Commit the changes with the enhanced message
    result = subprocess.run(
        ["git", "-C", repo_dir, "commit", "-m", commit_message],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to commit changes: {result}")

    logger.info(f"Created commit with message: {commit_message}")


def send_pull_request(
    issue: Issue,
    token: str,
    username: str | None,
    platform: ProviderType,
    resolver_output: CustomResolverOutput,
    pr_type: str,
    fork_owner: str | None = None,
    additional_message: str | None = None,
    target_branch: str | None = None,
    reviewer: str | None = None,
    pr_title: str | None = None,
    base_domain: str | None = None,
) -> str:
    """Send a pull request to a GitHub repository.

    Args:
        issue: The issue to send the pull request for
        token: The GitHub token to use for authentication
        username: The GitHub username, if provided
        platform: The platform of the repository (always GitHub)
        resolver_output: The resolver output containing branch information
        pr_type: The type: branch (no PR created), draft or ready (regular PR created)
        fork_owner: The owner of the fork to push changes to (if different from the original repo owner)
        additional_message: The additional messages to post as a comment on the PR in json list format
        target_branch: The target branch to create the pull request against (defaults to repository default branch)
        reviewer: The GitHub username of the reviewer to assign
        pr_title: Custom title for the pull request (optional)
        base_domain: The base domain for the git server (defaults to "github.com")
    """
    if pr_type not in ["branch", "draft", "ready"]:
        raise ValueError(f"Invalid pr_type: {pr_type}")

    # Set default base_domain
    if base_domain is None:
        base_domain = "github.com"

    # Create GitHub handler
    handler = ServiceContextIssue(
        GithubIssueHandler(issue.owner, issue.repo, token, username, base_domain),
        None,
    )

    # Use the branch name from resolver_output
    branch_name = resolver_output.branch_name
    if not branch_name:
        raise ValueError("Branch name is required but not provided in resolver output")
    logger.info(f"Using existing branch: {branch_name}")

    # Get the default branch or use specified target branch
    logger.info("Getting base branch...")
    if target_branch:
        base_branch = target_branch
        exists = handler.branch_exists(branch_name=target_branch)
        if not exists:
            raise ValueError(f"Target branch {target_branch} does not exist")
    else:
        base_branch = handler.get_default_branch_name()
    logger.info(f"Base branch: {base_branch}")

    # Determine the repository to push to (original or fork)
    push_owner = fork_owner if fork_owner else issue.owner
    handler._strategy.set_owner(push_owner)

    # Prepare the PR data: title and body
    final_pr_title = (
        pr_title if pr_title else f"Fix issue #{issue.number}: {issue.title}"
    )
    pr_body = f"This pull request fixes #{issue.number}."
    if additional_message:
        pr_body += f"\n\n{additional_message}"
    pr_body += (
        "\n\nAutomatic fix generated by "
        "[OpenHands](https://github.com/All-Hands-AI/OpenHands/) 🙌"
    )

    # For cross repo pull request, we need to send head parameter like fork_owner:branch
    # as per git documentation here:
    # https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#create-a-pull-request
    # head parameter usage: The name of the branch where your changes are implemented.
    # For cross-repository pull requests in the same network, namespace head with a user
    # like this: username:branch.
    if fork_owner:
        head_branch = f"{fork_owner}:{branch_name}"
    else:
        head_branch = branch_name

    # Prepare the PR for the GitHub API
    data = {
        "title": final_pr_title,
        "body": pr_body,
        "head": head_branch,
        "base": base_branch,
        "draft": pr_type == "draft",
    }

    pr_data = handler.create_pull_request(data)
    url = pr_data["html_url"]

    # Request review if a reviewer was specified
    if reviewer and pr_type != "branch":
        number = pr_data["number"]
        handler.request_reviewers(reviewer, number)

    logger.info(
        f"{pr_type} created: {url}\n\n--- Title: {final_pr_title}\n\n--- Body:\n{pr_body}"
    )

    return url


def update_existing_pull_request(
    issue: Issue,
    token: str,
    username: str | None,
    platform: ProviderType,
    resolver_output: CustomResolverOutput,
    llm_config: LLMConfig,
    comment_message: str | None = None,
    additional_message: str | None = None,
    base_domain: str | None = None,
) -> str:
    """Update an existing pull request with the new patches.

    Args:
        issue: The issue to update.
        token: The GitHub token to use for authentication.
        username: The GitHub username to use for authentication.
        platform: The platform of the repository (always GitHub).
        resolver_output: The resolver output containing branch information.
        llm_config: The LLM configuration to use for summarizing changes.
        comment_message: The main message to post as a comment on the PR.
        additional_message: The additional messages to post as a comment on the PR in json list format.
        base_domain: The base domain for the git server (defaults to "github.com")
    """
    # Set default base_domain
    if base_domain is None:
        base_domain = "github.com"

    # Create GitHub handler
    handler = ServiceContextIssue(
        GithubIssueHandler(issue.owner, issue.repo, token, username, base_domain),
        llm_config,
    )

    # We don't need to push changes as that's handled in resolve_issues.py
    branch_name = resolver_output.branch_name
    logger.info(f"Using existing branch: {branch_name}")

    pr_url = handler.get_pull_url(issue.number)
    logger.info(f"Updated pull request {pr_url} with new patches.")

    # Generate a summary of all comment success indicators for PR message
    if not comment_message and additional_message:
        try:
            explanations = json.loads(additional_message)
            if explanations:
                comment_message = (
                    "OpenHands made the following changes to resolve the issues:\n\n"
                )
                for explanation in explanations:
                    comment_message += f"- {explanation}\n"

                # Summarize with LLM if provided
                if llm_config is not None:
                    llm = LLM(llm_config)
                    with open(
                        os.path.join(
                            os.path.dirname(__file__),
                            "prompts/resolve/pr-changes-summary.jinja",
                        ),
                        "r",
                    ) as f:
                        template = jinja2.Template(f.read())
                    prompt = template.render(comment_message=comment_message)
                    response = llm.completion(
                        messages=[{"role": "user", "content": prompt}],
                    )
                    comment_message = response.choices[0].message.content.strip()

        except (json.JSONDecodeError, TypeError):
            comment_message = f"A new OpenHands update is available, but failed to parse or summarize the changes:\n{additional_message}"

    # Post a comment on the PR
    if comment_message:
        handler.send_comment_msg(issue.number, comment_message)

    # Reply to each unresolved comment thread
    if additional_message and issue.thread_ids:
        try:
            explanations = json.loads(additional_message)
            for count, reply_comment in enumerate(explanations):
                comment_id = issue.thread_ids[count]
                handler.reply_to_comment(issue.number, comment_id, reply_comment)
        except (json.JSONDecodeError, TypeError):
            msg = f"Error occured when replying to threads; success explanations {additional_message}"
            handler.send_comment_msg(issue.number, msg)

    return pr_url


def process_single_issue(
    output_dir: str,
    resolver_output: CustomResolverOutput,
    token: str,
    username: str,
    platform: ProviderType,
    pr_type: str,
    llm_config: LLMConfig,
    fork_owner: str | None,
    send_on_failure: bool,
    target_branch: str | None = None,
    reviewer: str | None = None,
    pr_title: str | None = None,
    base_domain: str | None = None,
) -> None:
    # Determine default base_domain based on platform
    if base_domain is None:
        base_domain = "github.com"

    issue_type = resolver_output.issue_type

    # [PR-Arena] issue_type is always "issue"
    if issue_type != "issue":
        raise ValueError(f"Invalid issue type: {issue_type}")

    if not resolver_output.success and not send_on_failure:
        logger.info(
            f"Issue {resolver_output.issue.number} was not successfully resolved. Skipping PR creation."
        )
        return

    # Check for empty git patch and skip PR creation
    if not resolver_output.git_patch or resolver_output.git_patch.strip() == "":
        logger.warning(
            f"Issue {resolver_output.issue.number} has empty git patch. Skipping PR creation."
        )
        return

    # Create a PR using the branch that was already created in resolve_issues.py
    send_pull_request(
        issue=resolver_output.issue,
        token=token,
        username=username,
        platform=platform,
        resolver_output=resolver_output,
        pr_type=pr_type,
        fork_owner=fork_owner,
        additional_message=resolver_output.result_explanation,
        target_branch=target_branch,
        reviewer=reviewer,
        pr_title=pr_title,
        base_domain=base_domain,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a pull request to Github.")
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Github token to access the repository.",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help="username to access the repository.",
    )
    parser.add_argument(
        "--pr-type",
        type=str,
        default="draft",
        choices=["branch", "draft", "ready"],
        help="Type of the pull request to send [branch, draft, ready]",
    )
    parser.add_argument(
        "--issue-number",
        type=str,
        required=True,
        help="Issue number to send the pull request for, or 'all_successful' to process all successful issues.",
    )
    parser.add_argument(
        "--fork-owner",
        type=str,
        default=None,
        help="Owner of the fork to push changes to (if different from the original repo owner).",
    )
    parser.add_argument(
        "--send-on-failure",
        # action='store_true',
        default=False,
        help="Send a pull request even if the issue was not successfully resolved.",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM model to use for summarizing changes.",
    )
    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="API key for the LLM model.",
    )
    parser.add_argument(
        "--llm-base-url",
        type=str,
        default=None,
        help="Base URL for the LLM model.",
    )
    parser.add_argument(
        "--target-branch",
        type=str,
        default=None,
        help="Target branch to create the pull request against (defaults to repository default branch)",
    )
    parser.add_argument(
        "--reviewer",
        type=str,
        help="GitHub username of the person to request review from",
        default=None,
    )
    parser.add_argument(
        "--pr-title",
        type=str,
        help="Custom title for the pull request",
        default=None,
    )
    parser.add_argument(
        "--base-domain",
        type=str,
        default=None,
        help='Base domain for the git server (defaults to "github.com")',
    )
    parser.add_argument(
        "--model-number",
        type=int,
        required=True,
        help="Get the number of model for the ARENA setting.",
    )
    my_args = parser.parse_args()

    token = my_args.token or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "token is not set, set via --token or GITHUB_TOKEN environment variable."
        )
    username = my_args.username if my_args.username else os.getenv("GIT_USERNAME")
    if not username:
        raise ValueError("username is required.")

    # Set platform to GitHub only
    platform = ProviderType.GITHUB

    # Not use LLM - only used for OpenHands Resolver > update_existing_pull_request
    # api_key = my_args.llm_api_key or os.environ.get('LLM_API_KEY')
    # llm_config = LLMConfig(
    #     model=my_args.llm_model or os.environ.get('LLM_MODEL'),
    #     api_key=SecretStr(api_key) if api_key else None,
    #     base_url=my_args.llm_base_url or os.environ.get('LLM_BASE_URL', None),
    # )

    output_dir = f"output{my_args.model_number}"

    if not os.path.exists(output_dir):
        raise ValueError(f"Output directory {output_dir} does not exist.")

    if not my_args.issue_number.isdigit():
        raise ValueError(f"Issue number {my_args.issue_number} is not a number.")
    issue_number = int(my_args.issue_number)
    output_path = os.path.join(output_dir, "output.jsonl")
    resolver_output = load_single_resolver_output(output_path, issue_number)

    process_single_issue(
        output_dir,
        resolver_output,
        token,
        username,
        platform,
        my_args.pr_type,
        None,
        my_args.fork_owner,
        my_args.send_on_failure,
        resolver_output.default_branch,
        my_args.reviewer,
        None,
        None,
    )


if __name__ == "__main__":
    main()
