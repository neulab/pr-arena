# PR Arena ⚔️

---

## PR Arena (GitHub App)

You can use PR-Arena **without the API Key** for limited time!

### How to use
0. Install the App on your GitHub repository.
   - https://github.com/apps/openhands-pr-arena/installations/new
1. Go to the repository where the App is installed, or select repositories to install the App below at `Repository access`.
2. Label an issue with `pr-arena` to trigger an automated fix.
  💡 Create or click a specific issue, and press the `Labels` on the sidebar on your right. Type `pr-arena` to label the issue.
3. Wait for approximately 10 minutes (up to 20 minutes) for the agent to resolve the issue and open the Arena.
4. Click the link in the comment to enter the Arena, and choose preferred model.
5. The selected fix is automatically generated as a Pull Request.

**⭐️ Every progress is updated via comment on issue. Please keep an eye on the comments!**
**⭐️ OpenHands PR-Arena uses frontier models to resolve issues. Enjoy it for free for limited time!**

---

### Privacy Notification
1. The only codes we collect are the `git_diff` we make during resolving the issue. We **never** collect the whole codebase and **never** release the data.
2. **Never** try to modify the workflow. The workflow will not be triggered once modified.
3. The followings are what we collect about users, regarding the **Privacy**:
  - User info: `owner`, `repo`, `repo URL`
  - Model info: `user preference on model`, `duration of an attempt`
  - Code info: `agent code (git_diffs)`, `commit hash` 

Note that we **never** access user repository for codebase.

---

###  Q&A
**Q. How can I track the progress?**
A. The agent automatically **comments on the issue** for the following steps:
  - `⚙️ PR-Arena workflow has been triggered. The workflow will automatically timeout after 40 minutes if it takes too long. You can monitor the progress in the repository's Actions tab.`
  - `OpenHands started fixing the issue! You can monitor the progress [here]`
    - Step 1. OpenHands starts fixing the issue. Please wait up to 40 minutes until the next comment.
  - `⚔️PR-Arena is now open⚔️! You can view the proposed fixes and make a decision at [this link]`
    - Step 2. The Arena is open. Enter the Arena via provided link and select the preferred fix.
  - `PR has been created based on the fix you've selected. Please review the changes below.`
    - Step 3. The PR has been created. You could merge the code via provided Pull Request link.

**Q. What happens when error occurs?**
A. The error message will show up in the issue comment whenever the error occurs. You can simply remove the label, wait for 5 seconds, and add it again to retry.

There are three types of error that could occur.
  - **[Agent side error]** If the agent is unable to fix the issue, the workflow terminates with the comment on issue:
  `❌ PR-Arena has failed due to the agent error. Please remove the 'pr-arena' label and add it back to retry.`
  - **[Workflow side error]** If the workflow encounters an error (e.g., when model itself encounters an error), the workflow terminates with the comment on issue:
  `❌ PR-Arena encountered an error while ___. Please remove the 'pr-arena' label and add it back to retry.`
  - **[Timeout error]** If the workflow exceeds 40 minutes, the workflow terminates with the comment on issue:
  `⏱️ PR-Arena workflow has been cancelled due to exceeding the 40-minute timeout limit. This may be due to a complex task or an agent error. Please remove the 'pr-arena' label and add it back to retry.`

**Q. How long does the attempt take?**
A. As the issue description gets complicated, the time it takes for the agent to resolve gets longer. Also, we found that some reasoning models consume longer time for each step. It should **take less than 40 minutes**, so please be patient!

---

### Security & Permission (🔒)
This GitHub App requires the following permissions:
- **Read & Write Access** to Issues and Pull Requests to analyze issues and generate pull requests.
- **Workflow Execution** to trigger automated fixes through GitHub Actions.
- **Repository Contents Access** to apply necessary changes and submit pull requests.

No user secrets or sensitive information are stored in repositories. All sensitive operations are securely handled via API.

---

### Support
📌 **Need Help?** Reach out via [Support](mailto:contact@all-hands.dev).

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
