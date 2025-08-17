# flake8: noqa: E501

import asyncio
import argparse
import os
import json

from openhands.core.logger import openhands_logger as logger

import firebase_admin
from firebase_admin import credentials, firestore

from resolver.secrets import Secrets


async def get_selected_model_number(
    uuid: str, owner: str, repo: str, issue_number: str, firebase_config: dict
):
    """
    Listen for changes in a specific Firestore document (comparison ID).
    """
    cred = credentials.Certificate(firebase_config)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    # Reference to the document in issue_collection using the UUID
    doc_ref = db.collection("issue_collection").document(uuid)

    loop = asyncio.get_event_loop()
    event = asyncio.Event()

    def on_snapshot(doc_snapshot, changes, read_time):
        for doc in doc_snapshot:
            doc_data = doc.to_dict()

            # Check for the winner field
            winner = doc_data.get("winner")

            # Only proceed if winner is set to a value (not None)
            if winner is not None and doc_data.get("status") == "completed":
                logger.info(f"Winner determined: {winner}")

                # Translate winner value to model number
                selected = None
                if winner == "modelA":
                    selected = "1"
                elif winner == "modelB":
                    selected = "2"
                elif winner == "tie":
                    # In case of a tie, default to model 1
                    selected = "1"

                if selected is None:
                    logger.error(f"Unknown winner value: {winner}")
                    selected = "1"  # Default to model 1 if winner value is unknown

                # Check if the selected model has an empty patch by fetching the issue data
                # Get the issue document to check for empty patches
                issue_doc_ref = db.collection("issue_collection").document(uuid)
                issue_doc = issue_doc_ref.get()

                selected_model_has_empty_patch = False
                if issue_doc.exists:
                    issue_data = issue_doc.to_dict()
                    models = issue_data.get("models", {})

                    # Check if the selected model has empty agent_code (git patch)
                    if winner == "modelA":
                        selected_model_code = models.get("modelA", {}).get(
                            "agent_code", ""
                        )
                    elif winner == "modelB":
                        selected_model_code = models.get("modelB", {}).get(
                            "agent_code", ""
                        )
                    elif winner == "tie":
                        # For tie, check model A (which we default to)
                        selected_model_code = models.get("modelA", {}).get(
                            "agent_code", ""
                        )
                    else:
                        selected_model_code = ""

                    selected_model_has_empty_patch = (
                        not selected_model_code or selected_model_code.strip() == ""
                    )

                # Write to GitHub environment file
                github_env_path = os.getenv("GITHUB_ENV")
                if not github_env_path:
                    raise RuntimeError("GITHUB_ENV environment variable is not set.")

                with open(github_env_path, "a") as env_file:
                    env_file.write(f"SELECTED={selected}\n")
                    # Add flag for empty patch detection
                    if selected_model_has_empty_patch:
                        env_file.write("SELECTED_MODEL_EMPTY_PATCH=TRUE\n")
                        logger.info(
                            f"Selected model #{selected} has empty patch, flagged in environment."
                        )
                    else:
                        env_file.write("SELECTED_MODEL_EMPTY_PATCH=FALSE\n")

                # Also update the user_collection with the choice
                try:
                    # Get the user document using owner as document ID
                    user_doc_ref = db.collection("userdata_collection").document(owner)

                    # First, get the current document to find other UUIDs
                    user_doc = user_doc_ref.get()

                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        selections = user_data.get("selections", {})

                        # Create update data
                        update_data = {}

                        # Set all existing selections' isLatest to False
                        for existing_uuid in selections.keys():
                            update_data[f"selections.{existing_uuid}.isLatest"] = False

                        # Set the current selection data
                        update_data.update(
                            {
                                f"selections.{uuid}.choice": winner,
                                f"selections.{uuid}.selectedAt": firestore.SERVER_TIMESTAMP,
                                f"selections.{uuid}.isLatest": True,
                                "lastActive": firestore.SERVER_TIMESTAMP,
                            }
                        )

                        # Apply all updates in one operation
                        user_doc_ref.update(update_data)

                        other_count = len([k for k in selections.keys() if k != uuid])
                        logger.info(
                            f"Updated user selection for {owner}: set {uuid} as latest, marked {other_count} others as not latest"
                        )

                    else:
                        # Document doesn't exist, create it
                        user_doc_ref.set(
                            {
                                "githubId": owner,
                                "createdAt": firestore.SERVER_TIMESTAMP,
                                "lastActive": firestore.SERVER_TIMESTAMP,
                                "selections": {
                                    uuid: {
                                        "choice": winner,
                                        "selectedAt": firestore.SERVER_TIMESTAMP,
                                        "isLatest": True,
                                    }
                                },
                            }
                        )
                        logger.info(
                            f"Created new user document for {owner} with {uuid} as latest selection"
                        )

                except Exception as e:
                    logger.error(f"Error updating user_collection: {str(e)}")
                    logger.error(
                        f"Details - Owner: {owner}, UUID: {uuid}, Winner: {winner}"
                    )

                logger.info(
                    f"Model #{selected} is selected and saved to GitHub environment {github_env_path}."
                )
                loop.call_soon_threadsafe(event.set)
                break
        return

    # Attach the listener
    logger.info(f"Listening for changes on issue_collection document with UUID: {uuid}")
    doc_watch = doc_ref.on_snapshot(on_snapshot)

    # Keep the listener alive
    try:
        await event.wait()
    finally:
        doc_watch.unsubscribe()


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
        "--uuid",
        type=str,
        help="Reference UUID for the issue collection.",
    )

    my_args = parser.parse_args()

    owner, repo = my_args.repo.split("/")

    Secrets.TOKEN = my_args.token

    raw_config = Secrets.get_firebase_config()
    firebase_config = load_firebase_config(raw_config)

    asyncio.run(
        get_selected_model_number(
            uuid=my_args.uuid,
            owner=str(owner),
            repo=str(repo),
            issue_number=str(my_args.issue_number),
            firebase_config=firebase_config,
        )
    )


if __name__ == "__main__":
    main()
