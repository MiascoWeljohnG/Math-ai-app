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

// MathJax is loaded with <script async>, so it may not be ready yet (slow phone connection) or may be blocked; until it
// is, window.MathJax is only the config object from materials.html and has no typesetPromise. Calling it unguarded threw
// inside addAskMessage, so the question never appeared and the Ask button looked dead.
function typesetMath(el) {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
        window.MathJax.typesetPromise([el]).catch((err) => console.log(err));
    }
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

// ---------------------------------------------------------------------------------------------
// PDF preview.
// Desktop browsers show a PDF inside an <iframe> just fine. Phones and tablets do not: Android Chrome / Brave
// replace the iframe with a grey "PDF - Open" placeholder whose button does nothing (it points at a blob: URL),
// and iOS Safari only shows page 1. So on those devices the pages are drawn with pdf.js instead, which works
// in every browser. pdf.js is loaded only when a PDF is opened on such a device.
// ---------------------------------------------------------------------------------------------
const PDFJS_BASE = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
let pdfjsPromise = null;
let selectSeq = 0;           // bumps on every file pick, so a slow download can't overwrite a newer pick
let currentBlobUrl = null;
let pdfViewerCleanup = null;

function prefersPdfJs() {
    const ua = navigator.userAgent || "";
    const phoneOrTablet = /Android|iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(navigator.platform || "") && navigator.maxTouchPoints > 1);
    return phoneOrTablet || window.matchMedia("(max-width: 820px)").matches;   // 820px = the breakpoint in css/mobile.css
}

function loadPdfJs() {
    if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
    if (!pdfjsPromise) {
        pdfjsPromise = new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = PDFJS_BASE + "pdf.min.js";
            script.onload = () => {
                window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_BASE + "pdf.worker.min.js";
                resolve(window.pdfjsLib);
            };
            script.onerror = () => { pdfjsPromise = null; reject(new Error("pdf.js could not be loaded")); };
            document.head.appendChild(script);
        });
    }
    return pdfjsPromise;
}

function teardownPdfViewer() {
    if (pdfViewerCleanup) { pdfViewerCleanup(); pdfViewerCleanup = null; }
}

// Last resort when the preview can't be drawn: a working download link (blob: links need no login header).
function showPdfFallback(url, displayName) {
    const holder = document.createElement("div");
    holder.className = "pdf-placeholder";
    holder.dataset.pdfUrl = url;
    holder.dataset.pdfName = displayName;
    holder.innerHTML = `<div>Couldn't show a preview here.<br><a href="${url}" download="${escapeHtml(displayName)}" style="color:#93c5fd; margin-top:0.5rem; display:inline-block;">Download ${escapeHtml(displayName)}</a></div>`;
    pdfPane.replaceChildren(holder);
}

