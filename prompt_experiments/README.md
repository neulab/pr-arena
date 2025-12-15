# Prompt Experiments

Test different prompt templates to optimize PR-Arena agent behavior.

**What it does**: Runs issue resolution with custom prompt templates and saves results for comparison.

**Structure**:
- **Input**: Prompt templates in `{prompt_name}/*.jinja`
- **Output**: Results in `{repo}_{issue}/{model}/{prompt_name}/`
- **Scripts**: `scripts/run_experiment.py`

## Setup

**Prerequisites**:
- Docker Desktop (or Docker daemon) must be running
- Python 3.12 (3.13 has compatibility issues)

**Install dependencies**:

```bash
# From prompt_experiments directory
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Start

```bash
# Basic usage with defaults (uses gemini-2.5-pro, requires API key and GitHub token)
python run_experiment.py \
  --api-key "$LLM_API_KEY" \
  --github-token "$GITHUB_TOKEN"

# Full custom example
python run_experiment.py \
  --model-name "litellm_proxy/neulab/gemini-2.5-pro" \
  --api-key "your-api-key" \
  --github-token "your-github-token" \
  --repo "JiseungHong/SYCON-Bench" \
  --issue-number 33 \
  --prompt "basic_prompt"
```

## Directory Structure

```
prompt_experiments/
├── scripts/
│   └── run_experiment.py       # Main runner script
├── prompts/                    # Prompt template variants (INPUT)
│   ├── basic_prompt/           # Baseline templates
│   │   ├── user_instructions.jinja
│   │   └── conversation_instructions.jinja
│   └── enhanced_prompt/         # Enhanced templates
│       ├── user_instructions.jinja
│       └── conversation_instructions.jinja
├── requirements.txt            # Dependencies
├── README.md                   # This file
├── STRUCTURE.md                # Detailed documentation
│
└── {repo}_{issue}/             # Results (OUTPUT - auto-generated)
    └── {model}/                # e.g., gemini-2.5-pro
        └── {prompt}/           # e.g., basic_prompt
            ├── patch.diff      # Generated code patch
            ├── result.json     # Full resolution result
            ├── summary.json    # Quick summary
            └── experiment.log  # Execution log

Templates (INPUT):  prompt_experiments/prompts/{prompt_name}/*.jinja
Results (OUTPUT):   prompt_experiments/{repo}_{issue}/{model}/{prompt_name}/
```

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--model-name` | `litellm_proxy/neulab/gemini-2.5-pro` | LLM model to use |
| `--api-key` | `$LLM_API_KEY` or `XXX` | API key for LLM |
| `--github-token` | `$GITHUB_TOKEN` or `XXX` | GitHub access token |
| `--repo` | `JiseungHong/SYCON-Bench` | GitHub repository |
| `--issue-number` | `33` | Issue number to resolve |
| `--prompt` | `basic_prompt` | Prompt template directory |

## Creating New Prompts

1. Copy `prompts/basic_prompt/` to a new directory (e.g., `prompts/enhanced_prompt/`)
2. Edit the `.jinja` files in your new directory
3. Run with `--prompt "enhanced_prompt"`

**Required files in each prompt directory:**
- `user_instructions.jinja` - Initial task description
- `conversation_instructions.jinja` - Ongoing conversation rules

## Special Prompts

### `shorter_prompt`
Automatically uses the same LLM to shorten the issue body before passing it to the agent. This tests whether concise problem descriptions improve resolution quality.

**How it works**: When `--prompt "shorter_prompt"` is used, the script calls the LLM to summarize the issue while preserving technical details, then uses the shortened version in the prompt.

## Output Files

Each experiment creates:
- **patch.diff** - Git diff of generated changes
- **result.json** - Full OpenHands result with history
- **summary.json** - Quick metrics (cost, duration, success)
- **experiment.log** - Execution log

## Example Workflow

```bash
# Test baseline prompt
python scripts/run_experiment.py --prompt "basic_prompt"

# Test shorter_prompt (uses LLM to shorten issue body)
python scripts/run_experiment.py --prompt "shorter_prompt"

# Create enhanced prompt
cp -r prompts/basic_prompt/ prompts/enhanced_prompt/
# Edit prompts/enhanced_prompt/*.jinja files

# Test enhanced prompt
python scripts/run_experiment.py --prompt "enhanced_prompt"
