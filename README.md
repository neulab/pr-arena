# PR Arena ⚔️

PR Arena is a coding assistant designed to evaluate and improve [OpenHands GitHub Backlog Resolver](https://github.com/All-Hands-AI/OpenHands/tree/main/openhands/resolver) through paired pull request (PR) generations. It enables developers to compare contributions from different LLMs such as GPT-4o, Llama, and more.

This project is inspired by [Copilot Arena](https://github.com/lmarena/copilot-arena), an open source AI coding assistant that provides paired autocomplete completions from different LLMs.

Follow the instruction below to setup the Arena setting for the OpenHands resolver.

## Using the GitHub Actions Workflow

This repository includes a GitHub Actions workflow that can automatically attempt to generate a pair of pull requests for individual issues labeled with 'fix-me'. Follow the steps to use this workflow in your own repository:

1. Prepare a github personal access token. You can:
    1. [Contact us](mailto:contact@all-hands.dev) and we will set up a token for the [openhands-agent](https://github.com/openhands-agent) account (if you want to make it clear which commits came from the agent.
    2. Choose your own github user that will make the commits to the repo, [and create a personal access token](https://github.com/settings/tokens?type=beta) with read/write scope for "contents", "issues", "pull requests", and "workflows" on the desired repos.

2. Create an API key for the LLMs you will be setting up for the Arena setting. We usually use a single API key which can access the LLM Router.

3. Copy the `.github/workflows/openhands-resolver.yml` file to your repository's `.github/workflows/` directory.

4. Enable read/write workflows for the repository by going to `Settings -> Actions -> General -> Workflow permissions` and selecting "Read and write permissions" and click "Allow Github Actions to create and approve pull requests".

5. Set up the following [GitHub secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) in your repository, or across your entire org if you want to only set ths once and use the resolver in multiple repositories:
   - `PAT_USERNAME`: The github username that you used to create the personal access token.
   - `PAT_TOKEN`: The personal access token for github.
   - `LLM_MODELS`: The comma seperated LLM models to use (e.g., "litellm_proxy/claude-3-5-sonnet-20241022,litellm_proxy/claude-3-5-sonnet-20240620,litellm_proxy/gpt-4o-2024-08-06,litellm_proxy/gpt-4o-2024-05-13,litellm_proxy/gemini-1.5-pro-002,litellm_proxy/gemini-1.5-flash-002,litellm_proxy/Llama-3.1-405b-instruct,litellm_proxy/Llama-3.1-70b-instruct,litellm_proxy/deepseek-chat")
   - `LLM_API_KEY`: Your API key to access the LLM Router for the LLM service
   - `LLM_BASE_URL`: The base URL for the LLM API ("https://llm-proxy.app.all-hands.dev")


6. To trigger the workflow, add the 'fix-me' label to any issue you want the AI to attempt to resolve in an Arena setting.

The workflow will:

- Randomly select two LLMs among given `LLM_MODELS` to  attempt to resolve the issue twice, using the OpenHands resolver and the selected models.
- (Work-In-Progress) Create two branches that corresponds to each of the attempts.
- (Work-In-Progress) When the user selects one of them, it automatically creates a Pull Request of the selected model.
- (Work-In-Progress) Comment on the issue with the results

## Troubleshooting

This project is an extension of [OpenHands GitHub Backlog Resolver](https://github.com/All-Hands-AI/OpenHands/tree/main/openhands/resolver). If you have any issues, please open an issue on this github repo, we're happy to help!
Alternatively, you can [email us](mailto:contact@all-hands.dev) or join the [OpenHands Slack workspace](https://join.slack.com/t/opendevin/shared_invite/zt-2oikve2hu-UDxHeo8nsE69y6T7yFX_BA) and ask there.