async function renderPdfJs(blob, url, displayName, seq) {
    const pdfjsLib = await loadPdfJs();
    const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(await blob.arrayBuffer()) }).promise;
    if (seq !== selectSeq) { pdf.destroy(); return; }
    const first = await pdf.getPage(1);
    if (seq !== selectSeq) { pdf.destroy(); return; }
    const base = first.getViewport({ scale: 1 });
    const total = pdf.numPages;

    const wrap = document.createElement("div");
    wrap.className = "pdfjs-wrap";
    wrap.dataset.pdfUrl = url;                 // css/mobile.js reads these for the "Download" button in the top bar
    wrap.dataset.pdfName = displayName;
    wrap.innerHTML = `
        <div class="pdfjs-scroll"><div class="pdfjs-pages"></div></div>
        <div class="pdfjs-bar">
            <button type="button" class="pdfjs-zoom-out" aria-label="Zoom out">&minus;</button>
            <span class="pdfjs-pageno" aria-live="polite"></span>
            <button type="button" class="pdfjs-zoom-in" aria-label="Zoom in">+</button>
        </div>`;
    pdfPane.replaceChildren(wrap);

    const scroller = wrap.querySelector(".pdfjs-scroll");
    const pagesEl = wrap.querySelector(".pdfjs-pages");
    const pageNoEl = wrap.querySelector(".pdfjs-pageno");
    const zoomOutBtn = wrap.querySelector(".pdfjs-zoom-out");
    const zoomInBtn = wrap.querySelector(".pdfjs-zoom-in");

    const pageEls = [];
    let io = null;
    let zoom = 1;
    let scale = 1;
    let laidOutWidth = 0;

    // Pages are only drawn while near the screen (a module can be 300+ pages) and cleared again when far away.
    const unrender = (el) => {
        el._wanted = false;
        if (el._task) { try { el._task.cancel(); } catch (_) { /* already finished */ } el._task = null; }
        el._rendered = false;
        el.replaceChildren();
    };

    async function renderPage(el) {
        if (el._busy || el._rendered) return;
        el._busy = true;
        const forScale = scale;
        try {
            const page = await pdf.getPage(Number(el.dataset.n));
            if (!el._wanted || !el.isConnected || forScale !== scale) return;
            const vp = page.getViewport({ scale: forScale });
            const ratio = Math.max(1, Math.min(window.devicePixelRatio || 1, 2, 2600 / vp.width));   // sharp, but bounded for phone memory
            const canvas = document.createElement("canvas");
            canvas.width = Math.floor(vp.width * ratio);
            canvas.height = Math.floor(vp.height * ratio);
            canvas.style.width = "100%";
            canvas.style.height = "100%";
            const task = page.render({
                canvasContext: canvas.getContext("2d"),
                viewport: vp,
                transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
            });
            el._task = task;
            await task.promise;
            el._task = null;
            if (!el._wanted || !el.isConnected || forScale !== scale) return;
            el.style.width = `${vp.width}px`;
            el.style.height = `${vp.height}px`;
            el.replaceChildren(canvas);
            el._rendered = true;
        } catch (_) { /* render cancelled because the page scrolled away, or this one page is unreadable */ }
        finally { el._busy = false; }
    }

    function updatePageNo() {
        const mid = scroller.scrollTop + scroller.clientHeight * 0.35;
        let lo = 0, hi = pageEls.length - 1;
        while (lo < hi) {
            const m = (lo + hi) >> 1;
            if (pageEls[m].offsetTop + pageEls[m].offsetHeight < mid) lo = m + 1; else hi = m;
        }
        pageNoEl.textContent = `Page ${lo + 1} of ${total}`;
    }

    function layout() {
        const available = scroller.clientWidth || wrap.clientWidth;
        if (!available) return;   // the Read tab is hidden right now; the ResizeObserver calls this again when it shows
        const cssWidth = Math.max(160, available - 16) * zoom;
        if (pageEls.length && Math.abs(cssWidth - laidOutWidth) < 4) return;
        const keep = scroller.scrollHeight > 0 ? scroller.scrollTop / scroller.scrollHeight : 0;
        laidOutWidth = cssWidth;
        scale = cssWidth / base.width;
        if (io) io.disconnect();
        pageEls.forEach(unrender);
        pagesEl.replaceChildren();
        pageEls.length = 0;
        const height = Math.round(cssWidth * base.height / base.width);
        for (let n = 1; n <= total; n++) {
            const el = document.createElement("div");
            el.className = "pdfjs-page";
            el.dataset.n = String(n);
            el.style.width = `${Math.round(cssWidth)}px`;
            el.style.height = `${height}px`;
            pagesEl.appendChild(el);
            pageEls.push(el);
        }
        io = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                entry.target._wanted = entry.isIntersecting;
                if (entry.isIntersecting) renderPage(entry.target); else unrender(entry.target);
            }
        }, { root: scroller, rootMargin: "900px 0px" });
        pageEls.forEach(el => io.observe(el));
        scroller.scrollTop = keep * scroller.scrollHeight;
        updatePageNo();
        zoomOutBtn.disabled = zoom <= 1;
        zoomInBtn.disabled = zoom >= 3;
    }

    const setZoom = (next) => { zoom = Math.min(3, Math.max(1, next)); layout(); };
    zoomOutBtn.addEventListener("click", () => setZoom(zoom - 0.5));
    zoomInBtn.addEventListener("click", () => setZoom(zoom + 0.5));

    let ticking = false;
    scroller.addEventListener("scroll", () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => { ticking = false; updatePageNo(); });
    }, { passive: true });

    const resizeObserver = new ResizeObserver(() => layout());   // rotation, or the Read tab becoming visible
    resizeObserver.observe(scroller);
    layout();

    pdfViewerCleanup = () => {
        resizeObserver.disconnect();
        if (io) io.disconnect();
        pageEls.forEach(unrender);
        try { pdf.destroy(); } catch (_) { /* already gone */ }
    };
}

