// State management
const state = {
    selectedIssue: null,
    selectedModel: null,
    experiments: {},
    prompts: [],
    currentView: 'diff'
};

// Initialize
async function init() {
    await loadExperiments();
    renderIssueButtons();
    setupViewTabs();
}

// Setup view tabs
function setupViewTabs() {
    const tabs = document.querySelectorAll('.view-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            switchView(tab.dataset.view);
        });
    });
}

// Switch view mode
function switchView(view) {
    state.currentView = view;

    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === view);
    });

    loadContent('left');
    loadContent('right');
}

// Load experiments
async function loadExperiments() {
    try {
        const response = await fetch('data.json');
        const data = await response.json();
        state.experiments = data;
    } catch (error) {
        console.error('Failed to load experiments:', error);
        state.experiments = {};
    }
}

// Parse issue folder name
function parseIssueFolder(folderName) {
    const parts = folderName.split('_');
    if (parts.length < 3) return null;

    const issueNumber = parts[parts.length - 1];
    const repo = parts[parts.length - 2];
    const owner = parts.slice(0, parts.length - 2).join('_');

    return { owner, repo, issueNumber, folderName };
}

// Render issue buttons
function renderIssueButtons() {
    const container = document.getElementById('issueButtons');
    container.innerHTML = '';

    const issues = Object.keys(state.experiments);

    if (issues.length === 0) {
        container.innerHTML = '<span style="color: #999; font-size: 12px;">No experiments found</span>';
        return;
    }

    issues.forEach(issueFolder => {
        const parsed = parseIssueFolder(issueFolder);
        if (!parsed) return;

        const btn = document.createElement('button');
        btn.className = 'issue-btn';
        btn.textContent = `${parsed.owner}/${parsed.repo}#${parsed.issueNumber}`;
        btn.onclick = () => selectIssue(issueFolder);
        container.appendChild(btn);
    });

    if (issues.length > 0) {
        selectIssue(issues[0]);
    }
}

