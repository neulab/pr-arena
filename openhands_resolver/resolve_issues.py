# flake8: noqa: E501

import asyncio
import dataclasses
import shutil
from typing import Any, Awaitable, TextIO
import argparse
import multiprocessing as mp
import os
import pathlib
import requests
import subprocess
import json
import random
import shlex
import uuid

from termcolor import colored
from tqdm import tqdm


from typing import cast, Optional

from openhands_resolver.github_issue import GithubIssue
from openhands_resolver.issue_definitions import ( 
    IssueHandler, 
    IssueHandlerInterface, 
    PRHandler
)
from openhands_resolver.resolver_output import ResolverOutput
import openhands
from openhands.core.main import create_runtime, run_controller
from openhands.controller.state.state import State
from openhands.core.logger import openhands_logger as logger
from openhands.events.action import CmdRunAction, MessageAction
from openhands.events.observation import (
    CmdOutputObservation,
    ErrorObservation,
    Observation,
)
from openhands.core.config import (
    AppConfig,
    SandboxConfig,
)
from openhands.core.config import LLMConfig
from openhands.runtime.runtime import Runtime
from openhands_resolver.utils import (
    codeact_user_response,
    reset_logger_for_multiprocessing,
)

from openhands_resolver.patching import parse_patch, apply_diff
from openhands_resolver.send_pull_request import initialize_repo, apply_patch, make_commit, branch_exists

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app


# Don't make this confgurable for now, unless we have other competitive agents
AGENT_CLASS = "CodeActAgent"

