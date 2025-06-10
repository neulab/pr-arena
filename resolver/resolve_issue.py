import asyncio
import dataclasses
import json
import os
import pathlib
import shutil
import subprocess
from argparse import Namespace
from typing import Any, cast
import uuid
import random
import shlex
import time
import requests
import httpx
from enum import Enum

from resolver.secrets import Secrets
from resolver.utils import load_firebase_config
from resolver.resolver_output import CustomResolverOutput
from resolver.send_pull_request import (
    initialize_repo,
    apply_patch,
    make_commit
)

import openhands
from openhands.core.logger import openhands_logger as logger
from openhands.resolver.interfaces.issue import Issue
from openhands.resolver.resolver_output import ResolverOutput

from openhands.resolver.issue_resolver import IssueResolver
from openhands.core.config import LLMConfig
from openhands.runtime import Runtime

from openhands.integrations.service_types import ProviderType
from openhands.resolver.issue_handler_factory import IssueHandlerFactory
from openhands.core.config.utils import load_openhands_config

import firebase_admin
from firebase_admin import credentials, firestore

# Don't make this confgurable for now, unless we have other competitive agents
AGENT_CLASS = 'CodeActAgent'


class PRArenaIssueResolver(IssueResolver):

    def __init__(self, args: Namespace):
        # super().__init__(args) # Most shared arguments are processed by parent class
        parts = args.selected_repo.rsplit('/', 1)
        if len(parts) < 2:
            raise ValueError('Invalid repository format. Expected owner/repo')
        owner, repo = parts

        token = args.token or os.getenv('GITHUB_TOKEN') or os.getenv('GITLAB_TOKEN')
        username = args.username if args.username else os.getenv('GIT_USERNAME')
        if not username:
            raise ValueError('Username is required.')

        if not token:
            raise ValueError('Token is required.')

        platform = ProviderType.GITHUB

        repo_instruction = None
        if args.repo_instruction_file:
            with open(args.repo_instruction_file, 'r') as f:
                repo_instruction = f.read()

        issue_type = args.issue_type

        # Read the prompt template
        prompt_file = args.prompt_file
        if prompt_file is None:
            if issue_type == 'issue':
                prompt_file = os.path.join(
                    os.path.dirname(__file__), 'prompts/resolve/basic-with-tests.jinja'
                )
            else:
                prompt_file = os.path.join(
                    os.path.dirname(__file__), 'prompts/resolve/basic-followup.jinja'
                )
        with open(prompt_file, 'r') as f:
            user_instructions_prompt_template = f.read()

        with open(
            prompt_file.replace('.jinja', '-conversation-instructions.jinja')
        ) as f:
            conversation_instructions_prompt_template = f.read()

        base_domain = 'github.com'

        self.output_dir = args.output_dir
        self.issue_type = issue_type
        self.issue_number = args.issue_number

        self.workspace_base = self.build_workspace_base(
            self.output_dir, self.issue_type, self.issue_number
        )

        self.max_iterations = args.max_iterations

        self.app_config = self.update_openhands_config(
            load_openhands_config(),
            self.max_iterations,
            self.workspace_base,
            args.base_container_image,
            args.runtime_container_image,
            args.is_experimental,
        )

        self.owner = owner
        self.repo = repo
        self.platform = platform
        self.user_instructions_prompt_template = user_instructions_prompt_template
        self.conversation_instructions_prompt_template = (
            conversation_instructions_prompt_template
        )
        self.repo_instruction = repo_instruction
        self.comment_id = args.comment_id

        factory = IssueHandlerFactory(
            owner=self.owner,
            repo=self.repo,
            token=token,
            username=username,
            platform=self.platform,
            base_domain=base_domain,
            issue_type=self.issue_type,
            llm_config=self.app_config.get_llm_config(),
        )
        self.issue_handler = factory.create()

        # Initialize values for custom resolver

        multiple_models = args.llm_models or os.environ["LLM_MODELS"]
        if multiple_models:
            model_names = [model.strip() for model in multiple_models.split(",")]
        else:
            raise ValueError("No LLM models provided in either the arguments or environment variables.")
        

        self.token = token
        Secrets.TOKEN = self.token
        api_key = Secrets.get_api_key()
        self.llm_configs = []

        for model in model_names:
            self.llm_configs.append(
                LLMConfig(
                    model=model,
                    api_key=api_key,
                    base_url=args.llm_base_url or os.environ.get("LLM_BASE_URL", None),
                )
            )


        raw_config = Secrets.get_firebase_config()
        self.firebase_config = load_firebase_config(raw_config)
        
    async def complete_runtime(
        self,
        runtime: Runtime,
        base_commit: str,
    ) -> dict[str, Any]:
        patch = await super().complete_runtime(runtime, base_commit)
        runtime.close()
        return patch

    async def resolve_issues_with_random_models(self):
        selected_llms = random.sample(self.llm_configs, 2)
        self.llm_config = selected_llms[0] # Set current config
        resolver_output_1: ResolverOutput = await self.resolve_issue()
        resolver_output_1 = CustomResolverOutput(**resolver_output_1.model_dump(),
                                                 model=self.llm_config.model.split("/")[-1])


        self.llm_config = selected_llms[1] # Set new config
        resolver_output_2: ResolverOutput = await self.resolve_issue()
        resolver_output_2 = CustomResolverOutput(**resolver_output_2.model_dump(),
                                                 model=self.llm_config.model.split("/")[-1])



        # TODO: Send commit hash to the firebase.
        await self.send_to_firebase (
            resolved_output_1=resolver_output_1,
            resolved_output_2=resolver_output_2,
            pr_type="draft"
        )

    async def send_to_firebase (
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
        self.get_new_commit_hash(
            output_dir="output1",
            resolver_output=resolved_output_1,
            pr_type=pr_type
        
        )
        self.get_new_commit_hash(
            output_dir="output2",
            resolver_output=resolved_output_2,
            pr_type=pr_type
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
        issue_name = f"Issue #{self.issue_number}"
        
        model_reference = {
            "claude-3-7-sonnet-20250219": "model1",
            "gpt-4o-2024-05-13": "model2",
            "Meta-Llama-3.1-405B-Instruct": "model3",
            "deepseek-chat": "model4",
            "gemini-2.5-pro-exp-03-25": "model5",
            "deepseek-reasoner": "model6",
            "Meta-Llama-3.1-8B-Instruct": "model7",
            "o3-mini": "model8",
        }
        
        model1_id = model_reference.get((cast(str, resolved_output_1.model)), "Model ID Not Found")
        model2_id = model_reference.get((cast(str, resolved_output_2.model)), "Model ID Not Found")
        
        if not resolved_output_1.git_patch or not resolved_output_2.git_patch or resolved_output_1.success is False or resolved_output_2.success is False:
            issue_data = {
                "repo_url": repo_url,
                "issue_name": issue_name,
                "owner": self.owner,
                "repo": self.repo,
                "status": "failed",
                "models": {
                    "modelA": {
                        "modelId": model1_id,
                        "modelName": resolved_output_1.model,
                        "commit_hash": resolved_output_1.commit_hash,
                        "agent_code": resolved_output_1.git_patch if resolved_output_1.git_patch else "",
                        "duration": resolved_output_1.duration if resolved_output_1.duration else None
                    },
                    "modelB": {
                        "modelId": model2_id,
                        "modelName": resolved_output_2.model,
                        "commit_hash": resolved_output_2.commit_hash,
                        "agent_code": resolved_output_2.git_patch if resolved_output_2.git_patch else "",
                        "duration": resolved_output_2.duration if resolved_output_2.duration else None
                    }
                },
                "winner": None,  # No winner determined yet
                "createdAt": current_time,
                "updatedAt": current_time,
                "installationToken": self.token
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
            "owner": self.owner,
            "repo": self.repo,
            "status": "pending",  # Initial status is pending
            "models": {
                "modelA": {
                    "modelId": model1_id,
                    "modelName": resolved_output_1.model,
                    "commit_hash": resolved_output_1.commit_hash,
                    "agent_code": resolved_output_1.git_patch if resolved_output_1.git_patch else "",
                    "duration": resolved_output_1.duration if resolved_output_1.duration else None
                },
                "modelB": {
                    "modelId": model2_id,
                    "modelName": resolved_output_2.model,
                    "commit_hash": resolved_output_2.commit_hash,
                    "agent_code": resolved_output_2.git_patch if resolved_output_2.git_patch else "",
                    "duration": resolved_output_1.duration if resolved_output_1.duration else None
                }
            },
            "winner": None,  # No winner determined yet
            "createdAt": current_time,
            "updatedAt": current_time,
            "installationToken": self.token
        }
        
        reference_id = str(uuid.uuid4())
        
        issue_ref = db.collection("issue_collection").document(reference_id)
        issue_ref.set(issue_data)
        
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
                    "modelA": {
                        "modelId": model1_id,
                        "modelName": resolved_output_1.model
                    },
                    "modelB": {
                        "modelId": model2_id,
                        "modelName": resolved_output_2.model
                    }
                }
            }
        }
        
        # Store in user_collection with owner as document ID
        user_ref = db.collection("userdata_collection").document(self.owner)
        user_ref.set(user_data, merge=True)
        
        github_env_path = os.getenv("GITHUB_ENV")
        if not github_env_path:
            raise RuntimeError("GITHUB_ENV environment variable is not set.")

        # Write the decision to the environment file
        with open(github_env_path, "a") as env_file:
            env_file.write(f"UUID={reference_id}\n")
            env_file.write("FAILED=FALSE\n")
        
        print("Data successfully written to Firestore collections 'issue_collection' and 'user_collection'")
        print(f"Issue ID: {self.issue_number}, Models: {resolved_output_1.model} vs {resolved_output_2.model}")

    
    async def resolve_issue(
        self,
        reset_logger: bool = False,
    ) -> ResolverOutput:
        """Resolve a single issue.

        Args:
            reset_logger: Whether to reset the logger for multiprocessing.
        """
        start_time = time.time()
        output = None
        
        issue = self.extract_issue()

        if self.comment_id is not None:
            if (
                self.issue_type == 'pr'
                and not issue.review_comments
                and not issue.review_threads
                and not issue.thread_comments
            ):
                raise ValueError(
                    f'Comment ID {self.comment_id} did not have a match for issue {issue.number}'
                )

            if self.issue_type == 'issue' and not issue.thread_comments:
                raise ValueError(
                    f'Comment ID {self.comment_id} did not have a match for issue {issue.number}'
                )

        # TEST METADATA
        model_name = self.llm_config.model.split('/')[-1]

        pathlib.Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(os.path.join(self.output_dir, 'infer_logs')).mkdir(
            parents=True, exist_ok=True
        )
        logger.info(f'Using output directory: {self.output_dir}')

        # checkout the repo
        repo_dir = os.path.join(self.output_dir, 'repo')
        if not os.path.exists(repo_dir):
            checkout_output = subprocess.check_output(  # noqa: ASYNC101
                [
                    'git',
                    'clone',
                    self.issue_handler.get_clone_url(),
                    f'{self.output_dir}/repo',
                ]
            ).decode('utf-8')
            if 'fatal' in checkout_output:
                raise RuntimeError(f'Failed to clone repository: {checkout_output}')

        # get the commit id of current repo for reproducibility
        base_commit = (
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo_dir)  # noqa: ASYNC101
            .decode('utf-8')
            .strip()
        )
        logger.info(f'Base commit: {base_commit}')

        # Commenting out because we are not using repo_instruction for PR-Arena
        # if self.repo_instruction is None:
        #     # Check for .openhands_instructions file in the workspace directory
        #     openhands_instructions_path = os.path.join(
        #         repo_dir, '.openhands_instructions'
        #     )
        #     if os.path.exists(openhands_instructions_path):
        #         with open(openhands_instructions_path, 'r') as f:  # noqa: ASYNC101
        #             self.repo_instruction = f.read()

        # OUTPUT FILE
        output_file = os.path.join(self.output_dir, 'output.jsonl')
        logger.info(f'Writing output to {output_file}')

        # Check if this issue was already processed
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:  # noqa: ASYNC101
                for line in f:
                    data = ResolverOutput.model_validate_json(line)
                    if data.issue.number == self.issue_number:
                        logger.warning(
                            f'Issue {self.issue_number} was already processed. Skipping.'
                        )
                        return

        logger.info(
            f'Resolving issue {self.issue_number} with Agent {AGENT_CLASS}, model {model_name}, max iterations {self.max_iterations}.'
        )
        
        try:
            # checkout to pr branch if needed
            if self.issue_type == 'pr':
                branch_to_use = issue.head_branch
                logger.info(
                    f'Checking out to PR branch {branch_to_use} for issue {issue.number}'
                )

                if not branch_to_use:
                    raise ValueError('Branch name cannot be None')

                # Fetch the branch first to ensure it exists locally
                fetch_cmd = ['git', 'fetch', 'origin', branch_to_use]
                subprocess.check_output(  # noqa: ASYNC101
                    fetch_cmd,
                    cwd=repo_dir,
                )

                # Checkout the branch
                checkout_cmd = ['git', 'checkout', branch_to_use]
                subprocess.check_output(  # noqa: ASYNC101
                    checkout_cmd,
                    cwd=repo_dir,
                )

                base_commit = (
                    subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo_dir)  # noqa: ASYNC101
                    .decode('utf-8')
                    .strip()
                )

            output = await self.process_issue(
                issue,
                base_commit,
                self.issue_handler,
                reset_logger,
            )

        finally:
            logger.info('Finished.')
            
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Total time taken: {duration} seconds")
            
            if output is not None:  # Check if output was created
                output.duration = duration
            
            return output
    
    
    def get_new_commit_hash(
        self,
        output_dir,
        resolver_output: ResolverOutput,
        pr_type: str
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

            # 3) make_commit
            # logger.info(f"[DEBUG] Resolver Output: {resolver_output} to {output_dir}")
            make_commit(patched_repo_dir, resolver_output.issue, resolver_output.issue_type)
            
            # 4) branch checkout and push
            branch_name, default_branch, base_url, headers = self.prepare_branch_and_push(
                patch_dir=patched_repo_dir,
                pr_type=pr_type,
            )
            
            resolver_output.success = False
            resolver_output.success_explanation = "Git patch applied successfully."
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
        base_branch_name = f"openhands-fix-issue-{self.issue_number}-try1"
        branch_name = base_branch_name
        attempt = 1

        # Ensure the branch doesn't already exist on the remote
        while httpx.get(f'{base_url}/branches/{branch_name}', headers=headers).status_code == 200:
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
        push_owner = self.owner
        push_repo = self.repo

        # Construct push command
        username_and_token = (
            f"{self.username}:{self.token}"
            if self.username else
            f"x-auth-token:{self.token}"
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
    
def main():
    import argparse
    
    def int_or_none(value: str) -> int | None:
        if value.lower() == 'none':
            return None
        else:
            return int(value)
        
    parser = argparse.ArgumentParser(description="Resolve issues from Github.")
    parser.add_argument(
        '--selected-repo',
        type=str,
        required=True,
        help='repository to resolve issues in form of `owner/repo`.',
    )
    parser.add_argument(
        '--token',
        type=str,
        default=None,
        help='token to access the repository.',
    )
    parser.add_argument(
        '--username',
        type=str,
        default=None,
        help='username to access the repository.',
    )
    parser.add_argument(
        '--base-container-image',
        type=str,
        default=None,
        help='base container image to use.',
    )
    parser.add_argument(
        '--runtime-container-image',
        type=str,
        default=None,
        help='Container image to use.',
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=50,
        help='Maximum number of iterations to run.',
    )
    parser.add_argument(
        '--issue-number',
        type=int,
        required=True,
        help='Issue number to resolve.',
    )
    parser.add_argument(
        '--comment-id',
        type=int_or_none,
        required=False,
        default=None,
        help='Resolve a specific comment',
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='output',
        help='Output directory to write the results.',
    )
    parser.add_argument(
        '--llm-model',
        type=str,
        default='Mock GPT',
        help='Mock model name to adapt with the existing code.',
    )
    parser.add_argument(
        '--llm-models',
        type=str,
        default=None,
        help='LLM models to use.',
    )
    parser.add_argument(
        '--llm-api-key',
        type=str,
        default=None,
        help='LLM API key to use.',
    )
    parser.add_argument(
        '--llm-base-url',
        type=str,
        default=None,
        help='LLM base URL to use.',
    )
    parser.add_argument(
        '--prompt-file',
        type=str,
        default=None,
        help='Path to the prompt template file in Jinja format.',
    )
    parser.add_argument(
        '--repo-instruction-file',
        type=str,
        default=None,
        help='Path to the repository instruction file in text format.',
    )
    parser.add_argument(
        '--issue-type',
        type=str,
        default='issue',
        choices=['issue', 'pr'],
        help='Type of issue to resolve, either open issue or pr comments.',
    )
    parser.add_argument(
        '--is-experimental',
        type=lambda x: x.lower() == 'true',
        help='Whether to run in experimental mode.',
    )
    parser.add_argument(
        '--base-domain',
        type=str,
        default=None,
        help='Base domain for the git server (defaults to "github.com" for GitHub and "gitlab.com" for GitLab)',
    )

    my_args = parser.parse_args()
    issue_resolver = PRArenaIssueResolver(my_args)
    
    asyncio.run(
        issue_resolver.resolve_issues_with_random_models()
    )

if __name__ == "__main__":
    main()
