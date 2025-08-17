import uuid
from typing import Optional, Dict, Any

import firebase_admin
from firebase_admin import credentials, firestore

from resolver.secrets import Secrets
from resolver.utils import load_firebase_config


class ErrorTracker:
    """Utility class for tracking errors and empty patches in the error_collection."""

    def __init__(self, owner: str, repo: str, issue_number: int, token: str):
        self.owner = owner
        self.repo = repo
        self.issue_number = issue_number
        self.token = token
        self.issue_title: Optional[str] = None  # Will be populated when available
        self.issue_body: Optional[str] = None  # Will be populated when available

        # Initialize Firebase
        raw_config = Secrets.get_firebase_config()
        self.firebase_config = load_firebase_config(raw_config)

    def set_issue_info(
        self, issue_title: Optional[str] = None, issue_body: Optional[str] = None
    ) -> None:
        """Set issue title and body when available."""
        if issue_title:
            self.issue_title = issue_title
        if issue_body:
            self.issue_body = issue_body

    async def log_error(
        self,
        error_type: str,
        error_message: str,
        uuid_ref: Optional[str] = None,
        models: Optional[Dict[str, str]] = None,
        additional_context: Optional[Dict[str, Any]] = None,
        git_patch_empty: Optional[bool] = None,
        model_error_details: Optional[str] = None,
    ) -> str:
        """
        Log an error to the error_collection in Firebase.

        Args:
            error_type: Type of error (e.g., 'timeout', 'agent_failure', 'workflow_error', 'empty_patch_success')
            error_message: Detailed error message
            uuid_ref: UUID reference from issue_collection (if available)
            models: Dict of models involved (if available)
            additional_context: Additional context information
            git_patch_empty: Whether the git patch is empty or not
            model_error_details: Details about which model caused the error

        Returns:
            The UUID used for the error record
        """
        # Setup Firebase
        cred = credentials.Certificate(self.firebase_config)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        db = firestore.client()
        current_time = firestore.SERVER_TIMESTAMP

        # Generate UUID for error record (use existing UUID if provided, else create new)
        error_uuid = uuid_ref if uuid_ref else str(uuid.uuid4())

        repo_url = f"https://github.com/{self.owner}/{self.repo}"

        error_data = {
            "repo_url": repo_url,
            "issue_number": self.issue_number,
            "owner": self.owner,
            "repo": self.repo,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": current_time,
            "models": models or {},
            "additional_context": additional_context or {},
            "installationToken": self.token,
            "issue_title": self.issue_title,
            "issue_body": self.issue_body,
            "git_patch_empty": git_patch_empty,
            "model_error_details": model_error_details,
        }

        # If we have an existing UUID, try to link it to issue_collection
        if uuid_ref:
            error_data["linked_issue_uuid"] = uuid_ref

        # Store in error_collection
        error_ref = db.collection("error_collection").document(error_uuid)
        error_ref.set(error_data)

        return error_uuid

    def log_error_sync(
        self,
        error_type: str,
        error_message: str,
        uuid_ref: Optional[str] = None,
        models: Optional[Dict[str, str]] = None,
        additional_context: Optional[Dict[str, Any]] = None,
        git_patch_empty: Optional[bool] = None,
        model_error_details: Optional[str] = None,
    ) -> str:
        """
        Synchronous version of log_error for use in scripts and workflows.
        """
        import asyncio

        # For synchronous usage, we cannot handle running event loops
        # This function is meant for standalone script usage
        try:
            # Try to run in a new event loop
            return asyncio.run(
                self.log_error(
                    error_type,
                    error_message,
                    uuid_ref,
                    models,
                    additional_context,
                    git_patch_empty,
                    model_error_details,
                )
            )
        except RuntimeError as e:
            if "asyncio.run() cannot be called from a running event loop" in str(e):
                # If called from within an async context, generate UUID and warn
                import warnings

                error_uuid = uuid_ref if uuid_ref else str(uuid.uuid4())
                warnings.warn(
                    "log_error_sync called from async context. Error logging skipped. "
                    "Use 'await log_error()' instead.",
                    RuntimeWarning,
                )
                return error_uuid
            else:
                raise


def log_workflow_error(
    owner: str,
    repo: str,
    issue_number: int,
    token: str,
    error_type: str,
    error_message: str,
    uuid_ref: Optional[str] = None,
    models: Optional[str] = None,
    git_patch_empty: Optional[bool] = None,
    model_error_details: Optional[str] = None,
) -> str:
    """
    Standalone function to log errors from GitHub workflows.

    Args:
        owner: Repository owner
        repo: Repository name
        issue_number: Issue number
        token: GitHub token
        error_type: Type of error
        error_message: Error message
        uuid_ref: UUID from issue_collection if available
        models: Comma-separated string of models (from workflow)
        git_patch_empty: Whether the git patch is empty or not
        model_error_details: Details about which model caused the error
    """
    tracker = ErrorTracker(owner, repo, issue_number, token)

    # Parse models string if provided
    models_dict = {}
    if models:
        model_list = [m.strip() for m in models.split(",")]
        for i, model in enumerate(model_list, 1):
            models_dict[f"model{i}"] = model

    return tracker.log_error_sync(
        error_type=error_type,
        error_message=error_message,
        uuid_ref=uuid_ref,
        models=models_dict,
        git_patch_empty=git_patch_empty,
        model_error_details=model_error_details,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Log workflow errors to Firebase")
    parser.add_argument("--owner", required=True, help="Repository owner")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--issue-number", type=int, required=True, help="Issue number")
    parser.add_argument("--token", required=True, help="GitHub token")
    parser.add_argument("--error-type", required=True, help="Type of error")
    parser.add_argument("--error-message", required=True, help="Error message")
    parser.add_argument("--uuid", help="UUID from issue_collection")
    parser.add_argument("--models", help="Comma-separated list of models")
    parser.add_argument(
        "--git-patch-empty", action="store_true", help="Flag if git patch is empty"
    )
    parser.add_argument(
        "--model-error-details", help="Details about which model caused the error"
    )

    args = parser.parse_args()

    error_uuid = log_workflow_error(
        owner=args.owner,
        repo=args.repo,
        issue_number=args.issue_number,
        token=args.token,
        error_type=args.error_type,
        error_message=args.error_message,
        uuid_ref=args.uuid,
        models=args.models,
        git_patch_empty=args.git_patch_empty,
        model_error_details=args.model_error_details,
    )

    print(f"Error logged with UUID: {error_uuid}")
