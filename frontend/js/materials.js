const fileList = document.getElementById("fileList");
const viewerHeader = document.getElementById("viewerHeader");
const pdfPane = document.getElementById("pdfPane");
const askLog = document.getElementById("askLog");
const askInput = document.getElementById("askInput");
const askSendBtn = document.getElementById("askSendBtn");

function authHeaders() {
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

// Ensure markdown doesn't break math brackets
function protectMath(text) {
    if (!text) return "";
    return text
        .replace(/\\\[/g, '\\\\[')         .replace(/\\\]/g, '\\\\]')
        .replace(/\\\(/g, '\\\\(')         .replace(/\\\)/g, '\\\\)');
}

let currentFilename = null;
let readingConversationId = null;

const BRANCH_FILTERS = ["All", "Algebra", "Geometry", "Statistics", "Calculus", "General"];
const branchFilterEl = document.getElementById("branchFilter");
let allFiles = [];
let activeBranch = "All";

function renderBranchFilter() {
    branchFilterEl.innerHTML = "";
    for (const b of BRANCH_FILTERS) {
        const chip = document.createElement("button");
        chip.className = "branch-chip" + (b === activeBranch ? " active" : "");
        chip.textContent = b;
        chip.addEventListener("click", () => { activeBranch = b; renderBranchFilter(); renderFiles(); });
        branchFilterEl.appendChild(chip);
    }
}

function renderFiles() {
    const files = activeBranch === "All" ? allFiles : allFiles.filter(f => f.branch === activeBranch);
    if (files.length === 0) {
        fileList.innerHTML = `<div class="file-empty">${allFiles.length === 0 ? "No materials uploaded yet." : `No ${activeBranch} materials yet.`}</div>`;
        return;
    }
    fileList.innerHTML = "";
    for (const f of files) {
        const btn = document.createElement("button");
        btn.className = "file-item" + (f.filename === currentFilename ? " active" : "");
        const name = document.createElement("div");
        name.textContent = f.display_name;
        const badge = document.createElement("span");
        badge.className = `branch-badge badge-${f.branch}`;
        badge.textContent = f.branch;
        btn.appendChild(name);
        btn.appendChild(badge);
        btn.addEventListener("click", () => selectFile(f.filename, f.display_name, btn));
        fileList.appendChild(btn);
    }
}

async function loadFiles() {
    renderBranchFilter();
    try {
        const res = await fetch(`${API}/materials`, { headers: authHeaders() });
        if (!res.ok) throw new Error();
        allFiles = await res.json();
        renderFiles();
    } catch (_) {
        fileList.innerHTML = `<div class="file-empty">Couldn't load materials.</div>`;
    }
}
loadFiles();

async function selectFile(filename, displayName, btnEl) {
    document.querySelectorAll(".file-item").forEach(b => b.classList.remove("active"));
    btnEl.classList.add("active");
    currentFilename = filename;
    
    // NEW: Retrieve any saved conversation ID for this specific file
    const savedConvos = JSON.parse(localStorage.getItem("material_convos") || "{}");
    readingConversationId = savedConvos[filename] || null;
    
    askLog.innerHTML = "";
    const note = document.createElement("div");
    note.className = "ask-note";
    note.textContent = `Ask anything about "${displayName}" — you can also ask about specific pages, like "what's on page 6?"`;
    askLog.appendChild(note);
    
    // NEW: If we found a past conversation for this file, fetch and display the history
    if (readingConversationId) {
        try {
            const res = await fetch(`${API}/conversations/${readingConversationId}/messages`, { headers: authHeaders() });
            if (res.ok) {
                const messages = await res.json();
                for (const m of messages) {
                    addAskMessage(m.content, m.role === "user" ? "user" : "bot");
                }
            } else {
                readingConversationId = null; // Clear if the server doesn't recognize it
            }
        } catch (_) {
            readingConversationId = null;
        }
    }
    
    viewerHeader.textContent = displayName;
    pdfPane.innerHTML = `<div class="pdf-placeholder">Loading ${displayName}...</div>`;

    try {
        const res = await fetch(`${API}/materials/${encodeURIComponent(filename)}/file`, { headers: authHeaders() });
        if (!res.ok) throw new Error();
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);

        if (blob.type === "application/pdf" || displayName.toLowerCase().endsWith(".pdf")) {
            pdfPane.innerHTML = `<iframe src="${url}" title="${displayName}"></iframe>`;
        } else {
            pdfPane.innerHTML = `<div class="pdf-placeholder">Preview isn't available for this file type.<br><a href="${url}" download="${displayName}" style="color:#93c5fd; margin-top:0.5rem; display:inline-block;">Download ${displayName}</a></div>`;
        }
    } catch (_) {
        pdfPane.innerHTML = `<div class="pdf-placeholder">Couldn't load this file.</div>`;
    }
}

function addAskMessage(text, role) {
    const div = document.createElement("div");
    div.className = `ask-msg ${role}`;
    
    // Parse Markdown and Math
    div.innerHTML = typeof marked !== "undefined" ? marked.parse(protectMath(text)) : text;
    if (typeof MathJax !== "undefined") {
        MathJax.typesetPromise([div]).catch((err) => console.log(err));
    }
    
    askLog.appendChild(div);
    askLog.scrollTop = askLog.scrollHeight;
}

async function sendAskQuestion() {
    const question = askInput.value.trim();
    if (!question) return;

    addAskMessage(question, "user");
    askInput.value = "";
    askSendBtn.disabled = true;
    const thinkingDiv = document.createElement("div");
    thinkingDiv.className = "ask-msg bot";
    thinkingDiv.textContent = "...";
    askLog.appendChild(thinkingDiv);
    askLog.scrollTop = askLog.scrollHeight;

    let streamedText = "";
    let tokensStarted = false;

    try {
        await streamAsk(
            { question, conversation_id: readingConversationId, material_filename: currentFilename },
            {
                onMeta: (event) => {
                    readingConversationId = event.conversation_id;
                    
                    // NEW: Save the generated conversation ID tied to this specific file
                    const savedConvos = JSON.parse(localStorage.getItem("material_convos") || "{}");
                    savedConvos[currentFilename] = readingConversationId;
                    localStorage.setItem("material_convos", JSON.stringify(savedConvos));
                },
                onToken: (text) => {
                    if (!tokensStarted) {
                        tokensStarted = true;
                        thinkingDiv.textContent = "";
                    }
                    streamedText += text;
                    // Render markdown live as it types
                    thinkingDiv.innerHTML = typeof marked !== "undefined" ? marked.parse(protectMath(streamedText)) : streamedText;
                    askLog.scrollTop = askLog.scrollHeight;
                },
                onDone: (event) => {
                    // Render math fractions once the stream finishes
                    if (typeof MathJax !== "undefined") {
                        MathJax.typesetPromise([thinkingDiv]).catch((err) => console.log(err));
                    }
                },
                onError: (detail) => {
                    thinkingDiv.textContent = detail || "Error";
                },
            }
        );
    } finally {
        askSendBtn.disabled = false;
        askInput.focus();
    }
}

askSendBtn.addEventListener("click", sendAskQuestion);
askInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        sendAskQuestion();
    }
});