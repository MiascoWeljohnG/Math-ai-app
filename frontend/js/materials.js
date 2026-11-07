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

const branchFilterEl = document.getElementById("branchFilter");
let allFiles = [];
let subjectNames = [];   // the school's subjects: what the topic dropdown offers
let activeBranch = "All";
let searchQuery = "";

const sameBranch = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

// Every subject of the school (the teacher's own subjects are not for students, so personal ones are left out), then any
// other topic a file is still filed under, such as "General" or a subject that was deleted, so no file becomes unreachable.
function branchChoices() {
    const choices = [];
    const add = name => {
        name = String(name || "").trim();
        if (name && !choices.some(existing => sameBranch(existing, name))) choices.push(name);
    };
    subjectNames.forEach(add);
    allFiles.map(file => file.branch).sort((a, b) => String(a).localeCompare(String(b))).forEach(add);
    return choices;
}

// Fills the dropdown once the subjects and files are known. Only the options change, so the search box keeps its text and focus.
function fillBranchOptions() {
    const select = document.getElementById("branchSelect");
    if (!select) return;
    const choices = branchChoices();
    const current = choices.find(name => sameBranch(name, activeBranch));
    activeBranch = current || "All";   // a topic that no longer exists falls back to All
    select.replaceChildren(new Option("All topics", "All"), ...choices.map(name => new Option(name, name)));
    select.value = activeBranch;
}

async function loadSubjects() {
    try {
        const res = await fetch(`${API}/subjects`, { headers: authHeaders() });
        if (!res.ok) return;
        subjectNames = (await res.json()).filter(subject => !subject.is_personal).map(subject => subject.name);
    } catch (_) { /* the files still load; the dropdown just lists the topics they carry */ }
}

