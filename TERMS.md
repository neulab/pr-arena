# Terms of Service - OpenHands PR Arena

**Effective Date:** September 9, 2025  
**Last Updated:** September 9, 2025

## 1. Introduction

Welcome to OpenHands PR Arena ("PR Arena", "the Service", "we", "us", or "our"), a competitive framework for coding assistants designed to evaluate and benchmark frontier large language models (LLMs) through paired pull request (PR) generations. PR Arena is operated by NeuLab at Carnegie Mellon University's Language Technologies Institute.

By installing, accessing, or using the OpenHands PR Arena GitHub App or related services, you ("User", "you", or "your") agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the Service.

## 2. Service Description

OpenHands PR Arena provides:
- A platform for evaluating and benchmarking agentic coding assistants
- Paired pull request generations for real-world issue resolution
- Side-by-side comparison of multiple LLM solutions
- Automated issue resolution through AI coding agents
- Research data collection for advancing AI coding capabilities

The Service integrates with GitHub repositories through a GitHub App that processes issues labeled with "pr-arena" and generates comparative solutions using different AI models.

## 3. Eligibility and Account Requirements

### 3.1 Eligibility
- You must have a valid GitHub account to use the Service
- You must have administrative access to the GitHub repository where you install the PR Arena App
- You must be at least 13 years old (or the minimum age in your jurisdiction)
- You must not be prohibited from using the Service under applicable laws

### 3.2 Repository Requirements
- You may only install the PR Arena App on repositories where you have the legal right to authorize code processing
- You must ensure all repository contributors are aware of and consent to PR Arena usage
- The repository must comply with GitHub's Terms of Service

## 4. Data Collection and Privacy

### 4.1 Code Data Collection
- **Scope of Collection**: We collect only the `git_diff` generated during issue resolution
- **What We Do NOT Collect**: 
  - Complete codebase contents
  - GitHub secrets or sensitive credentials
  - Private repository metadata beyond the specific issue and generated diffs
  - Personal information not directly related to the code changes

### 4.2 Research Metadata
We collect the following metadata for research purposes:
- Issue description and labels
- Generated pull request diffs
- User voting preferences between model solutions
- Performance metrics and resolution times
- Model comparison data

### 4.3 Data Usage
- Research and academic publication
- Improving AI coding assistant capabilities
- Benchmarking and evaluation of LLM performance
- Service improvement and optimization

### 4.4 Data Retention
- Code diffs are retained for research purposes
- Anonymized data may be retained indefinitely for academic research
- You may request data deletion by contacting us (see Section 12)

## 5. User Responsibilities and Acceptable Use

### 5.1 Repository Content
You represent and warrant that:
- You have the right to authorize processing of all code in repositories where PR Arena is installed
- Repository content does not violate any third-party rights
- You will not use the Service to process proprietary or confidential code without proper authorization

### 5.2 Prohibited Uses
You may not:
- Use the Service for illegal activities or malicious purposes
- Attempt to reverse engineer or compromise the Service
- Submit issues designed to generate harmful, offensive, or inappropriate code
- Abuse the Service through excessive API calls or resource consumption
- Violate GitHub's Terms of Service or Community Guidelines

### 5.3 Issue Quality
- Submit only legitimate coding issues suitable for automated resolution
- Provide clear, actionable issue descriptions
- Do not submit issues containing sensitive information or credentials

## 6. GitHub App Permissions and Workflow

### 6.1 Required Permissions
The PR Arena GitHub App requires:
- **Read & Write access to Issues and Pull Requests**: To analyze issues and generate comparative solutions
- **Repository Content Read Access**: To understand codebase context for issue resolution
- **Workflow Write Access**: To inject the `pr-arena-workflow.yml` file

### 6.2 Workflow Injection
- Installing the App automatically adds `pr-arena-workflow.yml` to your repository
- This workflow file redirects to our secure resolver workflow
- **Do not modify** the injected workflow file - modifications will prevent proper functionality
- The workflow can be removed by uninstalling the App

### 6.3 Processing Flow
1. User labels issue with "pr-arena"
2. Workflow triggers automated resolution (10-20 minutes)
3. Multiple AI models generate solutions
4. Arena opens for user to compare and vote
5. Selected solution becomes a pull request
6. Arena closes after 60 minutes (viewing/voting may continue)

