# flake8: noqa: E501

import asyncio
import argparse
import os
import requests
import json


import openhands
from openhands.core.logger import openhands_logger as logger

import firebase_admin
from firebase_admin import credentials, firestore

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

async def get_selected_model_number (uuid: str, owner: str, repo: str, issue_number: str, firebase_config: dict):
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
                
                # Write to GitHub environment file
                github_env_path = os.getenv("GITHUB_ENV")
                if not github_env_path:
                    raise RuntimeError("GITHUB_ENV environment variable is not set.")

                with open(github_env_path, "a") as env_file:
                    env_file.write(f"SELECTED={selected}\n")
                
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
                        update_data.update({
                            f"selections.{uuid}.choice": winner,
                            f"selections.{uuid}.selectedAt": firestore.SERVER_TIMESTAMP,
                            f"selections.{uuid}.isLatest": True,
                            "lastActive": firestore.SERVER_TIMESTAMP
                        })
                        
                        # Apply all updates in one operation
                        user_doc_ref.update(update_data)
                        
                        other_count = len([k for k in selections.keys() if k != uuid])
                        logger.info(f"Updated user selection for {owner}: set {uuid} as latest, marked {other_count} others as not latest")
                        
                    else:
                        # Document doesn't exist, create it
                        user_doc_ref.set({
                            "githubId": owner,
                            "createdAt": firestore.SERVER_TIMESTAMP,
                            "lastActive": firestore.SERVER_TIMESTAMP,
                            "selections": {
                                uuid: {
                                    "choice": winner,
                                    "selectedAt": firestore.SERVER_TIMESTAMP,
                                    "isLatest": True
                                }
                            }
                        })
                        logger.info(f"Created new user document for {owner} with {uuid} as latest selection")

                except Exception as e:
                    logger.error(f"Error updating user_collection: {str(e)}")
                    logger.error(f"Details - Owner: {owner}, UUID: {uuid}, Winner: {winner}")
                
                logger.info(f"Model #{selected} is selected and saved to GitHub environment {github_env_path}.")
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
    
    asyncio.run(get_selected_model_number (uuid=my_args.uuid, owner=str(owner), repo=str(repo), issue_number=str(my_args.issue_number), firebase_config=firebase_config))
    
if __name__ == "__main__":
    main()