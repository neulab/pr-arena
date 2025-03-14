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
import time

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

async def get_selected_model_number (document_id: str, firebase_config: dict):
    """
    Listen for changes in a specific Firestore document (comparison ID).
    """
    cred = credentials.Certificate(firebase_config)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    # logger.info("3.1. Credentials complete")
    db = firestore.client()
    
    doc_ref = db.collection("issues").document(document_id)
    
    loop = asyncio.get_event_loop()
    event = asyncio.Event()
    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            doc_data = doc.to_dict()
            logger.info(f"Change detected in issues - {document_id}: {doc_data}")

            if doc_data.get("status") == "completed":
                selected = doc_data.get("selected")
                if selected is None:
                    print("Error: 'selected' field is missing in the document!")
                logger.info(f"Selected model received: {selected}")
                
                github_env_path = os.getenv("GITHUB_ENV")
                if not github_env_path:
                    raise RuntimeError("GITHUB_ENV environment variable is not set.")

                # Write the decision to the environment file
                with open(github_env_path, "a") as env_file:
                    env_file.write(f"SELECTED={selected}\n")
                logger.info(f"Model #{selected} is selected and saved to GitHub environment {github_env_path}.")
                # logger.info("Setting event to stop asyncio loop.")
                loop.call_soon_threadsafe(event.set)
                # logger.info("Event set.")
                break
        
        # logger.info("Returning on_snapshot.")
        return

    # Attach the listener
    logger.info(f"Listening for changes on document ID: {document_id}")
    doc_watch = doc_ref.on_snapshot(on_snapshot)

    # Keep the listener alive
    try:
        await event.wait()
        # logger.info("Event completed.")
    finally:
        doc_watch.unsubscribe()
        # logger.info("Stopped listening for changes.")

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
        "--token-config",
        type=str,
        help="Firebase configuration in JSON format."
    )

    my_args = parser.parse_args()
    
    owner, repo = my_args.repo.split("/")
    
    raw_config = my_args.token_config if my_args.token_config else os.getenv("FIREBASE_CONFIG")
    firebase_config = load_firebase_config(raw_config)
    # logger.info(f"Firebase Config Loaded... {firebase_config}")
    
    asyncio.run(get_selected_model_number (document_id=f"{owner}-{repo}-{int(my_args.issue_number)}", firebase_config=firebase_config))
    
if __name__ == "__main__":
    main()