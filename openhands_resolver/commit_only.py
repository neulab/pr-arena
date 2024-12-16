import argparse
import os
import subprocess
from openhands_resolver.resolver_output import ResolverOutput
from openhands_resolver.io_utils import load_single_resolver_output
from openhands_resolver.github_issue import GithubIssue
from openhands_resolver.patching import parse_patch, apply_diff
import firebase_admin
from firebase_admin import credentials, firestore


def apply_patch(repo_dir: str, patch: str) -> None:
    diffs = parse_patch(patch)
    for diff in diffs:
        if not diff.header.new_path:
            print("Warning: Could not determine file to patch")
            continue

        old_path = (
            os.path.join(repo_dir, diff.header.old_path.removeprefix("b/"))
            if diff.header.old_path and diff.header.old_path != "/dev/null"
            else None
        )
        new_path = os.path.join(repo_dir, diff.header.new_path.removeprefix("b/"))

        if diff.header.new_path == "/dev/null":
            if old_path and os.path.exists(old_path):
                os.remove(old_path)
                print(f"Deleted file: {old_path}")
            continue

        if old_path and os.path.exists(old_path):
            with open(old_path, "r") as f:
                original_content = f.readlines()
        else:
            original_content = []

        new_content = apply_diff(diff, original_content)

        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        with open(new_path, "w") as f:
            f.writelines(new_content)

    print("Patch applied successfully")


def initialize_repo(output_dir: str, base_commit: str) -> str:
    repo_dir = os.path.join(output_dir, "repo")
    if not os.path.exists(repo_dir):
        raise ValueError(f"Source directory {repo_dir} does not exist.")

    result = subprocess.run(
        ["git", "-C", repo_dir, "checkout", base_commit],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error checking out base commit: {result.stderr}")
        raise RuntimeError("Failed to check out base commit")

    return repo_dir


def create_branch(repo_dir: str, branch_name: str):
    subprocess.run(
        ["git", "-C", repo_dir, "checkout", "-b", branch_name],
        check=True
    )
    print(f"Created and switched to branch: {branch_name}")


def make_commit(repo_dir: str, issue: GithubIssue, issue_type: str) -> str:
    subprocess.run(
        ["git", "-C", repo_dir, "add", "."],
        check=True
    )

    commit_message = f"Fix {issue_type} #{issue.number}: {issue.title}"
    result = subprocess.run(
        ["git", "-C", repo_dir, "commit", "-m", commit_message],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to commit changes: {result.stderr}")

    commit_hash = subprocess.check_output(
        ["git", "-C", repo_dir, "rev-parse", "HEAD"]
    ).decode("utf-8").strip()
    return commit_hash


def push_branch(repo_dir: str, branch_name: str, github_token: str, github_username: str):
    result = subprocess.run(
        ["git", "-C", repo_dir, "push", "origin", branch_name],
        capture_output=True,
        text=True,
        env={"GIT_ASKPASS": "/bin/echo", "GIT_USERNAME": github_username, "GIT_PASSWORD": github_token}
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to push branch: {result.stderr}")
    print(f"Pushed branch {branch_name} to remote")


def update_firebase_commit_id(firebase_config: str, owner: str, repo: str, issue_number: int, model_number: int, commit_hash: str):
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    doc_ref = db.collection("issues").document(f"{owner}-{repo}-{issue_number}")

    field_name = f"json{model_number}.commit_id"
    doc_ref.update({field_name: commit_hash})
    print(f"Updated {field_name} in Firebase with commit hash {commit_hash}")


def main():
    parser = argparse.ArgumentParser(description="Apply patch, commit, and update Firebase.")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--model-number", type=int, required=True)
    parser.add_argument("--repo", type=str, required=True, help="owner/repo")
    parser.add_argument("--github-token", type=str, required=True)
    parser.add_argument("--github-username", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="output")
    parser.add_argument("--firebase-config", type=str, required=True, help="Path to Firebase config JSON")
    args = parser.parse_args()

    owner, repo = args.repo.split("/")

    # Load resolver output
    output_path = os.path.join(args.output_dir, f"output{args.model_number}.jsonl")
    resolver_output = load_single_resolver_output(output_path, args.issue_number)

    # Initialize repo
    repo_dir = initialize_repo(args.output_dir, resolver_output.base_commit)

    # Create branch
    branch_name = f"model{args.model_number}-branch"
    create_branch(repo_dir, branch_name)

    # Apply patch and commit
    apply_patch(repo_dir, resolver_output.git_patch)
    commit_hash = make_commit(repo_dir, resolver_output.issue, resolver_output.issue_type)

    # Push branch
    push_branch(repo_dir, branch_name, args.github_token, args.github_username)

    # Update Firebase
    update_firebase_commit_id(
        args.firebase_config, owner, repo, resolver_output.issue.number, args.model_number, commit_hash
    )

    print(f"Commit hash for model {args.model_number}: {commit_hash}")


if __name__ == "__main__":
    main()