// The file endpoint wants the login token in a header, which a plain <a href> can't send, so downloads go through fetch.
async function downloadMaterial(filename, displayName, btn) {
    const label = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "Downloading..."; }
    try {
        const res = await fetch(`${API}/materials/${encodeURIComponent(filename)}/file`, { headers: authHeaders() });
        if (!res.ok) throw new Error();
        const url = URL.createObjectURL(await res.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = displayName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 15000);
        if (btn) { btn.disabled = false; btn.textContent = label; }
    } catch (_) {
        if (btn) { btn.disabled = false; btn.textContent = "Failed - tap to retry"; }
    }
}

async function selectFile(filename, displayName, btnEl) {
    const seq = ++selectSeq;
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
                if (seq !== selectSeq) return;
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
    teardownPdfViewer();
    pdfPane.innerHTML = `<div class="pdf-placeholder">Loading ${escapeHtml(displayName)}...</div>`;

    const isPptx = displayName.toLowerCase().endsWith(".pptx");
    const isPdf = displayName.toLowerCase().endsWith(".pdf");

    try {
        if (isPptx) {
            const res = await fetch(`${API}/materials/${encodeURIComponent(filename)}/slides`, { headers: authHeaders() });
            if (seq !== selectSeq) return;
            if (res.ok) {
                const data = await res.json();
                if (seq !== selectSeq) return;
                renderPptxViewer(data, filename, displayName);
                return;
            }
        }

        const res = await fetch(`${API}/materials/${encodeURIComponent(filename)}/file`, { headers: authHeaders() });
        if (!res.ok) throw new Error();
        const blob = await res.blob();
        if (seq !== selectSeq) return;   // another file was picked while this one downloaded
        if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
        const url = currentBlobUrl = URL.createObjectURL(blob);
        const safeName = escapeHtml(displayName);

        if (blob.type === "application/pdf" || isPdf) {
            if (prefersPdfJs()) {
                try {
                    await renderPdfJs(blob, url, displayName, seq);
                } catch (err) {
                    console.warn("PDF preview failed:", err);
                    if (seq === selectSeq) showPdfFallback(url, displayName);
                }
                return;
            }
            pdfPane.innerHTML = `<iframe src="${url}" title="${safeName}"></iframe>`;
        } else {
            pdfPane.innerHTML = `<div class="pdf-placeholder">Preview isn't available for this file type.<br><a href="${url}" download="${safeName}" style="color:#93c5fd; margin-top:0.5rem; display:inline-block;">Download ${safeName}</a></div>`;
        }
    } catch (_) {
        if (seq === selectSeq) pdfPane.innerHTML = `<div class="pdf-placeholder">Couldn't load this file.</div>`;
    }
}

function renderPptxViewer(data, filename, displayName) {
    const slides = data.slides || [];
    if (slides.length === 0) {
        pdfPane.innerHTML = `<div class="pdf-placeholder"><div>Presentation is empty or contains no readable slides.<br><button type="button" class="pptx-action-btn" id="pptxDownloadBtn" style="margin-top:0.75rem;">Download ${escapeHtml(displayName)}</button></div></div>`;
        pdfPane.querySelector("#pptxDownloadBtn").addEventListener("click", (e) => downloadMaterial(filename, displayName, e.currentTarget));
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
                    <button type="button" class="pptx-action-btn" id="pptxDownloadBtn">Download PPTX</button>
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

    pdfPane.querySelector("#pptxDownloadBtn").addEventListener("click", (e) => downloadMaterial(filename, displayName, e.currentTarget));

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
    typesetMath(div);
    
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
                    typesetMath(thinkingDiv);
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