# Model Testing for PR-Arena

This folder contains tools for testing individual LLM models to evaluate their suitability for PR-Arena before adding them to the official model list.

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Test

Test a model against a GitHub issue to evaluate its performance:

```bash
python test_new_model.py \
  --model-name litellm_proxy/azure/gpt-5 \
  --api-key sk-YOUR_API_KEY_HERE \
  --github-token github_pat_YOUR_TOKEN_HERE \
  --repo "YOUR_REPO" \
  --issue-number ISSUE_NUMBER
```

### Required Arguments

- `--model-name`: Name of the LLM model to test (e.g., `claude-3-5-sonnet-20241022`)
- `--api-key`: API key for the LLM model (or set `LLM_API_KEY` environment variable)
- `--github-token`: GitHub token with repository access (or set `GITHUB_TOKEN` environment variable)

### Optional Arguments

- `--repo`: GitHub repository in format `owner/repo` (default: `JiseungHong/SYCON-Bench`)
- `--issue-number`: Issue number to test (default: `33`)
- `--github-username`: GitHub username (inferred from token if not provided)

## Output

The test will generate:
- **Logs**: Saved to `model_test_logs/`
- **Traces**: Detailed execution artifacts in `model_test_logs/{model_name}_{timestamp}_traces/`
- **Results**: Git patches, conversation history, and performance metrics

Check the trace directory for:
- `trace_summary.json` - Overview of test results
- `result_output.json` - Model output including git patch
- `git_patch.diff` - Generated code changes
- `conversation_history.jsonl` - Full agent conversation
