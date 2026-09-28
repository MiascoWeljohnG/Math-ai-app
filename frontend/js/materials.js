const fileList = document.getElementById("fileList");
const viewerHeader = document.getElementById("viewerHeader");
const pdfPane = document.getElementById("pdfPane");
const askLog = document.getElementById("askLog");
const askInput = document.getElementById("askInput");
const askSendBtn = document.getElementById("askSendBtn");

function authHeaders() {
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

let currentFilename = null;
// The conversation for the currently open document. Every question is sent
// with the open file's name, so the AI only sees excerpts from that file.
let readingConversationId = null;

// --- Load the file list (with branch filter) ---
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

// --- Preview a file (fetched as a blob, since the file endpoint needs an
// Authorization header a plain <iframe src="..."> can't send) ---
async function selectFile(filename, displayName, btnEl) {
    document.querySelectorAll(".file-item").forEach(b => b.classList.remove("active"));
    btnEl.classList.add("active");
    currentFilename = filename;
    // Each document gets its own conversation, so questions about one file
    // never carry history from another.
    readingConversationId = null;
    askLog.innerHTML = "";
    const note = document.createElement("div");
    note.className = "ask-note";
    note.textContent = `Ask anything about "${displayName}" — you can also ask about specific pages, like "what's on page 6?"`;
    askLog.appendChild(note);
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
            // Browsers can't render .docx/.txt inline the way they do PDFs —
            // offer a direct download instead of a blank frame.
            pdfPane.innerHTML = `<div class="pdf-placeholder">Preview isn't available for this file type.<br><a href="${url}" download="${displayName}" style="color:#93c5fd; margin-top:0.5rem; display:inline-block;">Download ${displayName}</a></div>`;
        }
    } catch (_) {
        pdfPane.innerHTML = `<div class="pdf-placeholder">Couldn't load this file.</div>`;
    }
}

// --- Ask panel ---
function addAskMessage(text, role) {
    const div = document.createElement("div");
    div.className = `ask-msg ${role}`;
    div.textContent = text;
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

    try {
        const res = await fetch(`${API}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ question, conversation_id: readingConversationId, material_filename: currentFilename }),
        });
        const data = await res.json();
        if (!res.ok) {
            thinkingDiv.textContent = data.detail || "Error";
            return;
        }
        readingConversationId = data.conversation_id;
        thinkingDiv.textContent = data.answer;
    } catch (err) {
        thinkingDiv.textContent = `Network error: ${err.message}`;
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
