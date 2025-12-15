#!/usr/bin/env python3
"""
Simple HTTP server for the prompt experiment viewer.

Automatically scans prompt_experiments directory and serves experiment data.

Usage:
    python server.py [port]

Default port is 8000.
"""

import http.server
import json
import socketserver
import sys
from pathlib import Path
from urllib.parse import urlparse


def scan_experiments():
    """Scan prompt_experiments directory and return experiment structure."""
    script_dir = Path(__file__).parent
    experiments_dir = script_dir.parent / "prompt_experiments"

    if not experiments_dir.exists():
        return {}

    data = {}

    # Scan for issue directories (format: Owner_Repo_IssueNumber)
    for issue_dir in experiments_dir.iterdir():
        if not issue_dir.is_dir():
            continue

        # Skip special directories
        if issue_dir.name in ['venv', '.venv', 'prompts', 'scripts', '__pycache__']:
            continue

        # Check if it matches the pattern (contains underscores and ends with a number)
        parts = issue_dir.name.split('_')
        if len(parts) < 3:
            continue

        # Check if last part is a number (issue number)
        try:
            int(parts[-1])
        except ValueError:
            continue

        issue_name = issue_dir.name
        data[issue_name] = {}

        # Scan for model directories
        for model_dir in issue_dir.iterdir():
            if not model_dir.is_dir():
                continue

            model_name = model_dir.name
            data[issue_name][model_name] = []

            # Scan for prompt directories
            for prompt_dir in model_dir.iterdir():
                if not prompt_dir.is_dir():
                    continue

                # Check if patch.diff exists (indicates a valid experiment result)
                patch_file = prompt_dir / "patch.diff"
                if patch_file.exists() or (prompt_dir / "summary.json").exists():
                    data[issue_name][model_name].append(prompt_dir.name)

            # Sort prompts, putting basic_prompt first if it exists
            prompts = data[issue_name][model_name]
            if 'basic_prompt' in prompts:
                prompts.remove('basic_prompt')
                prompts.sort()
                prompts.insert(0, 'basic_prompt')
            else:
                prompts.sort()

    return data


class ExperimentHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that serves experiment data dynamically."""

    def do_GET(self):
        """Handle GET requests, serving data.json dynamically."""
        parsed_path = urlparse(self.path)

        # Serve data.json dynamically
        if parsed_path.path == '/data.json':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            data = scan_experiments()
            self.wfile.write(json.dumps(data, indent=2).encode())
            return

        # Serve files from ../prompt_experiments/ directory
        if parsed_path.path.startswith('/prompt_experiments/'):
            # Remove the leading /prompt_experiments/ and serve from parent directory
            script_dir = Path(__file__).parent
            file_path = script_dir.parent / parsed_path.path.lstrip('/')

            if file_path.exists() and file_path.is_file():
                self.send_response(200)

                # Determine content type
                if file_path.suffix == '.diff':
                    content_type = 'text/plain'
                elif file_path.suffix == '.json':
                    content_type = 'application/json'
                elif file_path.suffix == '.jinja':
                    content_type = 'text/plain'
                else:
                    content_type = 'application/octet-stream'

                self.send_header('Content-type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, 'File not found')
                return

        # Serve other files normally
        super().do_GET()


def main():
    import os

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    # Change to the script's directory
    os.chdir(Path(__file__).parent)

    ExperimentHandler.extensions_map['.js'] = 'application/javascript'

    with socketserver.TCPServer(("", port), ExperimentHandler) as httpd:
        print(f"Serving at http://localhost:{port}")
        print(f"Open http://localhost:{port} in your browser")
        print("Press Ctrl+C to stop")
        print()

        # Show what we found
        data = scan_experiments()
        if data:
            print(f"Found {len(data)} issue(s):")
            for issue, models in data.items():
                print(f"  {issue}:")
                for model, prompts in models.items():
                    print(f"    {model}: {', '.join(prompts)}")
        else:
            print("No experiments found yet. Run experiments first!")

        print()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    main()
