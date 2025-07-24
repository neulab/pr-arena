import json
import re
import os
from collections import defaultdict
from typing import Dict, List, Tuple
import requests


def load_firebase_config(config_json: str) -> dict:
    """Load Firebase configuration from JSON string."""
    try:
        return json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid Firebase configuration JSON: {e}")

def get_file_extension_language_map() -> Dict[str, str]:
    """Map file extensions to programming languages."""
    return {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.jsx': 'JavaScript',
        '.tsx': 'TypeScript',
        '.java': 'Java',
        '.cpp': 'C++',
        '.cc': 'C++',
        '.cxx': 'C++',
        '.c': 'C',
        '.h': 'C/C++',
        '.hpp': 'C++',
        '.cs': 'C#',
        '.php': 'PHP',
        '.rb': 'Ruby',
        '.go': 'Go',
        '.rs': 'Rust',
        '.swift': 'Swift',
        '.kt': 'Kotlin',
        '.scala': 'Scala',
        '.r': 'R',
        '.R': 'R',
        '.m': 'Objective-C',
        '.mm': 'Objective-C++',
        '.pl': 'Perl',
        '.sh': 'Shell',
        '.bash': 'Shell',
        '.zsh': 'Shell',
        '.fish': 'Shell',
        '.ps1': 'PowerShell',
        '.sql': 'SQL',
        '.html': 'HTML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'Sass',
        '.less': 'Less',
        '.vue': 'Vue',
        '.dart': 'Dart',
        '.lua': 'Lua',
        '.vim': 'Vim Script',
        '.ex': 'Elixir',
        '.exs': 'Elixir',
        '.erl': 'Erlang',
        '.hrl': 'Erlang',
        '.clj': 'Clojure',
        '.cljs': 'ClojureScript',
        '.hs': 'Haskell',
        '.ml': 'OCaml',
        '.fs': 'F#',
        '.jl': 'Julia',
        '.nim': 'Nim',
        '.cr': 'Crystal',
        '.zig': 'Zig',
        '.v': 'V',
        '.d': 'D',
        '.pas': 'Pascal',
        '.pp': 'Pascal',
        '.f90': 'Fortran',
        '.f95': 'Fortran',
        '.f03': 'Fortran',
        '.f08': 'Fortran',
        '.for': 'Fortran',
        '.ftn': 'Fortran',
        '.asm': 'Assembly',
        '.s': 'Assembly',
        '.S': 'Assembly',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.json': 'JSON',
        '.xml': 'XML',
        '.toml': 'TOML',
        '.ini': 'INI',
        '.cfg': 'Config',
        '.conf': 'Config',
        '.md': 'Markdown',
        '.rst': 'reStructuredText',
        '.tex': 'LaTeX',
        '.dockerfile': 'Dockerfile',
        '.makefile': 'Makefile',
        '.cmake': 'CMake',
        '.gradle': 'Gradle',
        '.maven': 'Maven',
    }


def detect_languages_from_git_patch(git_patch: str) -> Dict[str, int]:
    """
    Detect programming languages from git patch by analyzing file extensions.
    
    Args:
        git_patch: Git patch string
        
    Returns:
        Dictionary mapping language names to line counts
    """
    if not git_patch:
        return {}
    
    extension_map = get_file_extension_language_map()
    language_lines: dict[str, int] = defaultdict(int)
    
    # Split patch into lines
    lines = git_patch.split('\n')
    current_file = None
    
    for line in lines:
        # Check for file headers (diff --git a/file b/file or +++ b/file)
        if line.startswith('diff --git'):
            # Extract filename from diff --git a/file b/file
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:]  # Remove 'b/' prefix
        elif line.startswith('+++') and line != '+++ /dev/null':
            # Extract filename from +++ b/file
            current_file = line[6:]  # Remove '+++ b/' prefix
        elif line.startswith('---') and line != '--- /dev/null':
            # Extract filename from --- a/file
            if current_file is None:
                current_file = line[6:]  # Remove '--- a/' prefix
        
        # Count added lines (lines starting with +, excluding +++ headers)
        if current_file and line.startswith('+') and not line.startswith('+++'):
            # Get file extension
            _, ext = os.path.splitext(current_file.lower())
            if ext in extension_map:
                language_lines[extension_map[ext]] += 1
            elif current_file.lower().endswith('dockerfile'):
                language_lines['Dockerfile'] += 1
            elif current_file.lower() in [
                'makefile',
                'makefile.am',
                'makefile.in',
            ]:
                language_lines['Makefile'] += 1
            elif (
                current_file.lower().endswith('.cmake')
                or current_file.lower() == 'cmakelists.txt'
            ):
                language_lines['CMake'] += 1
    
    return dict(language_lines)


def get_repo_languages_from_github(owner: str, repo: str, token: str) -> Dict[str, int]:
    """
    Get repository language statistics from GitHub API.
    
    Args:
        owner: Repository owner
        repo: Repository name
        token: GitHub token
        
    Returns:
        Dictionary mapping language names to byte counts
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/languages"
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get repo languages: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Error getting repo languages: {e}")
        return {}


def calculate_language_percentages(language_counts: Dict[str, int]) -> Dict[str, float]:
    """
    Calculate percentage distribution of languages.
    
    Args:
        language_counts: Dictionary mapping language names to counts
        
    Returns:
        Dictionary mapping language names to percentages
    """
    if not language_counts:
        return {}
    
    total = sum(language_counts.values())
    if total == 0:
        return {}
    
    return {lang: (count / total) * 100 for lang, count in language_counts.items()}


def get_comprehensive_language_info(
    owner: str,
    repo: str,
    token: str,
    git_patch_1: str | None = None,
    git_patch_2: str | None = None,
) -> Dict:
    """
    Get comprehensive language information combining repository stats and patch analysis.
    
    Args:
        owner: Repository owner
        repo: Repository name  
        token: GitHub token
        git_patch_1: First git patch (optional)
        git_patch_2: Second git patch (optional)
        
    Returns:
        Dictionary containing language information
    """
    # Get repository language distribution
    repo_languages = get_repo_languages_from_github(owner, repo, token)
    repo_percentages = calculate_language_percentages(repo_languages)
    
    # Analyze patches if provided
    patch_languages: dict[str, int] = {}
    if git_patch_1:
        patch1_langs = detect_languages_from_git_patch(git_patch_1)
        for lang, count in patch1_langs.items():
            patch_languages[lang] = patch_languages.get(lang, 0) + count
    
    if git_patch_2:
        patch2_langs = detect_languages_from_git_patch(git_patch_2)
        for lang, count in patch2_langs.items():
            patch_languages[lang] = patch_languages.get(lang, 0) + count
    
    patch_percentages = calculate_language_percentages(patch_languages)
    
    # Get primary language (most used in repo)
    primary_language = (
        max(repo_languages.keys(), key=lambda x: repo_languages[x]) 
        if repo_languages else "Unknown"
    )
    
    return {
        "primary_language": primary_language,
        "repo_languages": repo_languages,
        "repo_language_percentages": repo_percentages,
        "patch_languages": patch_languages,
        "patch_language_percentages": patch_percentages,
        "total_repo_bytes": sum(repo_languages.values()) if repo_languages else 0,
        "total_patch_lines": sum(patch_languages.values()) if patch_languages else 0
    }