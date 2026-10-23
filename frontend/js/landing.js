// --- Greeting: "Magandang umaga, Mika" (changes with the time of day) ---
function firstNameOf(full) {
    return (full || "").trim().split(/\s+/)[0] || "";
}
function setGreeting(firstName) {
    const first = (firstName || "").trim();
    if (first) {
        localStorage.setItem("first_name", first);
        const hour = new Date().getHours();
        const greeting = hour < 12 ? "Magandang umaga" : hour < 18 ? "Magandang hapon" : "Magandang gabi";
        document.getElementById("helloTitle").textContent = `${greeting}, ${first}`;
    }
}
setGreeting(localStorage.getItem("first_name") || firstNameOf(localStorage.getItem("full_name")) || localStorage.getItem("username"));
(async function refreshName() {
    try {
        const res = await fetch(`${API}/profile`, { headers: { "Authorization": `Bearer ${localStorage.getItem("token")}` } });
        if (res.ok) setGreeting((await res.json()).first_name);
    } catch (_) { /* keep the cached name */ }
})();

// --- "Type any math topic": hands the topic to the iChatbot, like the tiles below do ---
document.getElementById("topicForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const topic = document.getElementById("topicInput").value.trim();
    if (!topic) { document.getElementById("topicInput").focus(); return; }
    sessionStorage.setItem("landingPendingQuestion", `Teach me ${topic}. Give me an explanation, worked examples, and the solution step by step.`);
    window.location.href = "user.html";
});

// --- Subjects + REAL progress ---
// Each tile's bar shows the lessons this student has actually completed
// (marked on the Lessons page) out of all lessons in that subject, as
// calculated by the backend's GET /progress. Core subjects are the four
// fixed tiles in the HTML; personal subjects are drawn below from /subjects.
const authHeader = { "Authorization": `Bearer ${localStorage.getItem("token")}` };
const tilesGrid = document.getElementById("tilesGrid");
const coreSubjectIds = new Map();

const PERSONAL_ICON = '<svg class="tile-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2V4Z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7V4Z"/></svg>';

async function getJson(path) {
    const res = await fetch(`${API}${path}`, { headers: authHeader });
    if (!res.ok) throw new Error(`${path} failed`);
    return res.json();
}

// Fill one tile's bar + "2 of 4 lessons" + "50% complete" from a /progress entry.
function paintProgress(tile, entry) {
    const total = entry ? entry.total : 0;
    const completed = entry ? entry.completed : 0;
    const percent = entry ? entry.percent : 0;
    tile.querySelector(".tile-progress-fill").style.width = `${percent}%`;
    tile.querySelector(".tile-lessons").textContent =
        total === 0 ? "No lessons yet" : `${completed} of ${total} lesson${total === 1 ? "" : "s"}`;
    tile.querySelector(".tile-progress-pct").textContent = `${percent}% complete`;
}

function paintProgressUnavailable() {
    document.querySelectorAll(".tile .tile-progress-fill").forEach(el => { el.style.width = "0%"; });
    document.querySelectorAll(".tile .tile-lessons").forEach(el => { el.textContent = "Progress unavailable"; });
    document.querySelectorAll(".tile .tile-progress-pct").forEach(el => { el.textContent = ""; });
}

function openLessons(subjectId) {
    window.location.href = `lessons.html?subject=${encodeURIComponent(subjectId)}`;
}

// Core tiles: open that subject's lessons (fall back to the chatbot if the
// subject row doesn't exist yet, as before).
function openBranch(tile) {
    const subjectId = coreSubjectIds.get(tile.dataset.branch);
    if (subjectId) {
        openLessons(subjectId);
        return;
    }
    sessionStorage.setItem("landingPendingQuestion", `I'd like to practice ${tile.dataset.branch}. Can you help me get started?`);
    window.location.href = "user.html";
}
document.querySelectorAll(".tile[data-branch]").forEach(tile => {
    tile.addEventListener("click", () => openBranch(tile));
    tile.addEventListener("keydown", (e) => {
        if (e.target === tile && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openBranch(tile); }
    });
});

