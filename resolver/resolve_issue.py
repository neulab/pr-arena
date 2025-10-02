import asyncio
import os
import pathlib
import random
import shlex
import subprocess
import time
import uuid
from argparse import Namespace
from typing import Any

import httpx
import requests

import firebase_admin
from firebase_admin import credentials, firestore

from resolver.daytona_patch import apply_daytona_patch
from resolver.error_tracker import ErrorTracker
from resolver.resolver_output import CustomResolverOutput
from resolver.secrets import Secrets
from resolver.send_pull_request import (
    apply_patch,
    initialize_repo,
    make_commit_with_summary,
)
from resolver.utils import get_comprehensive_language_info, load_firebase_config

# Apply daytona compatibility patch before any openhands imports
apply_daytona_patch()

from openhands.core.config import LLMConfig  # noqa: E402
from openhands.core.logger import openhands_logger as logger  # noqa: E402
from openhands.integrations.service_types import ProviderType  # noqa: E402
from openhands.resolver.interfaces.issue import Issue  # noqa: E402
from openhands.resolver.issue_handler_factory import IssueHandlerFactory  # noqa: E402
from openhands.resolver.issue_resolver import IssueResolver  # noqa: E402
from openhands.resolver.resolver_output import ResolverOutput  # noqa: E402
from openhands.runtime import Runtime  # noqa: E402

# Monkey patch OpenHands LLM to handle GPT-5 models
def patch_openhands_for_gpt5():
    """Patch OpenHands to exclude GPT-5 models from receiving stop tokens."""
    try:
        from openhands.llm import llm as openhands_llm_module
        if hasattr(openhands_llm_module, 'MODELS_WITHOUT_STOP_WORDS'):
            # Add GPT-5 models to the exclusion list (both base and full proxy names)
            gpt5_models = ['gpt-5', 'litellm_proxy/neulab/gpt-5', 'litellm_proxy/azure/gpt-5', 'azure/gpt-5']
            current_models = list(openhands_llm_module.MODELS_WITHOUT_STOP_WORDS)
            for gpt5_model in gpt5_models:
                if gpt5_model not in current_models:
                    current_models.append(gpt5_model)
            openhands_llm_module.MODELS_WITHOUT_STOP_WORDS = current_models
            # logger.info(f"Updated MODELS_WITHOUT_STOP_WORDS to include GPT-5: {openhands_llm_module.MODELS_WITHOUT_STOP_WORDS}")
    except Exception as e:
        logger.warning(f"Failed to patch OpenHands for GPT-5: {e}")

# Apply the patch
patch_openhands_for_gpt5()

# Don't make this configurable for now, unless we have other competitive agents
AGENT_CLASS = "CodeActAgent"