// Select an issue
function selectIssue(issueFolder) {
    state.selectedIssue = issueFolder;
    state.selectedModel = null;

    document.querySelectorAll('.issue-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    renderModelButtons();
    clearContent();
}

// Render model buttons
function renderModelButtons() {
    const container = document.getElementById('modelButtons');
    container.innerHTML = '';

    if (!state.selectedIssue) {
        container.innerHTML = '<span style="color: #999; font-size: 12px;">Select an issue</span>';
        return;
    }

    const models = Object.keys(state.experiments[state.selectedIssue] || {});

    if (models.length === 0) {
        container.innerHTML = '<span style="color: #999; font-size: 12px;">No models found</span>';
        return;
    }

    models.forEach(model => {
        const btn = document.createElement('button');
        btn.className = 'model-btn';
        btn.textContent = model;
        btn.onclick = () => selectModel(model);
        container.appendChild(btn);
    });

    if (models.length > 0) {
        selectModel(models[0]);
    }
}

// Select a model
function selectModel(model) {
    state.selectedModel = model;

    document.querySelectorAll('.model-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    loadPrompts();
}

// Load prompts
function loadPrompts() {
    if (!state.selectedIssue || !state.selectedModel) return;

    const prompts = state.experiments[state.selectedIssue][state.selectedModel] || [];
    state.prompts = prompts;

    const leftSelect = document.getElementById('leftPrompt');
    const rightSelect = document.getElementById('rightPrompt');

    leftSelect.innerHTML = '<option value="">-- Select Prompt --</option>';
    rightSelect.innerHTML = '<option value="">-- Select Prompt --</option>';

    if (prompts.length === 0) {
        clearContent();
        return;
    }

    prompts.forEach(prompt => {
        const option1 = document.createElement('option');
        option1.value = prompt;
        option1.textContent = prompt;
        leftSelect.appendChild(option1);

        const option2 = document.createElement('option');
        option2.value = prompt;
        option2.textContent = prompt;
        rightSelect.appendChild(option2);
    });

    leftSelect.onchange = () => loadContent('left');
    rightSelect.onchange = () => loadContent('right');

    clearContent();
}

// Render history
function renderHistory(history, container) {
    container.innerHTML = '';
    container.className = 'content-wrapper history-content';

    if (!history || history.length === 0) {
        container.innerHTML = '<div style="padding: 20px; color: #999;">No history available</div>';
        return;
    }

    history.forEach((item, index) => {
        const role = (item.role || 'message').toLowerCase();
        const content = item.content || item.message || JSON.stringify(item);

        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';

        historyItem.innerHTML = `
            <div class="history-header">
                <span class="history-role ${role}">${role}</span>
                <span class="history-metadata">#${index + 1}</span>
            </div>
            <div class="history-body">${escapeHtml(content)}</div>
        `;

        container.appendChild(historyItem);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Load content
async function loadContent(side) {
    const select = document.getElementById(side + 'Prompt');
    const contentElement = document.getElementById(side + 'Content');
    const titleElement = document.getElementById(side + 'Title');
    const promptName = select.value;

    if (!promptName || !state.selectedIssue || !state.selectedModel) {
        contentElement.textContent = 'Select a prompt to view content';
        contentElement.className = 'content-wrapper empty';
        titleElement.textContent = side === 'left' ? 'Left Panel' : 'Right Panel';
        return;
    }

    const view = state.currentView;

    try {
        let title = '';

        if (view === 'diff') {
            title = `${promptName} - Diff`;
            const path = `/prompt_experiments/${state.selectedIssue}/${state.selectedModel}/${promptName}/patch.diff`;
            const response = await fetch(path);

            if (!response.ok) throw new Error('Diff not found');

            const diffText = await response.text();
            contentElement.className = 'content-wrapper';
            contentElement.innerHTML = '';

            if (diffText.trim()) {
                const diff2htmlUi = new Diff2HtmlUI(contentElement, diffText, {
                    drawFileList: false,
                    matching: 'lines',
                    outputFormat: 'line-by-line',
                    renderNothingWhenEmpty: false,
                });
                diff2htmlUi.draw();
            } else {
                contentElement.className = 'content-wrapper empty';
                contentElement.textContent = 'No diff to display';
            }
        }
        else if (view === 'prompt') {
            title = `${promptName} - Prompt Templates`;
            const userPath = `/prompt_experiments/prompts/${promptName}/user_instructions.jinja`;
            const convPath = `/prompt_experiments/prompts/${promptName}/conversation_instructions.jinja`;

            const [userResp, convResp] = await Promise.all([
                fetch(userPath),
                fetch(convPath)
            ]);

            const userInst = userResp.ok ? await userResp.text() : 'Not found';
            const convInst = convResp.ok ? await convResp.text() : 'Not found';

            const content = `=== User Instructions ===\n\n${userInst}\n\n=== Conversation Instructions ===\n\n${convInst}`;
            contentElement.className = 'content-wrapper';
            contentElement.innerHTML = `<pre class="plain-content">${escapeHtml(content)}</pre>`;
        }
        else if (view === 'summary') {
            title = `${promptName} - Summary`;
            const path = `/prompt_experiments/${state.selectedIssue}/${state.selectedModel}/${promptName}/summary.json`;
            const response = await fetch(path);

            if (!response.ok) throw new Error('Summary not found');

            const json = await response.json();
            const content = JSON.stringify(json, null, 2);
            contentElement.className = 'content-wrapper';
            contentElement.innerHTML = `<pre class="plain-content">${escapeHtml(content)}</pre>`;
        }
        else if (view === 'history') {
            title = `${promptName} - History`;
            const path = `/prompt_experiments/${state.selectedIssue}/${state.selectedModel}/${promptName}/result.json`;
            const response = await fetch(path);

            if (!response.ok) throw new Error('History not found');

            const json = await response.json();
            renderHistory(json.history, contentElement);
        }

        titleElement.textContent = title;
    } catch (error) {
        console.error(`Failed to load ${view} for ${side}:`, error);
        titleElement.textContent = `${promptName} - ${view}`;
        contentElement.textContent = `No ${view} to display`;
        contentElement.className = 'content-wrapper empty';
    }
}

// Clear content
function clearContent() {
    document.getElementById('leftContent').textContent = 'Select a prompt to view content';
    document.getElementById('rightContent').textContent = 'Select a prompt to view content';
    document.getElementById('leftContent').className = 'content-wrapper empty';
    document.getElementById('rightContent').className = 'content-wrapper empty';
    document.getElementById('leftTitle').textContent = 'Left Panel';
    document.getElementById('rightTitle').textContent = 'Right Panel';
}

init();
