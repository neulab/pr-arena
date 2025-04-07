# **OpenHands PR Arena ⚔️ - GitHub App**

## How to use
1. Install the App on your GitHub repository.
   - https://github.com/apps/openhands-pr-arena/installations/new
2. Label an issue with `pr-arena` to trigger an automated fix.
   - Create or click a specific issue, and press the `Labels` on the sidebar on your right. Type `pr-arena` to label the issue.
3. Wait for approximately 30 minutes (up to 40 minutes) for the agent to resolve the issue and open the Arena.
4. Click the link in the comment to enter the Arena, and choose preferred model.
5. The selected fix is automatically generated as a Pull Request.

**⭐️ Every progress is updated via comment on issue. Please keep an eye on the comments!**
**⭐️ OpenHands PR-Arena uses frontier models to resolve issues. Enjoy it for free for limited time!**

---

## Privacy Notification
1. The only codes we collect are the `git_diff` we make during resolving the issue. We **never** collect the whole codebase and **never** release the data.
2. **Never** try to modify the workflow. The workflow will not be triggered once modified.

---

## Q&A
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

## Security & Permission (🔒)
This GitHub App requires the following permissions:
- **Read & Write Access** to Issues and Pull Requests to analyze issues and generate pull requests.
- **Workflow Execution** to trigger automated fixes through GitHub Actions.
- **Repository Contents Access** to apply necessary changes and submit pull requests.

No user secrets or sensitive information are stored in repositories. All sensitive operations are securely handled via API.

---

## Support
📌 **Need Help?** Reach out via [Support](mailto:contact@all-hands.dev).