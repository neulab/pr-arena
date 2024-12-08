# flake8: noqa: E501

import asyncio
import dataclasses
import shutil
from typing import Any, Awaitable, TextIO
import argparse
import multiprocessing as mp
import os
import pathlib
import subprocess
import json
import random

from termcolor import colored
from tqdm import tqdm


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

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

def issue_handler_factory(issue_type: str, owner: str, repo: str, token: str) -> IssueHandlerInterface:
    if issue_type == "issue":
        return IssueHandler(owner, repo, token)
    elif issue_type == "pr":
        return PRHandler(owner, repo, token)
    else:
        raise ValueError(f"Invalid issue type: {issue_type}")

def build_resolver_output (
    owner: str,
    repo: str,
    token: str,
    issue_type: str,
    issue_number: int,
    model: str,
) -> ResolverOutput:
    """_summary_

    Args:
        owner (str): _description_
        repo (str): _description_
        token (str): _description_\
        output_dir (str): _description_
        issue_type (str): _description_
        repo_instruction (str | None): _description_
        issue_number (int): _description_

    Returns:
        ResolverOutput: _description_
    """
    
    logger.info(f"1. Start building resolver output for {owner}/{repo}.")
    
    issue_handler = issue_handler_factory(issue_type, owner, repo, token)
    issues: list[GithubIssue] = issue_handler.get_converted_issues()
    issue = None
    for issue in issues:
        if issue.number == issue_number:
            break

    if issue is None:
        ValueError(f"Issue does not match. Issue Number: {issue_number}.")
    
    logger.info(f"Limiting resolving to issues {issue_number}.")
        
    issue = issues[0]
    
    output = ResolverOutput(
        issue=issue,
        issue_type=issue_handler.issue_type,
        instruction="instruction",
        base_commit="base_commit",
        git_patch=f"Git Patch for Model {model}",
        history=[],
        metrics=None,
        success=1,
        comment_success=None,
        success_explanation="success_explanation",
        error=None,
        model=model,
    )
    return output


def send_to_firebase (
    resolved_output1: ResolverOutput,
    resolved_output2: ResolverOutput,
    output_dir: str,
    owner: str,
    repo: str,
    issue_number: int,
    firebase_config: dict,
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
    logger.info(f"2. Write down the resolver to {output_dir}/... .")
    
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    file_name = f"{owner}_{repo}_{issue_number}.jsonl"
    output_file = pathlib.Path(output_dir) / file_name
    
    output_data1 = json.loads(resolved_output1.model_dump_json())
    output_data1.update({
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number
    })
    
    output_data2 = json.loads(resolved_output2.model_dump_json())
    output_data2.update({
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number
    })
    
    output_data = {"json1": output_data1, "json2": output_data2, "status": "pending"}
    
    logger.info(f"2.1. Resolvers: {output_data}")
    
    with open(output_file, "a") as output_fp:
        output_fp.write(json.dumps(output_data) + "\n")
    
    logger.info("3. Sending jsonl file to firebase.")
    
    cred = credentials.Certificate(firebase_config)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    logger.info("3.1. Credentials complete")
    # Initialize Firestore client
    db = firestore.client()
    
    logger.info("3.2. Database complete")
    
    collection_name = "issues"
    document_id = f"{owner}-{repo}-{issue_number}"

    doc_ref = db.collection(collection_name).document(document_id)
    doc_ref.set(output_data)

    print(f"Data successfully written to Firestore collection '{collection_name}' with ID: {document_id}")

def load_firebase_config(config_json: str) -> dict:
    """Load Firebase configuration from JSON string."""
    try:
        return json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid Firebase configuration JSON: {e}")

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
        "--agent-class",
        type=str,
        default="CodeActAgent",
        help="The agent class to use.",
    )
    parser.add_argument(
        "--issue-number",
        type=str,
        default=None,
        help="issue number to resolve.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory to write the results.",
    )
    parser.add_argument(
        "--llm-models",
        type=str,
        default=None,
        help="LLM models to use.",
    )
    parser.add_argument(
        "--issue-type",
        type=str,
        default="issue",
        choices=["issue", "pr"],
        help="Type of issue to resolve, either open issue or pr comments.",
    )
    parser.add_argument(
    "--firebase-config",
    type=str,
    help="Firebase configuration in JSON format."
    )

    my_args = parser.parse_args()
    
    owner, repo = my_args.repo.split("/")
    token = (
        my_args.token if my_args.token else os.getenv("GITHUB_TOKEN")
    )
    
    if not token:
        raise ValueError("Github token is required.")
    
    models = my_args.llm_models or os.environ["LLM_MODELS"]
    if models:
        model_names = [model.strip() for model in models.split(",")]
    else:
        raise ValueError("No LLM models provided in either the arguments or environment variables.")
    
    selected_llms = random.sample(model_names, 2)
    
    issue_type = my_args.issue_type
    
    resolver_output1 = build_resolver_output (
        owner=owner,
        repo=repo,
        token=token,
        issue_type=issue_type,
        issue_number=int(my_args.issue_number),
        model=selected_llms[0]
    )
    
    resolver_output2 = build_resolver_output (
        owner=owner,
        repo=repo,
        token=token,
        issue_type=issue_type,
        issue_number=int(my_args.issue_number),
        model=selected_llms[1]
    )
    
    raw_config = my_args.firebase_config if my_args.firebase_config else os.getenv("FIREBASE_CONFIG")
    firebase_config = load_firebase_config(raw_config)
    logger.info(f"Firebase Config Loaded... {firebase_config}")
    
    send_to_firebase (
        resolved_output1=resolver_output1,
        resolved_output2=resolver_output2,
        output_dir=my_args.output_dir,
        owner=owner,
        repo=repo,
        issue_number=int(my_args.issue_number),
        firebase_config=firebase_config
    )

if __name__ == "__main__":
    main()