## 7. Intellectual Property Rights

### 7.1 Service Ownership
- PR Arena and all related technology remain the property of NeuLab/Carnegie Mellon University
- Users retain ownership of their original code and repository content
- Generated code suggestions are provided "as-is" without ownership claims

### 7.2 Generated Code
- AI-generated code suggestions are provided for evaluation purposes
- Users are responsible for reviewing and validating all generated code
- No warranties are provided regarding the functionality or quality of generated code
- Users assume responsibility for any generated code they choose to merge

### 7.3 Research Use
- Anonymized data may be used in research publications and academic work
- Individual user or repository identification will not be disclosed without consent
- Aggregate and statistical data may be shared publicly

## 8. Service Availability and Limitations

### 8.1 Service Availability
- The Service is provided on a "best effort" basis
- We do not guarantee continuous availability or uptime
- Maintenance windows may temporarily interrupt service

### 8.2 Processing Times
- Issue resolution typically takes 10-30 minutes
- Complex issues may require additional processing time
- Some models may take longer than others based on computational requirements

### 8.3 Resource Limitations
- GitHub Actions usage is minimal (lightweight triggering only)
- Actual processing occurs on our infrastructure
- We may implement usage limits to ensure fair access

## 9. Disclaimers and Limitations of Liability

### 9.1 No Warranties
THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.

### 9.2 AI-Generated Content Disclaimer
- AI-generated code may contain errors, bugs, or security vulnerabilities
- Users must review and test all generated code before implementation
- We are not responsible for consequences of using AI-generated code in production systems

### 9.3 Limitation of Liability
TO THE MAXIMUM EXTENT PERMITTED BY LAW, NEULAB AND CARNEGIE MELLON UNIVERSITY SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING FROM YOUR USE OF THE SERVICE.

## 10. Research and Academic Use

### 10.1 Academic and Community-Driven Purpose
This Service operates as a **community-driven research platform** primarily for research and educational purposes to advance the field of AI-assisted software development. The platform facilitates collaborative research by enabling the community to contribute data and insights through their participation in comparative evaluations.

### 10.2 Experimental Nature and Limitations
Users acknowledge that:
- This is an experimental research tool subject to ongoing development and modification
- Results may vary and should not be considered definitive or production-ready
- The platform may experience interruptions, changes, or discontinuation as research priorities evolve
- **Community contributions** help shape the direction and capabilities of the research

### 10.3 Publication Rights
We reserve the right to publish research findings based on anonymized, aggregated data collected through the Service.

### 10.4 Collaboration Opportunities
Users interested in research collaboration or accessing detailed analytics may contact us for potential partnerships.

## 11. Termination

### 11.1 User Termination
You may terminate your use of the Service at any time by:
- Uninstalling the PR Arena GitHub App from your repositories
- Removing the "pr-arena" label from issues
- Ceasing to use the Service

### 11.2 Service Termination
We may terminate or suspend access to the Service:
- For violation of these Terms
- For misuse or abuse of the Service
- If required by law or regulation
- At our discretion with reasonable notice

### 11.3 Effect of Termination
Upon termination:
- Your access to the Service will cease
- Previously collected research data may be retained as described in Section 4
- These Terms will survive termination where applicable

## 12. Contact Information

For questions, concerns, or requests regarding these Terms or the Service:

**NeuLab - Carnegie Mellon University**  
**Language Technologies Institute**  
**Email**: jiseungh@andrew.cmu.edu
**GitHub**: https://github.com/neulab/pr-arena

## 13. Changes to Terms

We reserve the right to modify these Terms at any time. Changes will be effective immediately upon posting to the GitHub repository. Continued use of the Service after changes constitutes acceptance of the revised Terms.

## 14. Governing Law

These Terms are governed by the laws of Pennsylvania, United States, without regard to conflict of law principles. Any disputes shall be resolved in the courts of Pennsylvania.

## 15. Severability

If any provision of these Terms is found to be unenforceable, the remaining provisions will remain in full force and effect.

---

**By using OpenHands PR Arena, you acknowledge that you have read, understood, and agree to be bound by these Terms of Service.**