# Prompt Experiment Viewer

A simple web-based viewer for comparing prompt experiment results side-by-side.

## Features

- Browse experiments by issue (Owner/Repo/Issue)
- View results for different models
- Compare two prompts side-by-side with diff viewer
- Clean navigation with vertical sidebar
- **Automatic scanning** - no manual data generation needed!

## Quick Start

1. **Start the server:**
   ```bash
   python server.py
   ```

2. **Open in browser:**
   Visit `http://localhost:8000`

That's it! The server automatically scans `../prompt_experiments/` and serves the data.

## Usage

### Navigation

1. **Left sidebar (Issues):** Click on an issue to view its experiments
   - Shows Owner, Repo, and Issue number
   - Parses from folder names like `JiseungHong_SYCON-Bench_33`

2. **Second sidebar (Models):** Click on a model to view its prompts
   - Shows available models (e.g., `gemini-2.5-pro`)

3. **Top controls:** Select which prompts to compare
   - Left dropdown: Choose prompt for left panel (defaults to `basic_prompt`)
   - Right dropdown: Choose prompt for right panel (defaults to second available prompt)

### Viewing Diffs

- Each side displays the `patch.diff` file from the selected prompt
- If no diff exists, shows "No diff to display"
- Diffs are shown in monospace font with syntax highlighting
- **Auto-refresh:** Just refresh the browser page to see new experiments

## File Structure

```
prompt_experiment_display/
├── index.html          # Main HTML page
├── style.css           # Styling
├── app.js              # Application logic
├── server.py           # HTTP server with automatic scanning
└── README.md           # This file
```

## How It Works

1. `server.py` automatically scans `../prompt_experiments/` directory on each request
2. Dynamically serves experiment data at `/data.json` endpoint
3. Web app loads data and fetches diff files on demand
4. Displays diffs side-by-side for comparison

No manual data generation step needed - just refresh your browser to see new experiments!

## Advanced

Run on a different port:
```bash
python server.py 3000
```
