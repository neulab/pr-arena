# ⚔️ OpenHands PR Arena ⚔️

**👐 We welcome your feedback. Feel free to fill out the [google form](https://docs.google.com/forms/d/e/1FAIpQLSdNwc2LuqpC7cMrHblH_ZV8PeubWomXh4t2rHQR4Q_Z2VXYKA/viewform?usp=dialog), send an [email](mailto:jiseungh@andrew.cmu.edu), or open an issue on this repository. 👐**

*OpenHands PR Arena* is a platform for evaluating and benchmarking agentic coding assistants through paired pull request (PR) generations. PR Arena enables developers to compare multiple LLMs in real-world issue resolution by presenting side-by-side pull requests and allowing users to select the better fix.

Follow the instruction below to setup the Arena setting for the OpenHands resolver.

![Demo](assets/img/demo.gif)

### Maintainer
[![X (formerly Twitter) Follow](https://img.shields.io/twitter/follow/jiseungh99?style=flat-square&logo=x&label=Jiseung%20Hong)](https://x.com/jiseungh99)
[![GitHub](https://img.shields.io/badge/JiseungHong-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/JiseungHong)
[![Website](https://img.shields.io/badge/wlqmfl.com-4285F4?style=flat-square&logo=google-chrome&logoColor=white)](https://wlqmfl.com)

## How to Get Started with the OpenHands PR Arena GitHub App

### How to use

1. Install OpenHands PR Arena to your GitHub Repository
    - Go to the [installation page](https://github.com/apps/openhands-pr-arena/installations/new)
    - Under **Repository access**, select the repositories you want to install the app on

### Once you've installed the GitHub App ...
🎉 You’re all set. Let’s start fixing your GitHub issues!

2. Open the repository where the GitHub App was installed (i.e., where you’d like to resolve issues).
3. Label an issue with `pr-arena` to trigger the automated fix:
    - Open or create an issue, click `Labels` in the sidebar, and select `pr-arena`
4. Wait for the agent to resolve the issue and open the Arena (this may take 10-20 minutes)
5. Click the link in the comment to enter the Arena and choose your preferred model
6. The selected fix will be automatically submitted as a Pull Request

⭐️ Please watch the [guideline video](https://youtu.be/BV2Rj_zlk2g) that explains how to use the OpenHands PR Arena GitHub App!

### Arena Lifecycle
- Progress is continuously updated via **comments** on the issue — keep an eye on them!
- The Arena will automatically close 60 minutes after the label is applied, **but you can still view fixes and vote**.
- For guidance on locally testing proposed fixes and viewing Arena results after closure, see [ARENA_GUIDE.md](ARENA_GUIDE.md).

## Privacy Notification
1. The only code we collect is the `git_diff` generated during issue resolution. We **never** access or store the entire codebase, access GitHub secrets, or release any user data.
2. **Important**: Installing this App will automatically add a workflow file named `pr-arena-workflow.yml` to your repository. This file redirects to the actual resolver workflow located [here](https://github.com/neulab/pr-arena/blob/main/.github/workflows/pr-arena-resolver.yml). If you are concerned about repository workflows, we encourage you to review the resolver workflow to understand the operations it performs.
3. Do not modify the injected workflow. Any modifications will prevent it from being triggered.
4. Please install and use this app **only** on repositories where you consent to having code snippets (i.e., `git_diff`) processed by the LLM provider.
5. The following metadata is collected for research purpose:
    - User info: `owner`, `repo`, `repo URL`
    - Model info: `user preference on model`, `duration of an attempt`
    - Code info: `agent code (git_diffs)`, `commit hash`, `repository language composition`

##  Q&A
**Q. How can I track the progress?**

A. The agent will automatically **comment on the issue** at each stage of the process:
  - `👐 OpenHands PR-Arena has started the task: [click here for details]. For more info about how to use OpenHands PR-Arena, [click this link].`
    - Step 1. OpenHands begins resolving the issue. Please wait 10 ~ 20 minutes for the next comment.
  - `⚔️PR-Arena is now open⚔️! You can view the proposed fixes and make a decision at [this link].`
    - Step 2. The Arena is open. Click the link to review both fixes and choose your preferred one.
  - `PR has been created based on the fix you've selected. Please review the changes.`
    - Step 3. A pull request has been created. You can now review and merge it.

**Q. What happens if an error occurs?**

A. If an error occurs, the agent will comment on the issue with an appropriate message. You can retry by removing the `pr-arena` label, waiting 5 seconds, and adding it again.

**Q. How long does the process take?**

A. The time depends on the complexity of the issue. Some reasoning models may take longer to process. Typically, it should take **less than 30 minutes**, so please be patient.

**Q. How does this affect my GitHub Actions build minutes?**

A. The workflow makes API calls to our backend infrastructure where OpenHands agents run remotely. Your GitHub Actions runner only handles lightweight tasks like triggering the workflow and creating pull requests. The actual AI processing and code generation happens on our servers, so it consumes minimal GitHub Actions minutes (typically just a few minutes per issue).

## Security & Permission
This GitHub App requires the following permissions:
- **Read & Write access** to Issues and Pull Requests — to analyze issues and generate PRs
- **Workflow execution** — to trigger automated fixes via GitHub Actions
- **Access to repository contents** — to apply code changes and submit pull requests

No user secrets or sensitive information are stored in your repository. All sensitive operations are securely handled through our backend infrastructure.

## Support and Acknowledgment

If you have any issues, please open an issue on this github repo, we're happy to help!
Alternatively, you can [email us](mailto:jiseungh@andrew.cmu.edu) or join the [OpenHands Slack workspace](https://join.slack.com/t/opendevin/shared_invite/zt-2oikve2hu-UDxHeo8nsE69y6T7yFX_BA) and ask there.

This project is built upon [OpenHands GitHub Backlog Resolver](https://github.com/All-Hands-AI/OpenHands/tree/main/openhands/resolver) and inspired by [Copilot Arena](https://github.com/lmarena/copilot-arena), an open source AI coding assistant that provides paired autocomplete completions from different LLMs.

[![Powered by OpenHands](https://img.shields.io/badge/Powered%20by-OpenHands-blue)](https://github.com/openhands)
<!-- ---

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
 -->