// Built once (not on every change) so the search box keeps focus while the user types.
function renderFilters() {
    branchFilterEl.innerHTML = "";

    const searchWrap = document.createElement("div");
    searchWrap.className = "search-wrap";
    searchWrap.innerHTML = `
        <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`;
    const search = document.createElement("input");
    search.type = "text";
    search.id = "fileSearch";
    search.className = "file-search";
    search.placeholder = "Search modules...";
    search.autocomplete = "off";
    search.setAttribute("aria-label", "Search modules");
    search.addEventListener("input", () => { searchQuery = search.value; clearBtn.hidden = !search.value; renderFiles(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Escape" && search.value) { clearSearch(); } });
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "search-clear";
    clearBtn.setAttribute("aria-label", "Clear search");
    clearBtn.textContent = "\u00d7";
    clearBtn.hidden = true;
    const clearSearch = () => { search.value = ""; searchQuery = ""; clearBtn.hidden = true; renderFiles(); search.focus(); };
    clearBtn.addEventListener("click", clearSearch);
    searchWrap.append(search, clearBtn);

    const selectWrap = document.createElement("div");
    selectWrap.className = "select-wrap";
    const select = document.createElement("select");
    select.id = "branchSelect";
    select.className = "branch-select";
    select.setAttribute("aria-label", "Filter by topic");
    select.add(new Option("All topics", "All"));   // the subjects are added by fillBranchOptions() once they have loaded
    select.value = activeBranch;
    select.addEventListener("change", () => { activeBranch = select.value; renderFiles(); });
    selectWrap.appendChild(select);

    branchFilterEl.append(searchWrap, selectWrap);
}

function renderFiles() {
    const query = searchQuery.trim().toLowerCase();
    const files = allFiles.filter(f =>
        (activeBranch === "All" || sameBranch(f.branch, activeBranch)) &&
        (!query || (f.display_name || "").toLowerCase().includes(query))
    );
    if (files.length === 0) {
        let msg;
        if (allFiles.length === 0) msg = "No materials uploaded yet.";
        else if (query) msg = `No modules match "${searchQuery.trim()}"${activeBranch === "All" ? "" : ` in ${activeBranch}`}.`;
        else msg = `No ${activeBranch} materials yet.`;
        fileList.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "file-empty";
        empty.textContent = msg;   // textContent so a typed query can't inject HTML
        fileList.appendChild(empty);
        return;
    }
    fileList.innerHTML = "";
    for (const f of files) {
        const btn = document.createElement("button");
        btn.className = "file-item" + (f.filename === currentFilename ? " active" : "");
        const name = document.createElement("div");
        name.textContent = f.display_name;
        const badge = document.createElement("span");
        badge.className = `branch-badge badge-${String(f.branch).replace(/[^A-Za-z0-9_-]+/g, "-")}`;
        badge.textContent = f.branch;
        btn.appendChild(name);
        btn.appendChild(badge);
        btn.addEventListener("click", () => selectFile(f.filename, f.display_name, btn));
        fileList.appendChild(btn);
    }
}

async function loadFiles() {
    renderFilters();
    try {
        const [res] = await Promise.all([fetch(`${API}/materials`, { headers: authHeaders() }), loadSubjects()]);
        if (!res.ok) throw new Error();
        allFiles = await res.json();
        fillBranchOptions();
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

    const isPptx = displayName.toLowerCase().endsWith(".pptx");

    try {
        if (isPptx) {
            const res = await fetch(`${API}/materials/${encodeURIComponent(filename)}/slides`, { headers: authHeaders() });
            if (res.ok) {
                const data = await res.json();
                renderPptxViewer(data, filename, displayName);
                return;
            }
        }

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

function renderPptxViewer(data, filename, displayName) {
    const slides = data.slides || [];
    if (slides.length === 0) {
        pdfPane.innerHTML = `<div class="pdf-placeholder">Presentation is empty or contains no readable slides.<br><a href="${API}/materials/${encodeURIComponent(filename)}/file" download="${displayName}" style="color:#93c5fd; margin-top:0.5rem; display:inline-block;">Download ${displayName}</a></div>`;
        return;
    }

    let currentSlideIdx = 0;

    function buildSlideHtml(slide) {
        const bulletsHtml = slide.bullets && slide.bullets.length > 0
            ? `<ul class="pptx-bullet-list">${slide.bullets.map(b => `<li>${escapeHtml(b)}</li>`).join("")}</ul>`
            : `<p style="color:#94a3b8; font-style:italic; font-size:0.9rem;">No bullet points on this slide</p>`;

        let tablesHtml = "";
        if (slide.tables && slide.tables.length > 0) {
            tablesHtml = slide.tables.map(table => {
                const rows = table.map((row, rIdx) => {
                    const tag = rIdx === 0 ? "th" : "td";
                    return `<tr>${row.map(c => `<${tag}>${escapeHtml(c)}</${tag}>`).join("")}</tr>`;
                }).join("");
                return `<table class="pptx-table">${rows}</table>`;
            }).join("");
        }

        const notesHtml = slide.notes
            ? `<div class="pptx-notes-box"><div class="pptx-notes-label">Speaker Notes</div><div>${escapeHtml(slide.notes)}</div></div>`
            : "";

        return `
            <div class="pptx-card">
                <div class="pptx-card-title">${escapeHtml(slide.title || `Slide ${slide.slide_number}`)}</div>
                ${bulletsHtml}
                ${tablesHtml}
                ${notesHtml}
            </div>
        `;
    }

    function update() {
        const slide = slides[currentSlideIdx];
        const container = pdfPane.querySelector(".pptx-preview-container");
        if (!container) return;

        const stage = container.querySelector(".pptx-stage");
        const info = container.querySelector(".pptx-slide-info");
        const prevBtn = container.querySelector("#pptxPrevBtn");
        const nextBtn = container.querySelector("#pptxNextBtn");

        stage.innerHTML = buildSlideHtml(slide);
        info.textContent = `Slide ${currentSlideIdx + 1} of ${slides.length}`;
        prevBtn.disabled = currentSlideIdx === 0;
        nextBtn.disabled = currentSlideIdx === slides.length - 1;
    }

    pdfPane.innerHTML = `
        <div class="pptx-preview-container">
            <div class="pptx-toolbar">
                <div class="pptx-nav-group">
                    <button class="pptx-nav-btn" id="pptxPrevBtn">◀ Prev</button>
                    <span class="pptx-slide-info">Slide 1 of ${slides.length}</span>
                    <button class="pptx-nav-btn" id="pptxNextBtn">Next ▶</button>
                </div>
                <div class="pptx-actions">
                    <a class="pptx-action-btn" href="${API}/materials/${encodeURIComponent(filename)}/file" download="${displayName}">Download PPTX</a>
                </div>
            </div>
            <div class="pptx-stage"></div>
        </div>
    `;

    pdfPane.querySelector("#pptxPrevBtn").addEventListener("click", () => {
        if (currentSlideIdx > 0) {
            currentSlideIdx--;
            update();
        }
    });

    pdfPane.querySelector("#pptxNextBtn").addEventListener("click", () => {
        if (currentSlideIdx < slides.length - 1) {
            currentSlideIdx++;
            update();
        }
    });

    update();
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
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