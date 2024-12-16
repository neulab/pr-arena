import argparse
import os
import shutil
import json
import subprocess
from openhands_resolver.resolver_output import ResolverOutput
from openhands_resolver.io_utils import load_single_resolver_output
from openhands_resolver.github_issue import GithubIssue
from openhands_resolver.patching import parse_patch, apply_diff

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

        # Check if the file is being deleted
        if diff.header.new_path == "/dev/null":
            if old_path and os.path.exists(old_path):
                os.remove(old_path)
                print(f"Deleted file: {old_path}")
            continue

        if old_path and os.path.exists(old_path):
            # Detect line endings
            with open(old_path, "rb") as f:
                original_content = f.read()

            if b"\r\n" in original_content:
                newline = "\r\n"
            elif b"\n" in original_content:
                newline = "\n"
            else:
                newline = None

            with open(old_path, "r", newline=newline) as f:
                split_content = [x.strip(newline) for x in f.readlines()]
        else:
            newline = "\n"
            split_content = []

        if diff.changes is None:
            print(f"Warning: No changes to apply for {old_path}")
            continue

        new_content = apply_diff(diff, split_content)

        # Ensure the directory exists before writing the file
        os.makedirs(os.path.dirname(new_path), exist_ok=True)

        # Write the new content using the detected line endings
        with open(new_path, "w", newline=newline) as f:
            for line in new_content:
                print(line, file=f)

    print("Patch applied successfully")

def initialize_repo(output_dir: str, issue_number: int, issue_type: str, base_commit: str | None = None) -> str:
    src_dir = os.path.join(output_dir, "repo")
    dest_dir = os.path.join(output_dir, "patches", f"{issue_type}_{issue_number}")

    if not os.path.exists(src_dir):
        raise ValueError(f"Source directory {src_dir} does not exist.")

    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)

    shutil.copytree(src_dir, dest_dir)
    print(f"Copied repository to {dest_dir}")

    if base_commit:
        result = subprocess.run(
            ["git", "-C", dest_dir, "checkout", base_commit],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error checking out commit: {result.stderr}")
            raise RuntimeError("Failed to check out commit")

    return dest_dir

def configure_git(repo_dir: str):
    result = subprocess.run(
        ["git", "-C", repo_dir, "config", "user.name"],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        subprocess.run(
            ["git", "-C", repo_dir, "config", "user.name", "openhands"],
            check=True
        )
        subprocess.run(
            ["git", "-C", repo_dir, "config", "user.email", "openhands@all-hands.dev"],
            check=True
        )
        print("Git user configured as openhands")

def make_commit(repo_dir: str, issue: GithubIssue, issue_type: str) -> None:
    configure_git(repo_dir)
    result = subprocess.run(
        ["git", "-C", repo_dir, "add", "."],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error adding files: {result.stderr}")
        raise RuntimeError("Failed to add files to git")

    commit_message = f"Fix {issue_type} #{issue.number}: {issue.title}"
    result = subprocess.run(
        ["git", "-C", repo_dir, "commit", "-m", commit_message],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to commit changes: {result.stderr}")

    # Return commit hash
    commit_hash = subprocess.check_output(
        ["git", "-C", repo_dir, "rev-parse", "HEAD"]
    ).decode("utf-8").strip()
    return commit_hash

def update_firebase_commit_id(firebase_config: dict, owner: str, repo: str, issue_number: int, model_number: int, commit_hash: str):
    # Initialize Firebase if not already initialized
    import firebase_admin
    from firebase_admin import credentials, firestore

    # Only initialize app if not already initialized
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    doc_ref = db.collection("issues").document(f"{owner}-{repo}-{issue_number}")

    # Determine which field to update based on model_number
    field_name = f"json{model_number}.commit_id"
    
    # Perform the update only for the commit_id field
    doc_ref.update({field_name: commit_hash})
    print(f"Updated {field_name} in Firebase with commit hash {commit_hash}")
    

def main():
    parser = argparse.ArgumentParser(description="Apply patch and commit only (no PR).")
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--model-number", type=int, required=True)
    parser.add_argument("--repo", type=str, required=True, help="owner/repo")
    parser.add_argument("--github-token", type=str, required=True)
    parser.add_argument("--github-username", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="output")
    parser.add_argument("--firebase-config", type=str, default=None, help="Firebase config JSON")
    args = parser.parse_args()

    owner, repo = args.repo.split("/")

    # Load the resolver output for this model and issue
    output_path = os.path.join(args.output_dir, f"output{args.model_number}.jsonl")
    resolver_output = load_single_resolver_output(output_path, args.issue_number)
    issue_type = resolver_output.issue_type

    # Initialize repo at base commit or head_branch (for PR)
    if issue_type == "issue":
        patched_repo_dir = initialize_repo(
            args.output_dir,
            resolver_output.issue.number,
            issue_type,
            resolver_output.base_commit
        )
    elif issue_type == "pr":
        patched_repo_dir = initialize_repo(
            args.output_dir,
            resolver_output.issue.number,
            issue_type,
            resolver_output.issue.head_branch
        )
    else:
        raise ValueError(f"Invalid issue type: {issue_type}")

    apply_patch(patched_repo_dir, resolver_output.git_patch)
    commit_hash = make_commit(patched_repo_dir, resolver_output.issue, issue_type)

    print(f"New commit created: {commit_hash}")

    if args.firebase_config:
        update_firebase_with_commit(
            args.firebase_config,
            owner,
            repo,
            resolver_output.issue.number,
            args.model_number,
            commit_hash
        )

if __name__ == "__main__":
    main()