class Secrets:
    """Class for retrieving specific secrets from the Firebase Function endpoint."""
    
    # Firebase Function endpoint
    ENDPOINT_URL = "https://us-central1-pr-arena-95f88.cloudfunctions.net/getSecrets"
    
    # The token to use for authentication - must be set before using the class
    TOKEN = "default"
    
    @classmethod
    def _get_secrets(cls, secret_names):
        """Internal method to retrieve secrets from the Firebase Function."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cls.TOKEN}"
        }
        
        payload = {
            "secrets": secret_names
        }
        
        response = requests.post(
            cls.ENDPOINT_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            error_msg = f"Error retrieving secrets: {response.status_code} - {response.text}"
            raise ValueError(error_msg)
        
        try:
            result = response.json()
            
            if not result.get("success"):
                raise ValueError(f"API reported failure: {result.get('message', 'Unknown error')}")
                
            return result.get("secrets", {})
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON response: {response.text}")
    
    @classmethod
    def get_api_key(cls):
        """Get the LLM API key directly."""
        secrets = cls._get_secrets(["LLM_API_KEY"])
        return secrets.get("LLM_API_KEY")
    
    @classmethod
    def get_firebase_config(cls):
        """Get the Firebase configuration directly."""
        secrets = cls._get_secrets(["FIRE_CONFIG"])
        return secrets.get("FIRE_CONFIG")
    
    @classmethod
    def get_base_url(cls):
        """Get the base URL directly."""
        secrets = cls._get_secrets(["BASE_URL"])
        return secrets.get("BASE_URL")
    
    @classmethod
    def get_llm_models(cls):
        """Get the LLM models configuration directly."""
        secrets = cls._get_secrets(["LLM_MODELS"])
        return secrets.get("LLM_MODELS")

def prepare_branch_and_push(
    github_issue: GithubIssue,
    github_token: str,
    github_username: Optional[str],
    patch_dir: str,
    pr_type: str,
) -> tuple[str, str, str, dict]:
    """
    1) Validates pr_type.
    2) Sets up API headers, base_url.
    3) Generates a unique branch name.
    4) Gets the repository's default branch.
    5) Creates & checks out a new local branch.
    6) Pushes the new branch to GitHub.
    7) Returns the data needed for creating a PR (branch name, default branch, base_url, etc.)
       plus the commit hash of HEAD.
    """

    if pr_type not in ["branch", "draft", "ready"]:
        raise ValueError(f"Invalid pr_type: {pr_type}")

    # Prepare GitHub API details
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    base_url = f"https://api.github.com/repos/{github_issue.owner}/{github_issue.repo}"

    # Create a new branch name
    base_branch_name = f"openhands-fix-issue-{github_issue.number}"
    branch_name = base_branch_name
    attempt = 1

    # Ensure the branch doesn't already exist on the remote
    while branch_exists(base_url, branch_name, headers):
        attempt += 1
        branch_name = f"{base_branch_name}-try{attempt}"

    # Get the default branch
    response = requests.get(base_url, headers=headers)
    response.raise_for_status()
    default_branch = response.json()["default_branch"]

    # Create and checkout the new branch locally
    result = subprocess.run(
        f"git -C {shlex.quote(patch_dir)} checkout -b {shlex.quote(branch_name)}",
        shell=True,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error creating new branch: {result.stderr}")
        raise RuntimeError(f"Failed to create a new branch {branch_name} in {patch_dir}.")

    # Determine the repository to push to
    push_owner = github_issue.owner
    push_repo = github_issue.repo

    # Construct push command
    username_and_token = (
        f"{github_username}:{github_token}"
        if github_username else
        f"x-auth-token:{github_token}"
    )
    push_command = (
        f"git -C {shlex.quote(patch_dir)} push "
        f"https://{username_and_token}@github.com/"
        f"{push_owner}/{push_repo}.git {shlex.quote(branch_name)}"
    )
    result = subprocess.run(push_command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error pushing changes\n{push_command}\n{result.stderr}")
        raise RuntimeError("Failed to push changes to the remote repository")

    return branch_name, default_branch, base_url, headers

def get_new_commit_hash(output_dir, resolver_output: ResolverOutput, github_token: str, github_username: str, pr_type: str) -> None:
    # 1) initialize_repo
    patched_repo_dir = initialize_repo(
        output_dir=output_dir,
        issue_number=resolver_output.issue.number,
        issue_type=resolver_output.issue_type,
        base_commit=resolver_output.base_commit,
    )

    # logger.info(f"[DEBUG] Previous Patched Repo Dir: {patched_repo_dir}")
    branch_name, default_branch, base_url, headers = None, None, None, None
    
    if resolver_output.git_patch:
        # 2) apply_patch
        apply_patch(patched_repo_dir, resolver_output.git_patch)

        # 3) make_commit
        # logger.info(f"[DEBUG] Resolver Output: {resolver_output} to {output_dir}")
        make_commit(patched_repo_dir, resolver_output.issue, resolver_output.issue_type)
        
        # 4) branch checkout and push
        branch_name, default_branch, base_url, headers = prepare_branch_and_push(
            github_issue=resolver_output.issue,
            github_token=github_token,
            github_username=github_username,
            patch_dir=patched_repo_dir,
            pr_type=pr_type,
        )
        
        # logger.info(f"[DEBUG] Success Patched Repo Dir: {patched_repo_dir}")
    else:
        resolver_output.success = False
        resolver_output.success_explanation = "No git patch found."
    
    resolver_output.branch_name = branch_name
    resolver_output.default_branch = default_branch
    resolver_output.base_url = base_url
    resolver_output.headers = headers

    # 5) Retrieve commit hash
    rev_parse_cmd = f'git -C "{patched_repo_dir}" rev-parse HEAD'
    result = subprocess.run(rev_parse_cmd, shell=True, capture_output=True, text=True)
    new_hash = result.stdout.strip()

    # 6) Assign it back to the resolver_output
    resolver_output.commit_hash = new_hash
    resolver_output.repo_dir = patched_repo_dir

    return


def cleanup():
    print("Cleaning up child processes...")
    for process in mp.active_children():
        print(f"Terminating child process: {process.name}")
        process.terminate()
        process.join()


def load_firebase_config(config_json: str) -> dict:
    """Load Firebase configuration from JSON string."""
    try:
        return json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid Firebase configuration JSON: {e}")

async def send_to_firebase (
    resolved_output1: ResolverOutput,
    resolved_output2: ResolverOutput,
    owner: str,
    repo: str,
    issue_number: int,
    firebase_config: dict,
    token: str,
    username: str,
    pr_type: str,
) -> None:
    """
    Send the resolver output to Firebase Firestore.

    Args:
        resolved_output (ResolverOutput): The resolved output to be sent.
        owner (str): GitHub owner.
        repo (str): GitHub repository name.
        issue_number (int): Issue number.
        firebase_config (dict): Firebase configuration.
    """
    pathlib.Path("output1").mkdir(parents=True, exist_ok=True)
    pathlib.Path("output2").mkdir(parents=True, exist_ok=True)
    
    file_name = "output.jsonl"
    output_file1 = pathlib.Path("output1") / file_name
    output_file2 = pathlib.Path("output2") / file_name
    
    # [PR-Arena] Retrieve commit hash and send it to firesbase as well.
    # And somehow save the file somewhere so that send_pull_request.py could get the file (new commit).
    get_new_commit_hash(
        output_dir="output1",
        resolver_output=resolved_output1,
        github_token=token,
        github_username=username,
        pr_type=pr_type
    
    )
    get_new_commit_hash(
        output_dir="output2",
        resolver_output=resolved_output2,
        github_token=token,
        github_username=username,
        pr_type=pr_type
    )
    
    # Write the resolved output to a JSONL file
    with open(output_file1, "a") as output_fp:
        output_fp.write(resolved_output1.model_dump_json() + "\n")
    
    with open(output_file2, "a") as output_fp:
        output_fp.write(resolved_output2.model_dump_json() + "\n")
    
    # Send the resolved output to Firebase Firestore
    cred = credentials.Certificate(firebase_config)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        
    db = firestore.client()
    
    current_time = firestore.SERVER_TIMESTAMP
    
    repo_url = f"https://github.com/{owner}/{repo}"
    issue_name = f"Issue #{issue_number}"
    
    model_reference = {
        "claude-3-7-sonnet-20250219": "model1",
        "gpt-4o-2024-05-13": "model2",
        "Meta-Llama-3.1-405B-Instruct": "model3",
        "deepseek-chat": "model4",
        "gemini-2.0-flash-exp": "model5",
        "Qwen2.5-72B-Instruct": "model6",
        "Meta-Llama-3.1-8B-Instruct": "model7"
    }
    
    model1_id = model_reference.get(resolved_output1.model, "Model ID Not Found")
    model2_id = model_reference.get(resolved_output2.model, "Model ID Not Found")
    
    if not resolved_output1.git_patch or not resolved_output2.git_patch or resolved_output1.success is False or resolved_output2.success is False:
        issue_data = {
            "repo_url": repo_url,
            "issue_name": issue_name,
            "owner": owner,
            "repo": repo,
            "status": "failed",
            "models": {
                "modelA": {
                    "modelId": model1_id,
                    "modelName": resolved_output1.model,
                    "commit_hash": resolved_output1.commit_hash,
                    "agent_code": resolved_output1.git_patch if resolved_output1.git_patch else ""
                },
                "modelB": {
                    "modelId": model2_id,
                    "modelName": resolved_output2.model,
                    "commit_hash": resolved_output2.commit_hash,
                    "agent_code": resolved_output2.git_patch if resolved_output2.git_patch else ""
                }
            },
            "winner": None,  # No winner determined yet
            "createdAt": current_time,
            "updatedAt": current_time
        }
        
        reference_id = str(uuid.uuid4())
        
        issue_ref = db.collection("issue_collection").document(reference_id)
        issue_ref.set(issue_data)
        
        github_env_path = os.getenv("GITHUB_ENV")
        if not github_env_path:
            raise RuntimeError("GITHUB_ENV environment variable is not set.")

        # Write the decision to the environment file
        with open(github_env_path, "a") as env_file:
            env_file.write("FAILED=TRUE\n")
        
        return
    
    issue_data = {
        "repo_url": repo_url,
        "issue_name": issue_name,
        "owner": owner,
        "repo": repo,
        "status": "pending",  # Initial status is pending
        "models": {
            "modelA": {
                "modelId": model1_id,
                "modelName": resolved_output1.model,
                "commit_hash": resolved_output1.commit_hash,
                "agent_code": resolved_output1.git_patch if resolved_output1.git_patch else ""
            },
            "modelB": {
                "modelId": model2_id,
                "modelName": resolved_output2.model,
                "commit_hash": resolved_output2.commit_hash,
                "agent_code": resolved_output2.git_patch if resolved_output2.git_patch else ""
            }
        },
        "winner": None,  # No winner determined yet
        "createdAt": current_time,
        "updatedAt": current_time
    }
    
    reference_id = str(uuid.uuid4())
    
    issue_ref = db.collection("issue_collection").document(reference_id)
    issue_ref.set(issue_data)
    
    current_time = firestore.SERVER_TIMESTAMP

    user_data = {
        "githubId": owner,
        "createdAt": current_time,
        "lastActive": current_time,
        "selections": {
            reference_id: {
                "issueId": reference_id,
                "choice": None,  # No choice made yet
                "selectedAt": None,
                "isLatest": True,
                "language": "en",  # Default language
                "isAnonymous": True,
                "deduplicated": True,
                "modelA": {
                    "modelId": model1_id,
                    "modelName": resolved_output1.model
                },
                "modelB": {
                    "modelId": model2_id,
                    "modelName": resolved_output2.model
                }
            }
        }
    }
    
    # Store in user_collection with owner as document ID
    user_ref = db.collection("userdata_collection").document(owner)
    user_ref.set(user_data, merge=True)
    
    github_env_path = os.getenv("GITHUB_ENV")
    if not github_env_path:
        raise RuntimeError("GITHUB_ENV environment variable is not set.")

    # Write the decision to the environment file
    with open(github_env_path, "a") as env_file:
        env_file.write(f"UUID={reference_id}\n")
        env_file.write("FAILED=FALSE\n")
    
    print("Data successfully written to Firestore collections 'issue_collection' and 'user_collection'")
    print(f"Issue ID: {issue_number}, Models: {resolved_output1.model} vs {resolved_output2.model}")


def create_git_patch(
    workspace_mount_path: str, main_branch: str, fix_branch: str, issue_number: int
) -> tuple[str, str | None]:
    """Create a git patch file between main_branch and fix_branch.

    Args:
        workspace_mount_path: Path to the workspace.
        main_branch: Main branch.
        fix_branch: Fix branch.
        issue_number: Issue number.

    Returns:
        A tuple of:
        - The original branch's git id
        - A patch to apply the fix
        or None if there is not a patch between the main and fix branch.
    """
    # Git the commit ID of the main branch
    git_id = (
        subprocess.check_output(["git", "rev-parse", main_branch])
        .decode("utf-8")
        .strip()
    )
    # Within the workspace, use git to create a patch between main_branch and fix_branch
    os.system(
        f"cd {workspace_mount_path} && git diff {main_branch} {fix_branch} > {issue_number}.patch"
    )
    git_patch_file = os.path.join(workspace_mount_path, f"{issue_number}.patch")
    with open(git_patch_file, "r") as f:
        patch_content = f.read()
    return git_id, patch_content


def initialize_runtime(
    runtime: Runtime,
):
    """Initialize the runtime for the agent.

    This function is called before the runtime is used to run the agent.
    Currently it does nothing.
    """
    logger.info('-' * 30)
    logger.info('BEGIN Runtime Completion Fn')
    logger.info('-' * 30)
    obs: Observation

    action = CmdRunAction(command='cd /workspace')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(
            f"Failed to change directory to /workspace.\n{obs}"
        )

    action = CmdRunAction(command='git config --global core.pager ""')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(f"Failed to set git config.\n{obs}")


async def complete_runtime(
    runtime: Runtime,
    base_commit: str,
) -> dict[str, Any]:
    """Complete the runtime for the agent.

    This function is called before the runtime is used to run the agent.
    If you need to do something in the sandbox to get the correctness metric after
    the agent has run, modify this function.
    """
    logger.info('-' * 30)
    logger.info('BEGIN Runtime Completion Fn')
    logger.info('-' * 30)
    obs: Observation

    action = CmdRunAction(command='cd /workspace')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(
            f"Failed to change directory to /workspace. Observation: {obs}"
        )

    action = CmdRunAction(command='git config --global core.pager ""')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(f"Failed to set git config. Observation: {obs}")

    action = CmdRunAction(command='git config --global --add safe.directory /workspace')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(f"Failed to set git config. Observation: {obs}")

    action = CmdRunAction(command='git add -A')
    logger.info(action, extra={'msg_type': 'ACTION'})
    obs = runtime.run_action(action)
    logger.info(obs, extra={'msg_type': 'OBSERVATION'})
    if not isinstance(obs, CmdOutputObservation) or obs.exit_code != 0:
        raise RuntimeError(f"Failed to git add. Observation: {obs}")

    n_retries = 0
    git_patch = None
    while n_retries < 5:
        action = CmdRunAction(
            command=f'git diff --no-color --cached {base_commit}',
            keep_prompt=False,
        )
        action.timeout = 600 + 100 * n_retries
        logger.info(action, extra={'msg_type': 'ACTION'})
        obs = runtime.run_action(action)
        logger.info(obs, extra={'msg_type': 'OBSERVATION'})
        n_retries += 1
        if isinstance(obs, CmdOutputObservation):
            if obs.exit_code == 0:
                git_patch = obs.content.strip()
                break
            else:
                logger.info('Failed to get git diff, retrying...')
                await asyncio.sleep(10)
        elif isinstance(obs, ErrorObservation):
            logger.error(f'Error occurred: {obs.content}. Retrying...')
            await asyncio.sleep(10)
        else:
            raise ValueError(f'Unexpected observation type: {type(obs)}')

    logger.info('-' * 30)
    logger.info('END Runtime Completion Fn')
    logger.info('-' * 30)
    return {'git_patch': git_patch}
        

async def process_issue(
    issue: GithubIssue,
    base_commit: str,
    max_iterations: int,
    llm_config: LLMConfig,
    output_dir: str,
    runtime_container_image: str,
    prompt_template: str,
    issue_handler: IssueHandlerInterface,
    repo_instruction: str | None = None,
    reset_logger: bool = True,
) -> ResolverOutput:

    # Setup the logger properly, so you can run multi-processing to parallelize processing
    if reset_logger:
        log_dir = os.path.join(output_dir, 'infer_logs')
        reset_logger_for_multiprocessing(logger, str(issue.number), log_dir)
    else:
        logger.info(f'Starting fixing issue {issue.number}.')

    workspace_base = os.path.join(output_dir, "workspace", f"{issue_handler.issue_type}_{issue.number}")

    # Get the absolute path of the workspace base
    workspace_base = os.path.abspath(workspace_base)
    # write the repo to the workspace
    if os.path.exists(workspace_base):
        shutil.rmtree(workspace_base)
    shutil.copytree(os.path.join(output_dir, "repo"), workspace_base)

    config = AppConfig(
        default_agent="CodeActAgent",
        runtime='eventstream',
        max_budget_per_task=4,
        max_iterations=max_iterations,
        sandbox=SandboxConfig(
            runtime_container_image=runtime_container_image,
            enable_auto_lint=False,
            use_host_network=False,
            # large enough timeout, since some testcases take very long to run
            timeout=300,
        ),
        # do not mount workspace
        workspace_base=workspace_base,
        workspace_mount_path=workspace_base,
    )
    config.set_llm_config(llm_config)

    runtime = create_runtime(config, sid=f"{issue.number}")
    initialize_runtime(runtime)

    instruction = issue_handler.get_instruction(issue, prompt_template, repo_instruction)
    # Here's how you can run the agent (similar to the `main` function) and get the final task state
    action = MessageAction(
        content=instruction,
    )
    state: State | None = await run_controller(
        config=config,
        initial_user_action=action,
        runtime=runtime,
        fake_user_response_fn=codeact_user_response,
    )
    if state is None:
        raise RuntimeError("Failed to run the agent.")

    # Get git patch
    return_val = await complete_runtime(runtime, base_commit)
    git_patch = return_val['git_patch']
    logger.info(
        f'Got git diff for instance {issue.number}:\n--------\n{git_patch}\n--------'
    )

    # Serialize histories
    histories = [dataclasses.asdict(event) for event in state.history.get_events()]
    metrics = state.metrics.get() if state.metrics else None

    # determine success based on the history and the issue description
    # success, comment_success, success_explanation = issue_handler.guess_success(issue, state.history, llm_config)
    success, comment_success, success_explanation = True, None, "Successfully created Git patch."

    if issue_handler.issue_type == "pr" and comment_success:
        success_log = "I have updated the PR and resolved some of the issues that were cited in the pull request review. Specifically, I identified the following revision requests, and all the ones that I think I successfully resolved are checked off. All the unchecked ones I was not able to resolve, so manual intervention may be required:\n"
        for success_indicator, explanation in zip(comment_success, json.loads(success_explanation)):
                status = colored("[X]", "red") if success_indicator else colored("[ ]", "red")
                bullet_point = colored("-", "yellow")
                success_log += f"\n{bullet_point} {status}: {explanation}"
        logger.info(success_log)



    # Save the output
    output = ResolverOutput(
        issue=issue,
        issue_type=issue_handler.issue_type,
        instruction=instruction,
        base_commit=base_commit,
        git_patch=git_patch,
        history=histories,
        metrics=metrics,
        success=success,
        comment_success=comment_success,
        success_explanation=success_explanation,
        error=state.last_error if state and state.last_error else None,
        model=llm_config.model.split("/")[-1],
    )
    return output

# This function tracks the progress AND write the output to a JSONL file
async def update_progress(output: ResolverOutput, output_fp: TextIO, pbar: tqdm) -> None:
    # output is now ResolverOutput, not Awaitable[ResolverOutput]
    resolved_output = output
    pbar.update(1)
    pbar.set_description(f'issue {resolved_output.issue.number}')
    pbar.set_postfix_str(
        f'Test Result: {resolved_output.metrics.get("test_result", "N/A") if resolved_output.metrics else "N/A"}'
    )
    logger.info(
        f'Finished issue {resolved_output.issue.number}: {resolved_output.metrics.get("test_result", "N/A") if resolved_output.metrics else "N/A"}'
    )
    # output_fp.write(resolved_output.model_dump_json() + "\n")
    # output_fp.flush()

def issue_handler_factory(issue_type: str, owner: str, repo: str, token: str) -> IssueHandlerInterface:
    if issue_type == "issue":
        return IssueHandler(owner, repo, token)
    elif issue_type == "pr":
        return PRHandler(owner, repo, token)
    else:
        raise ValueError(f"Invalid issue type: {issue_type}")

async def resolve_issues_with_random_models(
    owner: str,
    repo: str,
    token: str,
    username: str,
    max_iterations: int,
    limit_issues: int | None,
    num_workers: int,
    llm_configs: list[LLMConfig],
    runtime_container_image: str,
    prompt_template: str,
    issue_type: str,
    repo_instruction: str | None,
    issue_numbers: list[int] | None,
    issue_number: int,
    firebase_config: dict,
) -> None:
    """Randomly select two LLM models and call resolve_issues for each."""
    
    selected_llms = random.sample(llm_configs, 2)
    # logger.info(f"Selected LLM models: {selected_llms[0]} and {selected_llms[1]}")

    llm_config = selected_llms[0]
    # logger.info(f"Resolving issues using {llm_config.model.split("/")[-1]}: {llm_config}")
    resolverOutput1 = await resolve_issues(
        owner,
        repo,
        token,
        username,
        max_iterations,
        limit_issues,
        num_workers,
        "output1",
        llm_config,
        runtime_container_image,
        prompt_template,
        issue_type,
        repo_instruction,
        issue_numbers,
    )

    llm_config = selected_llms[1]
    # logger.info(f"Resolving issues using {llm_config.model.split("/")[-1]}: {llm_config}")
    resolverOutput2 = await resolve_issues(
        owner,
        repo,
        token,
        username,
        max_iterations,
        limit_issues,
        num_workers,
        "output2",
        llm_config,
        runtime_container_image,
        prompt_template,
        issue_type,
        repo_instruction,
        issue_numbers,
    )
    
    if asyncio.iscoroutine(resolverOutput1):
        logger.info(f"{resolverOutput1} is coroutine.")
    if asyncio.iscoroutine(resolverOutput2):
        logger.info(f"{resolverOutput2} is coroutine.")
    
    # TODO: Send commit hash to the firebase.
    await send_to_firebase (
        resolved_output1=resolverOutput1,
        resolved_output2=resolverOutput2,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        firebase_config=firebase_config,
        token=token,
        username=username,
        pr_type="draft"
    )

async def resolve_issues(
    owner: str,
    repo: str,
    token: str,
    username: str,
    max_iterations: int,
    limit_issues: int | None,
    num_workers: int,
    output_dir: str,
    llm_config: LLMConfig,
    runtime_container_image: str,
    prompt_template: str,  # Add this parameter
    issue_type: str,
    repo_instruction: str | None,
    issue_numbers: list[int] | None,
) -> ResolverOutput:
    """Resolve github issues.

    Args:
        owner: Github owner of the repo.
        repo: Github repository to resolve issues in form of `owner/repo`.
        token: Github token to access the repository.
        username: Github username to access the repository.
        max_iterations: Maximum number of iterations to run
        limit_issues: Limit the number of issues to resolve.
        output_dir: Output directory to write the results.
        runtime_container_image: Container image to use.
        prompt_template: Prompt template to use.
        repo_instruction: Repository instruction to use.
        issue_numbers: List of issue numbers to resolve.
    """

    issue_handler = issue_handler_factory(issue_type, owner, repo, token)

    # Load dataset
    issues: list[GithubIssue] = issue_handler.get_converted_issues()
    
    if issue_numbers is not None:
        issues = [issue for issue in issues if issue.number in issue_numbers]
        logger.info(f"Limiting resolving to issues {issue_numbers}.")
    if limit_issues is not None:
        issues = issues[:limit_issues]
        logger.info(f"Limiting resolving to first {limit_issues} issues.")

    # TEST METADATA
    model_name = llm_config.model.split("/")[-1]

    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    pathlib.Path(os.path.join(output_dir, "infer_logs")).mkdir(
        parents=True, exist_ok=True
    )
    logger.info(f"Using output directory: {output_dir}")

    # checkout the repo
    repo_dir = os.path.join(output_dir, "repo")
    if not os.path.exists(repo_dir):
        checkout_output = subprocess.check_output(
            [
            "git",
            "clone",
            f"https://{username}:{token}@github.com/{owner}/{repo}",
            f"{output_dir}/repo",
        ]
        ).decode("utf-8")
        if "fatal" in checkout_output:
            raise RuntimeError(f"Failed to clone repository: {checkout_output}")

    # get the commit id of current repo for reproducibility
    base_commit = (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir
        )
        .decode("utf-8")
        .strip()
    )
    logger.info(f"Base commit: {base_commit}")

    if repo_instruction is None:
        # Check for .openhands_instructions file in the workspace directory
        openhands_instructions_path = os.path.join(repo_dir, '.openhands_instructions')
        if os.path.exists(openhands_instructions_path):
            with open(openhands_instructions_path, 'r') as f:
                repo_instruction = f.read()

    # OUTPUT FILE / Moved the the job of writing to "output.jsonl" to send_to_firebase function
    # If we write the output here, the output does not contain the data (e.g., Base URL, headers, etc.) which is created in get_new_commit_hash function.
    output_file = os.path.join(output_dir, "output.jsonl")
    logger.info(f"Writing output to {output_file}")
    finished_numbers = set()
    if os.path.exists(output_file):
        with open(output_file, "r") as f:
            for line in f:
                data = ResolverOutput.model_validate_json(line)
                finished_numbers.add(data.issue.number)
        logger.warning(
            f"Output file {output_file} already exists. Loaded {len(finished_numbers)} finished issues."
        )
    output_fp = open(output_file, "a")

    logger.info(
        f"Resolving issues with Agent {AGENT_CLASS}, model {model_name}, max iterations {max_iterations}."
    )

    # =============================================
    # filter out finished issues
    new_issues = []
    for issue in issues:
        if issue.number in finished_numbers:
            logger.info(f"Skipping issue {issue.number} as it is already finished.")
            continue
        new_issues.append(issue)
    logger.info(
        f"Finished issues: {len(finished_numbers)}, Remaining issues: {len(issues)}"
    )
    # =============================================

    pbar = tqdm(total=len(issues))

    # This sets the multi-processing
    logger.info(f"Using {num_workers} workers.")
    
    resolverOutput = None

    try:
        # Replace the ProcessPoolExecutor with asyncio.gather
        tasks = []
        for issue in issues:
            
            # checkout to pr branch
            if issue_type == "pr":
                logger.info(f"Checking out to PR branch {issue.head_branch} for issue {issue.number}")
                
                subprocess.check_output(
                    ["git", "checkout", f"{issue.head_branch}"],
                    cwd=repo_dir,
                )

                base_commit = (
                    subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=repo_dir
                    )
                    .decode("utf-8")
                    .strip()
                )
            
            resolverOutput = await process_issue(
                issue,
                base_commit,
                max_iterations,
                llm_config,
                output_dir,
                runtime_container_image,
                prompt_template,
                issue_handler,
                repo_instruction,
                bool(num_workers > 1),
            )
            
            task = update_progress(
                resolverOutput,
                output_fp,
                pbar,
            )
            tasks.append(task)

        # Use asyncio.gather with a semaphore to limit concurrency
        sem = asyncio.Semaphore(num_workers)

        async def run_with_semaphore(task):
            async with sem:
                return await task

        await asyncio.gather(*[run_with_semaphore(task) for task in tasks])

    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Cleaning up...")
        cleanup()

    output_fp.close()
    logger.info("Finished.")
    
    return resolverOutput


def main():

    parser = argparse.ArgumentParser(description="Resolve issues from Github.")
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Github repository to resolve issues in form of `owner/repo`.",
    )
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
        help="Github username to access the repository.",
    )
    parser.add_argument(
        "--runtime-container-image",
        type=str,
        default=None,
        help="Container image to use.",
    )
    parser.add_argument(
        "--agent-class",
        type=str,
        default="CodeActAgent",
        help="The agent class to use.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum number of iterations to run.",
    )
    parser.add_argument(
        "--limit-issues",
        type=int,
        default=None,
        help="Limit the number of issues to resolve.",
    )
    parser.add_argument(
        "--issue-numbers",
        type=str,
        default=None,
        help="Comma separated list of issue numbers to resolve.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="Number of workers to use.",
    )
    parser.add_argument(
        "--llm-models",
        type=str,
        default=None,
        help="LLM models to use.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="LLM base URL to use.",
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        default=None,
        help="Path to the prompt template file in Jinja format.",
    )
    parser.add_argument(
        "--repo-instruction-file",
        type=str,
        default=None,
        help="Path to the repository instruction file in text format.",
    )
    parser.add_argument(
        "--issue-type",
        type=str,
        default="issue",
        choices=["issue", "pr"],
        help="Type of issue to resolve, either open issue or pr comments.",
    )

    my_args = parser.parse_args()

    runtime_container_image = my_args.runtime_container_image
    if runtime_container_image is None:
        runtime_container_image = f"ghcr.io/all-hands-ai/runtime:{openhands.__version__}-nikolaik"

    owner, repo = my_args.repo.split("/")
    token = (
        my_args.token if my_args.token else os.getenv("GITHUB_TOKEN")
    )
    username = (
        my_args.username
        if my_args.username
        else os.getenv("GITHUB_USERNAME")
    ) 

    if not token:
        raise ValueError("Github token is required.")

    # Suppose all llm models are comma separated.
    models = my_args.llm_models or os.environ["LLM_MODELS"]
    
    if models:
        model_names = [model.strip() for model in models.split(",")]
    else:
        raise ValueError("No LLM models provided in either the arguments or environment variables.")
    
    llm_configs = []
    
    Secrets.TOKEN = token
    
    # Retrieve the API keys from the endpoint.
    api_key = Secrets.get_api_key()
    
    # Suppose all the llm models are using the same api keys and base urls (: LLM Provider).
    for model in model_names:
        llm_configs.append(
            LLMConfig(
                model=model,
                # api_key=my_args.key or os.environ["LLM_API_KEY"],
                api_key=api_key,
                base_url=my_args.base_url or os.environ.get("LLM_BASE_URL", None),
            )
        )

    repo_instruction = None
    if my_args.repo_instruction_file:
        with open(my_args.repo_instruction_file, 'r') as f:
            repo_instruction = f.read()

    issue_numbers = None
    if my_args.issue_numbers:
        issue_numbers = [int(number) for number in my_args.issue_numbers.split(",")]

    issue_type = my_args.issue_type

    # Read the prompt template
    prompt_file = my_args.prompt_file
    if prompt_file is None:
        if issue_type == "issue":
            prompt_file = os.path.join(os.path.dirname(__file__), "prompts/resolve/basic-with-tests.jinja")
        else:
            prompt_file = os.path.join(os.path.dirname(__file__), "prompts/resolve/basic-followup.jinja") 
    with open(prompt_file, 'r') as f:
        prompt_template = f.read()
    
    # Retrieve the firebase configuration from the endpoint.
    raw_config = Secrets.get_firebase_config()
    firebase_config = load_firebase_config(raw_config)
    
    issue_number = issue_numbers[0]
    
    asyncio.run(
        resolve_issues_with_random_models(
            owner=owner,
            repo=repo,
            token=token,
            username=username,
            runtime_container_image=runtime_container_image,
            max_iterations=my_args.max_iterations,
            limit_issues=my_args.limit_issues,
            num_workers=my_args.num_workers,
            llm_configs=llm_configs,
            prompt_template=prompt_template,  # Pass the prompt template
            issue_type=issue_type,
            repo_instruction=repo_instruction,
            issue_numbers=issue_numbers,
            issue_number=issue_number,
            firebase_config=firebase_config,
        )
    )


if __name__ == "__main__":
    main()