// Personal subject tile: same layout as a core tile, plus Open / Remove.
function renderPersonalSubject(subject, entry, beforeElement) {
    const tile = document.createElement("div");
    tile.className = "tile personal-tile";
    tile.tabIndex = 0;
    tile.innerHTML = PERSONAL_ICON +
        '<div class="tile-name"></div>' +
        '<div class="tile-progress-track"><div class="tile-progress-fill"></div></div>' +
        '<div class="tile-progress-meta"><span class="tile-lessons"></span><span class="tile-progress-pct"></span></div>' +
        '<p class="tile-desc"></p>' +
        '<div class="tile-actions">' +
        '<button type="button" class="tile-btn open">Open lessons</button>' +
        '<button type="button" class="tile-btn danger remove">Remove</button>' +
        '</div>';
    // textContent (not innerHTML) for anything the student typed.
    tile.querySelector(".tile-name").textContent = subject.name;
    tile.querySelector(".tile-desc").textContent = subject.description || "Your personal subject";
    paintProgress(tile, entry);

    tile.addEventListener("click", () => openLessons(subject.id));
    tile.addEventListener("keydown", (e) => {
        if (e.target === tile && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openLessons(subject.id); }
    });
    tile.querySelector(".open").addEventListener("click", (e) => { e.stopPropagation(); openLessons(subject.id); });
    tile.querySelector(".remove").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!await uiConfirm(`Remove "${subject.name}"?`, { title: "Remove subject", okText: "Remove", danger: true })) return;
        try {
            const res = await fetch(`${API}/subjects/${subject.id}`, { method: "DELETE", headers: authHeader });
            const result = await res.json();
            if (!res.ok) throw new Error(result.detail || "Couldn't remove the subject.");
            tile.remove();
        } catch (err) {
            await uiAlert(err.message);
        }
    });

    if (beforeElement) beforeElement.before(tile);
    else tilesGrid.appendChild(tile);
    return tile;
}

// Plan lessons from the uploaded file, then write them one by one (each is a separate request, so
// the dialog can show progress). Resolves to how many were created; on failure the error says
// how far it got, and the lessons already written are kept.
async function createLessonsFromFile(subjectId, file, tile, setStatus) {
    const post = async (path, fields) => {
        const data = new FormData();
        data.append("file", file);
        for (const [key, value] of Object.entries(fields)) data.append(key, value);
        const res = await fetch(`${API}/subjects/${subjectId}${path}`, { method: "POST", headers: authHeader, body: data });
        const body = await res.json();
        if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Couldn't create the lessons.");
        return body;
    };
    setStatus("Planning your lessons…");
    const { titles } = await post("/lessons/outline-from-file", { count: 5 });
    let made = 0;
    try {
        for (const title of titles) {
            setStatus(`Writing lesson ${made + 1} of ${titles.length}: ${title}`);
            await post("/lessons/generate-from-file", { topic: title, force: "true" });   // the subject came from this file, so skip the relevance check
            made++;
            paintProgress(tile, { completed: 0, total: made, percent: 0 });
        }
    } catch (err) {
        throw new Error(`Created ${made} of ${titles.length} lessons. ${err.message}`);
    }
    return made;
}

// "+ Add personal subject": a tile the same size as the others.
function renderAddSubjectTile() {
    const addTile = document.createElement("button");
    addTile.type = "button";
    addTile.className = "tile add-subject-tile";
    addTile.innerHTML =
        '<span class="add-icon" aria-hidden="true">+</span>' +
        '<span class="tile-name">Add personal subject</span>' +
        '<span class="tile-desc">Create your own subject and track your lessons.</span>';

    const dialog = document.getElementById("addSubjectDialog");
    const form = document.getElementById("addSubjectForm");
    const nameInput = document.getElementById("newSubjectName");
    const descInput = document.getElementById("newSubjectDesc");
    const errorEl = document.getElementById("addSubjectError");
    const saveBtn = document.getElementById("saveAddSubject");
    const fileInput = document.getElementById("newSubjectFile");
    const autoFillBtn = document.getElementById("autoFillSubject");
    const autoFillStatus = document.getElementById("autoFillStatus");

    addTile.addEventListener("click", () => {
        form.reset();
        errorEl.textContent = "";
        autoFillStatus.textContent = "";
        autoFillBtn.disabled = true;
        lessonsRow.hidden = true;
        dialog.showModal();
        nameInput.focus();
    });

    // Let the AI propose a name + description from an uploaded PDF/DOCX. Nothing is saved here;
    // the student can edit both fields and then press "Add subject".
    const lessonsRow = document.getElementById("makeLessonsRow");
    const makeLessons = document.getElementById("makeLessons");
    const cancelBtn = document.getElementById("cancelAddSubject");
    fileInput.addEventListener("change", () => {
        autoFillBtn.disabled = !fileInput.files.length;
        lessonsRow.hidden = !fileInput.files.length;
        autoFillStatus.textContent = "";
    });
    autoFillBtn.addEventListener("click", async () => {
        const file = fileInput.files[0];
        if (!file) return;
        const data = new FormData();
        data.append("file", file);
        autoFillBtn.disabled = true;
        autoFillStatus.textContent = "Reading your file… this can take a moment.";
        errorEl.textContent = "";
        try {
            const res = await fetch(`${API}/subjects/suggest`, { method: "POST", headers: authHeader, body: data });
            const result = await res.json();
            if (!res.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Couldn't read that file.");
            nameInput.value = result.name;
            descInput.value = result.description;
            autoFillStatus.textContent = "Done. Check the name and description, edit them if you like, then add the subject.";
        } catch (err) {
            autoFillStatus.textContent = "";
            errorEl.textContent = err.message;
        } finally {
            autoFillBtn.disabled = false;
        }
    });
    document.getElementById("cancelAddSubject").addEventListener("click", () => dialog.close());
    nameInput.addEventListener("input", () => { errorEl.textContent = ""; });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = nameInput.value.trim();
        if (!name) { errorEl.textContent = "Please give your subject a name."; nameInput.focus(); return; }
        saveBtn.disabled = true;
        errorEl.textContent = "";
        try {
            const res = await fetch(`${API}/subjects`, {
                method: "POST",
                headers: { ...authHeader, "Content-Type": "application/json" },
                body: JSON.stringify({ name, description: descInput.value.trim() || null }),
            });
            const result = await res.json();
            if (!res.ok) {
                throw new Error(typeof result.detail === "string" ? result.detail : "Please check the name and description.");
            }
            // A brand-new subject has no lessons yet: 0 of 0.
            const tile = renderPersonalSubject(result, { completed: 0, total: 0, percent: 0 }, addTile);
            const file = fileInput.files[0];
            if (file && makeLessons.checked) {
                // The subject exists now; keep the dialog open (locked) while its lessons are written.
                cancelBtn.disabled = true;
                try {
                    await createLessonsFromFile(result.id, file, tile, (text) => { autoFillStatus.textContent = text; });
                } catch (err) {
                    await uiAlert(`${err.message} You can write the rest from the Lessons page.`);
                } finally {
                    cancelBtn.disabled = false;
                }
            }
            dialog.close();
        } catch (err) {
            errorEl.textContent = err.message;
        } finally {
            saveBtn.disabled = false;
        }
    });

    tilesGrid.appendChild(addTile);
}