class PRArenaIssueResolver(IssueResolver):
    """PR Arena Issue Resolver that processes issues with multiple LLM models."""

    # Type annotations for class attributes
    llm_config: LLMConfig
    issue_handler: Any  # This will be set dynamically in _resolve_with_model
    output_dir: str

    def __init__(self, args: Namespace) -> None:
        # super().__init__(args) # Most shared arguments are processed by parent class

        parts = args.selected_repo.rsplit("/", 1)
        if len(parts) < 2:
            raise ValueError("Invalid repository format. Expected owner/repo")
        owner, repo = parts

        token = args.token or os.getenv("GITHUB_TOKEN") or os.getenv("GITLAB_TOKEN")
        username = args.username if args.username else os.getenv("GIT_USERNAME")
        if not username:
            raise ValueError("Username is required.")

        if not token:
            raise ValueError("Token is required.")

        platform = ProviderType.GITHUB

        base_url = args.llm_base_url
        api_version = os.environ.get("LLM_API_VERSION", None)
        llm_num_retries = int(os.environ.get("LLM_NUM_RETRIES", "4"))
        llm_retry_min_wait = int(os.environ.get("LLM_RETRY_MIN_WAIT", "5"))
        llm_retry_max_wait = int(os.environ.get("LLM_RETRY_MAX_WAIT", "30"))
        llm_retry_multiplier = int(os.environ.get("LLM_RETRY_MULTIPLIER", 2))
        llm_timeout = int(os.environ.get("LLM_TIMEOUT", 0))

        # Use provided API key if available, otherwise fetch from secrets
        llm_api_key = args.llm_api_key if hasattr(args, 'llm_api_key') and args.llm_api_key else Secrets.get_api_key()

        # Setup and validate container images
        self.sandbox_config = self._setup_sandbox_config(
            args.base_container_image,
            args.runtime_container_image,
            args.is_experimental,
        )

        # Initialize values for custom resolver
        self.token = token
        self.username = username
        Secrets.TOKEN = self.token

        multiple_models = args.llm_models or os.environ["LLM_MODELS"]
        if multiple_models:
            model_names = [model.strip() for model in multiple_models.split(",")]
        else:
            raise ValueError(
                "No LLM models provided in either the arguments or environment variables."
            )

        selected_models = random.sample(model_names, 2)
        # selected_models = model_names
        
        # Save selected models to file for timeout handling
        with open('/tmp/selected_models.txt', 'w') as f:
            f.write(','.join(selected_models))
        
        self.llm_configs = []

        for model in selected_models:
            # Determine if this model needs special parameter handling
            needs_drop_params = (
                "o1-mini" in model
                or "o3-mini" in model
                or "o4-mini" in model
                or "gemini" in model.lower()
                or "gpt-5" in model.lower()
            )

            if "gpt-5" in model.lower():
                gpt5_timeout = 300  # 5 minutes per API call
                print(f"GPT-5 detected: {model}, applying specialized configuration")

                # GPT-5 needs very specific configuration - only default temperature (1.0) is supported
                config_params = {
                    "model": model,
                    "api_key": llm_api_key,
                    "base_url": base_url,
                    "num_retries": llm_num_retries,
                    "retry_min_wait": llm_retry_min_wait,
                    "retry_max_wait": llm_retry_max_wait,
                    "retry_multiplier": llm_retry_multiplier,
                    "timeout": gpt5_timeout,
                    "drop_params": True,  # Critical for GPT-5
                    # Note: GPT-5 only supports default temperature (1.0)
                }
                
                llm_config = LLMConfig(**config_params)
                
                # GPT-5 specific parameter cleanup - remove all custom parameters that aren't supported
                # GPT-5 only supports reasoning_effort parameter through allowed_openai_params
                # These should be configured in the LiteLLM proxy YAML with:
                #   allowed_openai_params: ["reasoning_effort"]
            else:
                llm_config = LLMConfig(
                    model=model,
                    api_key=llm_api_key,
                    base_url=base_url,
                    num_retries=llm_num_retries,
                    retry_min_wait=llm_retry_min_wait,
                    retry_max_wait=llm_retry_max_wait,
                    retry_multiplier=llm_retry_multiplier,
                    timeout=llm_timeout,
                    drop_params=needs_drop_params,
                )

            if "gemini" in model.lower():
                # Gemini models have specific limitations on tool formats
                # Set additional Gemini-specific configurations if needed
                if hasattr(llm_config, "supports_function_calling"):
                    llm_config.supports_function_calling = True
                # Gemini models work better with simplified tool schemas
                if hasattr(llm_config, "simplify_tools"):
                    llm_config.simplify_tools = True

            # o-series models need specific parameter handling
            # These models don't support certain OpenAI parameters
            if "o4-mini" in model or "o3-mini" in model or "o1-mini" in model:
                # The drop_params flag is already set above, which tells LiteLLM
                # to automatically drop unsupported parameters
                pass

            self.llm_configs.append(llm_config)

            # Only set api_version if it was explicitly provided, otherwise let LLMConfig handle it
            if api_version is not None:
                llm_config.api_version = api_version

        repo_instruction = None
        if args.repo_instruction_file:
            with open(args.repo_instruction_file, "r") as f:
                repo_instruction = f.read()

        issue_type = args.issue_type

        # Read the prompt template
        prompt_file = os.path.join(
            os.path.dirname(__file__), "prompts/resolve/basic-with-tests.jinja"
        )

        with open(prompt_file, "r") as f:
            user_instructions_prompt_template = f.read()

        with open(
            prompt_file.replace(".jinja", "-conversation-instructions.jinja")
        ) as f:
            conversation_instructions_prompt_template = f.read()

        self.owner = owner
        self.repo = repo
        self.platform = platform
        self.max_iterations = args.max_iterations
        self.user_instructions_prompt_template = user_instructions_prompt_template
        self.conversation_instructions_prompt_template = (
            conversation_instructions_prompt_template
        )
        self.issue_type = issue_type
        self.repo_instruction = repo_instruction
        self.issue_number = args.issue_number
        self.comment_id = args.comment_id

        raw_config = Secrets.get_firebase_config()
        self.firebase_config = load_firebase_config(raw_config)

        # Initialize error tracker
        self.error_tracker = ErrorTracker(
            owner=self.owner,
            repo=self.repo,
            issue_number=self.issue_number,
            token=self.token,
        )

    async def complete_runtime(
        self,
        runtime: Runtime,
        base_commit: str,
    ) -> dict[str, Any]:
        patch = await super().complete_runtime(runtime, base_commit)
        runtime.close()
        return patch

    async def resolve_issues_with_random_models(self) -> None:
        uuid_ref = None
        models_info = {
            "model1": self.llm_configs[0].model.split("/")[-1]
            if len(self.llm_configs) > 0
            else "unknown",
            "model2": self.llm_configs[1].model.split("/")[-1]
            if len(self.llm_configs) > 1
            else "unknown",
        }

        try:
            # Run both agents in parallel using asyncio.gather
            # return_exceptions=True ensures we can handle individual failures
            results = await asyncio.gather(
                self._resolve_with_model(model_index=0, output_dir="output1"),
                self._resolve_with_model(model_index=1, output_dir="output2"),
                return_exceptions=True,
            )

            # Handle exceptions from either task
            resolver_output_1 = results[0]
            resolver_output_2 = results[1]

            if isinstance(resolver_output_1, Exception):
                raise resolver_output_1
            if isinstance(resolver_output_2, Exception):
                raise resolver_output_2

            # Send both outputs to Firebase after both complete
            # Type assertions to help mypy understand these are CustomResolverOutput
            assert isinstance(resolver_output_1, CustomResolverOutput)
            assert isinstance(resolver_output_2, CustomResolverOutput)

            await self.send_to_firebase(
                resolved_output_1=resolver_output_1,
                resolved_output_2=resolver_output_2,
                pr_type="draft",
            )

            # Get UUID from environment for error tracking if needed
            uuid_ref = os.getenv("UUID")

        except Exception as e:
            logger.error(f"Error in resolve_issues_with_random_models: {str(e)}")

            # Log the error to error_collection
            try:
                # Check if this was a git patch empty error
                git_patch_empty = "Openhands failed to make code changes" in str(e)

                # Determine which model caused the error
                model_error_details = None
                if models_info:
                    model_names = list(models_info.values())
                    if model_names:
                        model_error_details = (
                            f"Error occurred with models: {', '.join(model_names)}"
                        )

                await self.error_tracker.log_error(
                    error_type="agent_failure",
                    error_message=f"Agent failed during issue resolution: {str(e)}",
                    uuid_ref=uuid_ref,
                    models=models_info,
                    additional_context={
                        "stage": "issue_resolution",
                        "exception_type": type(e).__name__,
                    },
                    git_patch_empty=git_patch_empty,
                    model_error_details=model_error_details,
                )
            except Exception as tracking_error:
                logger.error(f"Failed to log error to Firebase: {tracking_error}")

            # Set FAILED=TRUE in GitHub environment
            github_env_path = os.getenv("GITHUB_ENV")
            if github_env_path:
                try:
                    with open(github_env_path, "a") as env_file:
                        env_file.write("FAILED=TRUE\n")
                except Exception as env_error:
                    logger.error(f"Failed to write to GITHUB_ENV: {env_error}")

            # Re-raise the exception so workflow can handle it
            raise

    async def _check_and_log_empty_patches(
        self,
        resolved_output_1: CustomResolverOutput,
        resolved_output_2: CustomResolverOutput,
        uuid_ref: str,
    ) -> None:
        """Check for empty git patches in successful resolutions and log them."""
        models_info = {
            "model1": resolved_output_1.model
            if hasattr(resolved_output_1, "model") and resolved_output_1.model
            else "unknown",
            "model2": resolved_output_2.model
            if hasattr(resolved_output_2, "model") and resolved_output_2.model
            else "unknown",
        }

        # Check if either model produced an empty patch
        model1_empty = (
            not resolved_output_1.git_patch or resolved_output_1.git_patch.strip() == ""
        )
        model2_empty = (
            not resolved_output_2.git_patch or resolved_output_2.git_patch.strip() == ""
        )

        if model1_empty or model2_empty:
            empty_models = []
            if model1_empty:
                empty_models.append(f"model1 ({models_info['model1']})")
            if model2_empty:
                empty_models.append(f"model2 ({models_info['model2']})")

            error_message = (
                f"One or more models produced empty patches: {', '.join(empty_models)}"
            )
            model_error_details = f"Empty patches from: {', '.join(empty_models)}"

            try:
                await self.error_tracker.log_error(
                    error_type="empty_patch_success",
                    error_message=error_message,
                    uuid_ref=uuid_ref,
                    models=models_info,
                    additional_context={
                        "stage": "successful_resolution_with_empty_patch",
                        "model1_empty": model1_empty,
                        "model2_empty": model2_empty,
                        "both_empty": model1_empty and model2_empty,
                    },
                    git_patch_empty=True,
                    model_error_details=model_error_details,
                )
                logger.info(
                    f"Logged empty patch tracking for successful resolution: {error_message}"
                )
            except Exception as tracking_error:
                logger.error(
                    f"Failed to log empty patch tracking to Firebase: {tracking_error}"
                )

    async def send_to_firebase(
        self,
        resolved_output_1: CustomResolverOutput,
        resolved_output_2: CustomResolverOutput,
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
        await self.get_new_commit_hash(
            output_dir="output1", resolver_output=resolved_output_1, pr_type=pr_type
        )
        await self.get_new_commit_hash(
            output_dir="output2", resolver_output=resolved_output_2, pr_type=pr_type
        )

        # Write the resolved output to a JSONL file
        with open(output_file1, "a") as output_fp:
            output_fp.write(resolved_output_1.model_dump_json() + "\n")

        with open(output_file2, "a") as output_fp:
            output_fp.write(resolved_output_2.model_dump_json() + "\n")

        # Send the resolved output to Firebase Firestore
        cred = credentials.Certificate(self.firebase_config)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        db = firestore.client()

        current_time = firestore.SERVER_TIMESTAMP

        repo_url = f"https://github.com/{self.owner}/{self.repo}"

        # Extract issue details from the first resolver output (both should have the same issue)
        issue = resolved_output_1.issue
        issue_number = issue.number
        issue_title = issue.title
        issue_body = issue.body

        # Collect language information
        language_info = get_comprehensive_language_info(
            owner=self.owner,
            repo=self.repo,
            token=self.token,
            git_patch_1=resolved_output_1.git_patch,
            git_patch_2=resolved_output_2.git_patch,
        )

        # logger.info(f"Language information collected: {language_info}")

        # Determine whether each model produced an empty git patch
        model1_git_patch = resolved_output_1.git_patch or ""
        model2_git_patch = resolved_output_2.git_patch or ""
        model1_empty_patch = model1_git_patch.strip() == ""
        model2_empty_patch = model2_git_patch.strip() == ""

        reference_id = str(uuid.uuid4())

        # Create unified issue data structure that handles both empty and non-empty patches
        issue_data = {
            "repo_url": repo_url,
            "issue_number": issue_number,
            "issue_title": issue_title,
            "issue_body": issue_body,
            "owner": self.owner,
            "repo": self.repo,
            "status": "pending",  # Always pending to allow arena comparison
            "language_info": language_info,
            "models": {
                "modelA": {
                    "modelName": resolved_output_1.model,
                    "commit_hash": resolved_output_1.commit_hash,
                    "agent_code": model1_git_patch,
                    "duration": resolved_output_1.duration
                    if resolved_output_1.duration
                    else None,
                    "success": resolved_output_1.success,
                    "comment_success": resolved_output_1.comment_success,
                    "iterations": {
                        "total_iterations": resolved_output_1.total_iterations,
                        "action_count": resolved_output_1.action_count,
                        "iteration_number": resolved_output_1.iteration_number,
                    },
                    "cost": {
                        "accumulated_cost": resolved_output_1.accumulated_cost,
                        "token_usage": resolved_output_1.token_usage,
                        "cost_per_input_token": resolved_output_1.cost_per_input_token,
                        "cost_per_output_token": resolved_output_1.cost_per_output_token,
                    },
                },
                "modelB": {
                    "modelName": resolved_output_2.model,
                    "commit_hash": resolved_output_2.commit_hash,
                    "agent_code": model2_git_patch,
                    "duration": resolved_output_2.duration
                    if resolved_output_2.duration
                    else None,
                    "success": resolved_output_2.success,
                    "comment_success": resolved_output_2.comment_success,
                    "iterations": {
                        "total_iterations": resolved_output_2.total_iterations,
                        "action_count": resolved_output_2.action_count,
                        "iteration_number": resolved_output_2.iteration_number,
                    },
                    "cost": {
                        "accumulated_cost": resolved_output_2.accumulated_cost,
                        "token_usage": resolved_output_2.token_usage,
                        "cost_per_input_token": resolved_output_2.cost_per_input_token,
                        "cost_per_output_token": resolved_output_2.cost_per_output_token,
                    },
                },
            },
            "winner": None,  # No winner determined yet
            "createdAt": current_time,
            "updatedAt": current_time,
            "installationToken": self.token,
        }

        issue_ref = db.collection("issue_collection").document(reference_id)
        issue_ref.set(issue_data)

        # Persist detailed histories for each model
        history_timestamp = firestore.SERVER_TIMESTAMP
        history_collection = db.collection("history_collection")
        history_entries = {
            f"{reference_id}_modelA": {
                "uuid": reference_id,
                "modelName": resolved_output_1.model,
                "history": resolved_output_1.history or [],
                "success": resolved_output_1.success,
                "language_info": language_info,
                "empty_git_patch": model1_empty_patch,
                "createdAt": history_timestamp,
            },
            f"{reference_id}_modelB": {
                "uuid": reference_id,
                "modelName": resolved_output_2.model,
                "history": resolved_output_2.history or [],
                "success": resolved_output_2.success,
                "language_info": language_info,
                "empty_git_patch": model2_empty_patch,
                "createdAt": history_timestamp,
            },
        }

        for document_id, history_data in history_entries.items():
            history_collection.document(document_id).set(history_data)

        current_time = firestore.SERVER_TIMESTAMP

        user_data = {
            "githubId": self.owner,
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
                    "programming_language": language_info.get(
                        "primary_language", "Unknown"
                    ),
                    "repo_languages": language_info.get(
                        "repo_language_percentages", {}
                    ),
                    "patch_languages": language_info.get(
                        "patch_language_percentages", {}
                    ),
                    "modelA": {
                        "modelName": resolved_output_1.model,
                    },
                    "modelB": {
                        "modelName": resolved_output_2.model,
                    },
                }
            },
        }

        # Store in user_collection with owner as document ID
        user_ref = db.collection("userdata_collection").document(self.owner)
        user_ref.set(user_data, merge=True)

        # Check for empty patches and log them
        await self._check_and_log_empty_patches(
            resolved_output_1, resolved_output_2, reference_id
        )

        github_env_path = os.getenv("GITHUB_ENV")
        if not github_env_path:
            raise RuntimeError("GITHUB_ENV environment variable is not set.")

        # Write the decision to the environment file
        with open(github_env_path, "a") as env_file:
            env_file.write(f"UUID={reference_id}\n")
            env_file.write("FAILED=FALSE\n")

        # print("Data successfully written to Firestore collections 'issue_collection' and 'user_collection'")
        # print(f"Issue ID: {self.issue_number}, Models: {resolved_output_1.model} vs {resolved_output_2.model}")

    async def resolve_issue(
        self,
        reset_logger: bool = False,
    ) -> CustomResolverOutput:
        """Resolve a single issue.

        Args:
            reset_logger: Whether to reset the logger for multiprocessing.
        """
        start_time = time.time()
        output = None
        customOutput = None

        # Load dataset
        issues: list[Issue] = self.issue_handler.get_converted_issues(
            issue_numbers=[self.issue_number], comment_id=self.comment_id
        )

        if not issues:
            raise ValueError(
                f"No issues found for issue number {self.issue_number}. Please verify that:\n"
                f"1. The issue/PR #{self.issue_number} exists in the repository {self.owner}/{self.repo}\n"
                f"2. You have the correct permissions to access it\n"
                f"3. The repository name is spelled correctly"
            )

        issue = issues[0]

        # Update error tracker with issue information
        self.error_tracker.set_issue_info(issue.title, issue.body)

        if self.comment_id is not None:
            if (
                self.issue_type == "pr"
                and not issue.review_comments
                and not issue.review_threads
                and not issue.thread_comments
            ):
                raise ValueError(
                    f"Comment ID {self.comment_id} did not have a match for issue {issue.number}"
                )

            if self.issue_type == "issue" and not issue.thread_comments:
                raise ValueError(
                    f"Comment ID {self.comment_id} did not have a match for issue {issue.number}"
                )

        # Setup directories
        pathlib.Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(os.path.join(self.output_dir, "infer_logs")).mkdir(
            parents=True, exist_ok=True
        )
        logger.info(f"Using output directory: {self.output_dir}")

        # checkout the repo
        repo_dir = os.path.join(self.output_dir, "repo")
        if not os.path.exists(repo_dir):
            checkout_output = subprocess.check_output(
                [
                    "git",
                    "clone",
                    self.issue_handler.get_clone_url(),
                    f"{self.output_dir}/repo",
                ]
            ).decode("utf-8")
            if "fatal" in checkout_output:
                raise RuntimeError(f"Failed to clone repository: {checkout_output}")

        # get the commit id of current repo for reproducibility
        base_commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir)
            .decode("utf-8")
            .strip()
        )
        logger.info(f"Base commit: {base_commit}")

        if self.repo_instruction is None:
            # Check for .openhands_instructions file in the workspace directory
            openhands_instructions_path = os.path.join(
                repo_dir, ".openhands_instructions"
            )
            if os.path.exists(openhands_instructions_path):
                with open(openhands_instructions_path, "r") as f:
                    self.repo_instruction = f.read()

        # OUTPUT FILE
        output_file = os.path.join(self.output_dir, "output.jsonl")
        logger.info(f"Writing output to {output_file}")

        # Check if this issue was already processed
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                for line in f:
                    data = ResolverOutput.model_validate_json(line)
                    if data.issue.number == self.issue_number:
                        logger.warning(
                            f"Issue {self.issue_number} was already processed. Skipping."
                        )
                        return CustomResolverOutput(**data.model_dump())

        logger.info(
            f"Resolving issue {self.issue_number} with Agent {AGENT_CLASS}, model **MODEL NAME REDACTED**, max iterations {self.max_iterations}."
        )

        try:
            # checkout to pr branch if needed
            if self.issue_type == "pr":
                branch_to_use = issue.head_branch
                logger.info(
                    f"Checking out to PR branch {branch_to_use} for issue {issue.number}"
                )

                if not branch_to_use:
                    raise ValueError("Branch name cannot be None")

                # Fetch the branch first to ensure it exists locally
                fetch_cmd = ["git", "fetch", "origin", branch_to_use]
                subprocess.check_output(
                    fetch_cmd,
                    cwd=repo_dir,
                )

                # Checkout the branch
                checkout_cmd = ["git", "checkout", branch_to_use]
                subprocess.check_output(
                    checkout_cmd,
                    cwd=repo_dir,
                )

                base_commit = (
                    subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir)
                    .decode("utf-8")
                    .strip()
                )

            logger.info(
                f"Issue Resolve - Using base commit {base_commit} for issue {issue.number}\nOutput successfully written to {output_file}"
            )

            output = await self.process_issue(
                issue,
                base_commit,
                self.issue_handler,
                reset_logger,
            )

            customOutput = CustomResolverOutput(**output.model_dump())
            
            # Extract cost information from metrics if available
            self._calculate_and_set_costs(customOutput)
            
            # Calculate iteration counts from history
            self._calculate_and_set_iterations(customOutput)

        finally:
            logger.info("Finished.")

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Total time taken: {duration} seconds")

            if customOutput is not None:  # Check if customOutput was created
                customOutput.duration = duration
                # Log cost information
                if customOutput.accumulated_cost is not None:
                    logger.info(f"Total cost for issue resolution: ${customOutput.accumulated_cost:.4f}")
                # logger.info(f"Output: {customOutput}")
                return customOutput
            else:
                # Create a minimal error output if something went wrong
                error_output = CustomResolverOutput(
                    issue=issue,
                    issue_type=self.issue_type,
                    instruction="",
                    base_commit=base_commit,
                    git_patch=None,
                    history=[],
                    metrics={},
                    success=False,
                    comment_success=None,
                    result_explanation="Error occurred during processing",
                    error="Failed to complete processing",
                    duration=duration,
                    iteration_number=0,
                )
                return error_output

    async def get_new_commit_hash(
        self, output_dir, resolver_output: CustomResolverOutput, pr_type: str
    ) -> None:
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

            # 3) make_commit [NEW!] with Summary
            # logger.info(f"[DEBUG] Resolver Output: {resolver_output} to {output_dir}")
            # make_commit(patched_repo_dir, resolver_output.issue, resolver_output.issue_type)
            make_commit_with_summary(
                patched_repo_dir,
                resolver_output.issue,
                resolver_output.issue_type,
                resolver_output,
                branch_name,
                output_dir,
            )

            # 4) branch checkout and push
            branch_name, default_branch, base_url, headers = (
                self.prepare_branch_and_push(
                    patch_dir=patched_repo_dir,
                    pr_type=pr_type,
                )
            )

        resolver_output.branch_name = branch_name
        resolver_output.default_branch = default_branch
        resolver_output.base_url = base_url
        resolver_output.headers = headers

        # 5) Retrieve commit hash
        rev_parse_cmd = f'git -C "{patched_repo_dir}" rev-parse HEAD'
        result = subprocess.run(
            rev_parse_cmd, shell=True, capture_output=True, text=True
        )
        new_hash = result.stdout.strip()

        # 6) Assign it back to the resolver_output
        resolver_output.commit_hash = new_hash
        resolver_output.repo_dir = patched_repo_dir

        return

    async def _resolve_with_model(
        self, model_index: int, output_dir: str
    ) -> CustomResolverOutput:
        """Resolve issue with a specific model configuration.

        This method creates a completely independent resolver context for parallel execution,
        ensuring no shared state between concurrent model runs.

        Args:
            model_index: Index of the model configuration to use (0 or 1)
            output_dir: Output directory for this model's results

        Returns:
            CustomResolverOutput: The resolved output for this model
        """
        llm_config = self.llm_configs[model_index]

        # Create a completely independent issue handler factory for this model
        # This ensures thread safety and no shared state between parallel executions
        factory = IssueHandlerFactory(
            owner=self.owner,
            repo=self.repo,
            token=self.token,
            username=self.username,
            platform=self.platform,
            base_domain="github.com",
            issue_type=self.issue_type,
            llm_config=llm_config,
        )

        # Create independent issue handler for this execution
        issue_handler = factory.create()

        # Store current instance state to avoid conflicts
        current_llm_config = self.llm_config if hasattr(self, "llm_config") else None
        current_issue_handler = (
            self.issue_handler if hasattr(self, "issue_handler") else None
        )
        current_output_dir = self.output_dir if hasattr(self, "output_dir") else None
        current_error_tracker_issue_info = (
            self.error_tracker.issue_title,
            self.error_tracker.issue_body,
        )

        # Create a temporary backup of instance state for safe parallel execution
        backup_state = {
            "llm_config": current_llm_config,
            "issue_handler": current_issue_handler,
            "output_dir": current_output_dir,
        }

        try:
            # Temporarily set instance variables for this model's execution
            # This allows resolve_issue() to access the correct configuration
            self.llm_config = llm_config
            self.issue_handler = issue_handler
            self.output_dir = output_dir

            # Resolve the issue with this specific model configuration
            # This is the main time-consuming operation that benefits from parallelization
            resolver_output = await self.resolve_issue()

            # Update the output with the correct model name for identification
            resolver_output_dict = resolver_output.model_dump()
            resolver_output_dict["model"] = llm_config.model.split("/")[-1]
            resolved_output = CustomResolverOutput(**resolver_output_dict)
            
            # Calculate costs for this specific model's execution
            self._calculate_and_set_costs_for_model(resolved_output, llm_config)
            
            # Calculate iteration counts from history
            self._calculate_and_set_iterations(resolved_output)

            return resolved_output

        except Exception as e:
            # Ensure proper exception handling for parallel execution
            logger.error(
                f"Error in _resolve_with_model for model {model_index}: {str(e)}"
            )
            raise

        finally:
            # Restore the original instance state to avoid affecting other operations
            # This is critical for maintaining consistency in parallel execution
            for key, value in backup_state.items():
                if value is not None:
                    setattr(self, key, value)
                elif hasattr(self, key):
                    delattr(self, key)

            # Restore error tracker issue info if it was changed
            if current_error_tracker_issue_info != (None, None):
                self.error_tracker.set_issue_info(*current_error_tracker_issue_info)

    def prepare_branch_and_push(
        self,
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
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}"

        # Create a new branch name
        base_branch_name = f"openhands-fix-issue-{self.issue_number}"
        branch_name = base_branch_name + "-try1"
        attempt = 1

        # Ensure the branch doesn't already exist on the remote
        while (
            httpx.get(f"{base_url}/branches/{branch_name}", headers=headers).status_code
            == 200
        ):
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
            raise RuntimeError(
                f"Failed to create a new branch {branch_name} in {patch_dir}."
            )

        # Determine the repository to push to
        push_owner = self.owner
        push_repo = self.repo

        # Construct push command
        username_and_token = (
            f"{self.username}:{self.token}"
            if self.username
            else f"x-auth-token:{self.token}"
        )
        push_command = (
            f"git -C {shlex.quote(patch_dir)} push "
            f"https://{username_and_token}@github.com/"
            f"{push_owner}/{push_repo}.git {shlex.quote(branch_name)}"
        )
        result = subprocess.run(
            push_command, shell=True, capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error pushing changes\n{push_command}\n{result.stderr}")
            raise RuntimeError("Failed to push changes to the remote repository")

        return branch_name, default_branch, base_url, headers

    def _calculate_and_set_costs(self, resolver_output: CustomResolverOutput) -> None:
        """Calculate and set cost information from OpenHands metrics."""
        try:
            # Extract metrics from the resolver output
            if resolver_output.metrics and hasattr(resolver_output.metrics, 'accumulated_cost'):
                resolver_output.accumulated_cost = resolver_output.metrics.accumulated_cost
            elif resolver_output.metrics and isinstance(resolver_output.metrics, dict):
                resolver_output.accumulated_cost = resolver_output.metrics.get('accumulated_cost', 0.0)
            
            # Extract token usage information
            if resolver_output.metrics and hasattr(resolver_output.metrics, 'accumulated_token_usage'):
                resolver_output.token_usage = resolver_output.metrics.accumulated_token_usage
            elif resolver_output.metrics and isinstance(resolver_output.metrics, dict):
                resolver_output.token_usage = resolver_output.metrics.get('accumulated_token_usage', {})
            
            # Get cost per token from LLM config if available
            if hasattr(self, 'llm_config') and self.llm_config:
                resolver_output.cost_per_input_token = self.llm_config.input_cost_per_token
                resolver_output.cost_per_output_token = self.llm_config.output_cost_per_token
                
                # If accumulated cost isn't available but we have token counts and rates, calculate it
                if not resolver_output.accumulated_cost and resolver_output.token_usage:
                    input_tokens = 0
                    output_tokens = 0
                    
                    if isinstance(resolver_output.token_usage, dict):
                        # Sum up tokens from different components
                        for component_usage in resolver_output.token_usage.values():
                            if isinstance(component_usage, dict):
                                input_tokens += component_usage.get('prompt_tokens', 0)
                                output_tokens += component_usage.get('completion_tokens', 0)
                    
                    # Calculate cost
                    input_cost = input_tokens * (self.llm_config.input_cost_per_token or 0)
                    output_cost = output_tokens * (self.llm_config.output_cost_per_token or 0)
                    resolver_output.accumulated_cost = input_cost + output_cost
                    
        except Exception as e:
            logger.warning(f"Failed to calculate costs for resolver output: {e}")
            resolver_output.accumulated_cost = 0.0
            resolver_output.token_usage = {}

    def _calculate_and_set_costs_for_model(self, resolver_output: CustomResolverOutput, llm_config: "LLMConfig") -> None:
        """Calculate and set cost information for a specific model configuration."""
        try:
            # Extract metrics from the resolver output
            if resolver_output.metrics and hasattr(resolver_output.metrics, 'accumulated_cost'):
                resolver_output.accumulated_cost = resolver_output.metrics.accumulated_cost
            elif resolver_output.metrics and isinstance(resolver_output.metrics, dict):
                resolver_output.accumulated_cost = resolver_output.metrics.get('accumulated_cost', 0.0)
            
            # Extract token usage information
            if resolver_output.metrics and hasattr(resolver_output.metrics, 'accumulated_token_usage'):
                resolver_output.token_usage = resolver_output.metrics.accumulated_token_usage
            elif resolver_output.metrics and isinstance(resolver_output.metrics, dict):
                resolver_output.token_usage = resolver_output.metrics.get('accumulated_token_usage', {})
            
            # Set cost per token from the specific LLM config
            resolver_output.cost_per_input_token = llm_config.input_cost_per_token
            resolver_output.cost_per_output_token = llm_config.output_cost_per_token
            
            # If accumulated cost isn't available but we have token counts and rates, calculate it
            if not resolver_output.accumulated_cost and resolver_output.token_usage:
                input_tokens = 0
                output_tokens = 0
                
                if isinstance(resolver_output.token_usage, dict):
                    # Sum up tokens from different components
                    for component_usage in resolver_output.token_usage.values():
                        if isinstance(component_usage, dict):
                            input_tokens += component_usage.get('prompt_tokens', 0)
                            output_tokens += component_usage.get('completion_tokens', 0)
                
                # Calculate cost
                input_cost = input_tokens * (llm_config.input_cost_per_token or 0)
                output_cost = output_tokens * (llm_config.output_cost_per_token or 0)
                resolver_output.accumulated_cost = input_cost + output_cost
                
            logger.info(f"Cost calculation for **MODEL NAME REDACTED**: ${resolver_output.accumulated_cost:.4f}")
                
        except Exception as e:
            logger.warning(f"Failed to calculate costs for model **MODEL NAME REDACTED**: {e}")
            resolver_output.accumulated_cost = 0.0
            resolver_output.token_usage = {}

    def _calculate_and_set_iterations(self, resolver_output: CustomResolverOutput) -> None:
        """Calculate and set iteration information from OpenHands history."""
        try:
            iteration_number = 0
            if resolver_output.history:
                # Total events in history (actions + observations)
                resolver_output.total_iterations = len(resolver_output.history)

                # Count agent actions (approximate iteration count)
                action_count = 0
                for event in resolver_output.history:
                    # OpenHands history events have different structures
                    if not isinstance(event, dict):
                        continue

                    event_type = str(event.get('event_type', '')).lower()
                    source = str(event.get('source', '')).lower()
                    action_name = event.get('action')

                    # Count events that represent agent actions/iterations
                    if (
                        event_type in ['action', 'agent_action']
                        or source in ['agent']
                        or action_name is not None
                    ):
                        action_count += 1

                    # Derive iteration number from actionable agent events
                    if action_name is not None:
                        action_name_str = str(action_name).lower()
                        if action_name_str in ['message', 'system']:
                            continue
                        iteration_number += 1

                resolver_output.action_count = action_count
                resolver_output.iteration_number = iteration_number
                logger.info(
                    "Iteration tracking: %s total events, %s agent actions, %s iterations",
                    resolver_output.total_iterations,
                    action_count,
                    iteration_number,
                )
            else:
                resolver_output.total_iterations = 0
                resolver_output.action_count = 0
                resolver_output.iteration_number = 0
        except Exception as e:
            logger.warning(f"Failed to calculate iterations: {e}")
            resolver_output.total_iterations = 0
            resolver_output.action_count = 0
            resolver_output.iteration_number = 0


def main() -> None:
    import argparse

    def int_or_none(value: str) -> int | None:
        if value.lower() == "none":
            return None
        else:
            return int(value)

    parser = argparse.ArgumentParser(description="Resolve issues from Github.")
    parser.add_argument(
        "--selected-repo",
        type=str,
        required=True,
        help="repository to resolve issues in form of `owner/repo`.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="token to access the repository.",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help="username to access the repository.",
    )
    parser.add_argument(
        "--base-container-image",
        type=str,
        default=None,
        help="base container image to use.",
    )
    parser.add_argument(
        "--runtime-container-image",
        type=str,
        default=None,
        help="Container image to use.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximum number of iterations to run.",
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number to resolve.",
    )
    parser.add_argument(
        "--comment-id",
        type=int_or_none,
        required=False,
        default=None,
        help="Resolve a specific comment",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory to write the results.",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="Mock GPT",
        help="Mock model name to adapt with the existing code.",
    )
    parser.add_argument(
        "--llm-models",
        type=str,
        default=None,
        help="LLM models to use.",
    )
    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="LLM API key to use.",
    )
    parser.add_argument(
        "--llm-base-url",
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
    parser.add_argument(
        "--is-experimental",
        type=lambda x: x.lower() == "true",
        help="Whether to run in experimental mode.",
    )
    parser.add_argument(
        "--base-domain",
        type=str,
        default=None,
        help='Base domain for the git server (defaults to "github.com" for GitHub and "gitlab.com" for GitLab)',
    )

    my_args = parser.parse_args()
    issue_resolver = PRArenaIssueResolver(my_args)

    asyncio.run(issue_resolver.resolve_issues_with_random_models())


if __name__ == "__main__":
    main()
