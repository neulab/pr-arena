import os
import argparse
from argparse import Namespace
import asyncio
import pathlib
import random
import uuid

from openhands.resolver.resolve_issue import IssueResolver
from openhands.resolver.resolver_output import ResolverOutput
from openhands.core.config import LLMConfig
from openhands.resolver.send_pull_request import (
    initialize_repo, 
    apply_patch, 
    make_commit
)

from resolver.secrets import Secrets
from resolver.utils import load_firebase_config
from resolver.resolver_output import CustomResolverOutput

import firebase_admin
from firebase_admin import credentials, firestore

class PRArenaIssueResolver(IssueResolver):

    def __init__(self, args: Namespace):
        super().__init__(*args) # Most shared arguments are processed by parent class


        # Initialize values for custom resolver

        multiple_models = args.llm_models or os.environ["LLM_MODELS"]
        if multiple_models:
            model_names = [model.strip() for model in multiple_models.split(",")]
        else:
            raise ValueError("No LLM models provided in either the arguments or environment variables.")
        

        Secrets.TOKEN = self.token
        api_key = Secrets.get_api_key()
        self.llm_configs = []

        for model in model_names:
            self.llm_configs.append(
                LLMConfig(
                    model=model,
                    api_key=api_key,
                    base_url=args.base_url or os.environ.get("LLM_BASE_URL", None),
                )
            )


        raw_config = Secrets.get_firebase_config()
        self.firebase_config = load_firebase_config(raw_config)

    async def resolve_issues_with_random_models(self):
        selected_llms = random.sample(self.llm_configs, 2)
        self.llm_config = selected_llms[0] # Set current config
        resolver_output_1: ResolverOutput = await self.resolve_issue()
        resolver_output_1 = CustomResolverOutput(**resolver_output_1.model_dump(),
                                                 model=self.llm_config.model.split("/")[-1])


        self.llm_config = selected_llms # Set new config
        resolver_output_2: ResolverOutput = await self.resolve_issue()
        resolver_output_1 = CustomResolverOutput(**resolver_output_2.model_dump(),
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
        get_new_commit_hash(
            output_dir="output1",
            resolver_output=resolved_output_1,
            github_token=self.token,
            github_username=self.username,
            pr_type=pr_type
        
        )
        get_new_commit_hash(
            output_dir="output2",
            resolver_output=resolved_output_2,
            github_token=self.token,
            github_username=self.username,
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
        
        model1_id = model_reference.get(resolved_output_1.model, "Model ID Not Found")
        model2_id = model_reference.get(resolved_output_2.model, "Model ID Not Found")
        
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
        default=50,
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
    issue_resolver = PRArenaIssueResolver(my_args)
    
    asyncio.run(
        issue_resolver.resolve_issues_with_random_models(
            
        )
    )

if __name__ == "__main__":
    main()
