import os
import argparse
import asyncio

import openhands
from openhands.resolver.resolve_issue import IssueResolver
from resolver.secrets import Secrets
from resolver.utils import load_firebase_config

class PRArenaIssueResolver(IssueResolver):

    def __init__(self, *args, firebase_config: dict):
        super().__init__(*args)
        self.firebase_config = firebase_config

    def resolve_issues_with_random_models(self):
        pass

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


    issue_resolver = PRArenaIssueResolver(
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
        firebase_config=firebase_config)

    asyncio.run(
        issue_resolver.resolve_issues_with_random_models(
            
        )
    )

if __name__ == "__main__":
    main()
