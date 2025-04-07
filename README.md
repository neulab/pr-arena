# PR Arena ⚔️

---

## PR Arena (GitHub App)

You can use PR-Arena **without the API Key** for limited time!

➡️ Go to [OpenHands PR-Arena GitHub App](https://github.com/neulab/pr-arena/tree/main/openhands_resolver/GitHub%20App)

---

## PR Arena (Manual)

PR Arena is a coding assistant designed to evaluate and improve [OpenHands GitHub Backlog Resolver](https://github.com/All-Hands-AI/OpenHands/tree/main/openhands/resolver) through paired pull request (PR) generations. It enables developers to compare contributions from different LLMs such as GPT-4o, Llama, and more.

This project is inspired by [Copilot Arena](https://github.com/lmarena/copilot-arena), an open source AI coding assistant that provides paired autocomplete completions from different LLMs.

Follow the instruction below to setup the Arena setting for the OpenHands resolver.

## Using the GitHub Actions Workflow

This repository includes a GitHub Actions workflow that can automatically attempt to generate a pair of pull requests for individual issues labeled with 'pr-arena'. Follow the steps to use this workflow in your own repository:

1. Prepare a github personal access token. You can:
    1. [Contact us](mailto:contact@all-hands.dev) and we will set up a token for the [openhands-agent](https://github.com/openhands-agent) account (if you want to make it clear which commits came from the agent.
    2. Choose your own github user that will make the commits to the repo, [and create a personal access token](https://github.com/settings/tokens?type=beta) with read/write scope for "contents", "issues", "pull requests", and "workflows" on the desired repos.

2. Create an API key for the LLMs you will be setting up for the Arena setting. We usually use a single API key which can access the LLM Router.

3. Copy the `.github/workflows/openhands-resolver.yml` file to your repository's `.github/workflows/` directory.

4. Enable read/write workflows for the repository by going to `Settings -> Actions -> General -> Workflow permissions` and selecting "Read and write permissions" and click "Allow Github Actions to create and approve pull requests".

5. Set up the following [GitHub secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) in your repository, or across your entire org if you want to only set ths once and use the resolver in multiple repositories:
   - `PAT_USERNAME`: The github username that you used to create the personal access token.
   - `PAT_TOKEN`: The personal access token for github.
   <!-- - `LLM_MODELS`: The comma seperated LLM models to use (i.e. litellm_proxy/claude-3-5-sonnet-20241022,litellm_proxy/claude-3-5-sonnet-20240620,litellm_proxy/gpt-4o-2024-08-06,litellm_proxy/gpt-4o-2024-05-13,litellm_proxy/gemini-1.5-pro-002,litellm_proxy/gemini-1.5-flash-002,litellm_proxy/Llama-3.1-405b-instruct,litellm_proxy/Llama-3.1-70b-instruct,litellm_proxy/deepseek-chat) -->
   - `LLM_MODELS`: The comma seperated LLM models to use (i.e. litellm_proxy/neulab/claude-3-5-sonnet-20240620, litellm_proxy/neulab/gpt-4o-2024-05-13, litellm_proxy/neulab/gpt-4o-2024-08-06, litellm_proxy/neulab/gpt-4o-mini-2024-07-18, litellm_proxy/neulab/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo, litellm_proxy/neulab/Qwen/Qwen2-72B-Instruct, litellm_proxy/neulab/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo, litellm_proxy/neulab/NousResearch/Hermes-3-Llama-3.1-405B-Turbo, litellm_proxy/neulab/gemini/gemini-1.5-flash, litellm_proxy/neulab/gemini/gemini-1.5-pro, litellm_proxy/neulab/o1-preview, litellm_proxy/neulab/o1-mini, litellm_proxy/neulab/meta-llama/Meta-Llama-3.1-405B-Instruct, litellm_proxy/neulab/meta-llama/Meta-Llama-3.1-70B-Instruct, litellm_proxy/neulab/meta-llama/Meta-Llama-3.1-8B-Instruct, litellm_proxy/neulab/meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo, litellm_proxy/neulab/meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo, litellm_proxy/neulab/deepseek-chat)
   - `LLM_API_KEY`: Your API key to access the LLM Router for the LLM service
   - `LLM_BASE_URL`: The base URL for the LLM API (i.e. https://llm-proxy.app.all-hands.dev)
   - `FIREBASE_CONFIG`: (Only for the prototype) An environment variable containing the Firebase configuration details (e.g., API key, project ID, etc.).


6. To trigger the workflow, add the 'pr-arena' label to any issue you want the AI to attempt to resolve in an Arena setting.

The workflow will:

- Randomly select two LLMs among given `LLM_MODELS` to  attempt to resolve the issue, using the OpenHands resolver and the selected models respectively.
- Create and display two `git_patch`s that corresponds to each of the attempts. (Wait until the GitHub action comments on issue with the webpage URL for you arena!)
- When the user selects one of them, it automatically creates a Pull Request based on the selected model.
- Comment on the issue with the results.

## Troubleshooting

This project is an extension of [OpenHands GitHub Backlog Resolver](https://github.com/All-Hands-AI/OpenHands/tree/main/openhands/resolver). If you have any issues, please open an issue on this github repo, we're happy to help!
Alternatively, you can [email us](mailto:contact@all-hands.dev) or join the [OpenHands Slack workspace](https://join.slack.com/t/opendevin/shared_invite/zt-2oikve2hu-UDxHeo8nsE69y6T7yFX_BA) and ask there.