async function loadSubjectsAndProgress() {
    // Fetch both at once; either can fail without breaking the other.
    const [subjectsResult, progressResult] = await Promise.allSettled([getJson("/subjects"), getJson("/progress")]);
    const subjects = subjectsResult.status === "fulfilled" ? subjectsResult.value : [];
    const progress = progressResult.status === "fulfilled" ? progressResult.value : null;

    coreSubjectIds.clear();
    for (const subject of subjects) {
        if (!subject.is_personal) coreSubjectIds.set(subject.name, subject.id);
    }

    if (progress) {
        document.querySelectorAll(".tile[data-branch]").forEach(tile => {
            paintProgress(tile, progress.find(p => !p.is_personal && p.branch === tile.dataset.branch));
        });
    } else {
        paintProgressUnavailable();
    }

    for (const subject of subjects.filter(s => s.is_personal)) {
        const entry = progress ? progress.find(p => p.is_personal && p.subject_id === subject.id) : null;
        renderPersonalSubject(subject, entry);
    }
    renderAddSubjectTile();
    if (!progress) paintProgressUnavailable();
}

loadSubjectsAndProgress();

// "Continue learning": the first subject that has a lesson up next, with that subject's progress.
function paintResumeCard(subjects) {
    const subject = subjects.find(s => s.total && s.lessons.some(l => l.status === "next"));
    if (!subject) return;
    const index = subject.lessons.findIndex(l => l.status === "next");
    const next = subject.lessons[index];
    const percent = Math.round((subject.completed / subject.total) * 100) || 0;
    document.getElementById("resumeRing").style.setProperty("--p", `${percent}%`);
    document.getElementById("resumePct").textContent = `${percent}%`;
    document.getElementById("resumeTitle").textContent = next.title;
    document.getElementById("resumeMeta").textContent = `${subject.branch} · Lesson ${index + 1} of ${subject.total}`;
    document.getElementById("resumeBtn").href = `lessons.html?subject=${subject.subject_id}&lesson=${next.id}`;
    document.getElementById("resumeCard").hidden = false;
}

// "Your roadmap": one line per subject with progress and the next lesson to open. Details live on roadmap.html.
async function loadRoadmapSummary() {
    const list = document.getElementById("roadmapList");
    try {
        const { subjects } = await getJson("/learning/roadmap");
        paintResumeCard(subjects);
        const rows = subjects.filter(s => s.total).map(subject => {
            const next = subject.lessons.find(l => l.status === "next");
            const item = document.createElement("li");
            const branch = Object.assign(document.createElement("span"), { className: "rm-branch", textContent: subject.branch });
            const meta = Object.assign(document.createElement("span"), { className: "rm-meta", textContent: `${subject.completed} of ${subject.total} lessons done` });
            item.append(branch, meta);
            if (next) {
                item.append(Object.assign(document.createElement("a"), {
                    href: `lessons.html?subject=${subject.subject_id}&lesson=${next.id}`,
                    textContent: `Up next: ${next.title}`,
                }));
            } else {
                item.append(Object.assign(document.createElement("span"), { className: "rm-meta", textContent: "All lessons done" }));
            }
            return item;
        });
        list.replaceChildren(...(rows.length ? rows : [Object.assign(document.createElement("li"), { className: "panel-note", textContent: "No lessons yet. Open a branch above to get started." })]));
    } catch {
        document.getElementById("roadmapPanel").hidden = true;   // a bonus panel: the page works without it
    }
}
loadRoadmapSummary();
initRankings({
    select: document.getElementById("rankBranch"),
    body: document.getElementById("rankBody"),
    empty: document.getElementById("rankEmpty"),
});
