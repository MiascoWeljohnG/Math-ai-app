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

// Icons for the classic branches; every other subject gets the book icon. Tone picks the icon colour (see home.css).
const SUBJECT_ICONS = {
    Algebra: '<svg class="tile-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3V3Zm3.2 4.6h1.6V6.4H9.4V5H7.8V3.8H6.2V5H5v1.4h1.2v1.2ZM13 3h8v8h-8V3Zm1.6 4.7h4.8V6.3h-4.8v1.4ZM3 13h8v8H3v-8Zm1.6 1.6 4.8 4.8 1-1-4.8-4.8-1 1Zm0 3.8 1 1 4.8-4.8-1-1-4.8 4.8ZM13 13h8v8h-8v-8Zm1.6 2.4h4.8v1.4h-4.8v-1.4Zm0 2.8h4.8v1.4h-4.8v-1.4Z"/></svg>',
    Geometry: '<svg class="tile-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 5.9 3.3L12 10.9 6.1 7.6 12 4.3ZM5 9.3l6 3.4v6.9l-6-3.3V9.3Zm8 10.3v-6.9l6-3.4v7l-6 3.3Z"/></svg>',
    Statistics: '<svg class="tile-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 0 10 10h-10V2Z"/><path d="M14 2.2V10h7.8A10 10 0 0 0 14 2.2Z"/></svg>',
    Calculus: '<svg class="tile-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3c-2 0-3 1-3.4 3.2L9 17c-.4 2.3-1.5 3.6-3.5 3.6"/><path d="M13 9h4M15 7v4M14 17h5"/></svg>',
};
const DEFAULT_ICON = '<svg class="tile-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2V4Z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7V4Z"/></svg>';
const CLASSIC_DESCRIPTIONS = {
    Algebra: "Algebra is a branch of mathematics that uses symbols to represent unknown numbers and express relationships between quantities.",
    Geometry: "Geometry is the branch of mathematics that studies shapes, sizes, angles and the properties of space.",
    Statistics: "Statistics is the branch of applied mathematics that deals with collecting, analyzing, and presenting data.",
    Calculus: "Calculus is the branch of mathematics that studies continuous change through rates of change and accumulation of quantities.",
};
const CLASSIC_TONES = { Algebra: 0, Geometry: 1, Statistics: 2, Calculus: 3 };

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

// Personal subject tile: same layout as a core tile, plus Open / Remove.
// removable=false is used for subjects a teacher created for the school: students can open them
// but not delete them.
function renderPersonalSubject(subject, entry, beforeElement, removable = true, toneIndex = 0) {
    const tile = document.createElement("div");
    tile.className = removable ? "tile personal-tile" : "tile shared-tile";
    tile.tabIndex = 0;
    tile.dataset.tone = String(toneIndex % 4);
    tile.innerHTML = (SUBJECT_ICONS[subject.name] || DEFAULT_ICON) +
        '<div class="tile-name"></div>' +
        '<div class="tile-progress-track"><div class="tile-progress-fill"></div></div>' +
        '<div class="tile-progress-meta"><span class="tile-lessons"></span><span class="tile-progress-pct"></span></div>' +
        '<p class="tile-desc"></p>' +
        '<div class="tile-actions">' +
        '<button type="button" class="tile-btn open">Open lessons</button>' +
        (removable ? '<button type="button" class="tile-btn danger remove">Remove</button>' : '') +
        '</div>';
    // textContent (not innerHTML) for anything the student typed.
    tile.querySelector(".tile-name").textContent = subject.name;
    tile.querySelector(".tile-desc").textContent = subject.description || CLASSIC_DESCRIPTIONS[subject.name] || (removable ? "Your personal subject" : "Subject from your teacher");
    paintProgress(tile, entry);

    tile.addEventListener("click", () => openLessons(subject.id));
    tile.addEventListener("keydown", (e) => {
        if (e.target === tile && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openLessons(subject.id); }
    });
    tile.querySelector(".open").addEventListener("click", (e) => { e.stopPropagation(); openLessons(subject.id); });
    const removeBtn = tile.querySelector(".remove");
    if (removeBtn) removeBtn.addEventListener("click", async (e) => {
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
    const progress = progressResult.status === "fulfilled" ? progressResult.value : null;
    const loadingNote = document.getElementById("tilesLoading");
    if (loadingNote) loadingNote.remove();

    if (subjectsResult.status !== "fulfilled") {
        tilesGrid.innerHTML = '<p class="panel-note">Couldn\'t load your subjects. Please refresh the page.</p>';
        return;
    }
    const subjects = subjectsResult.value;
    if (!subjects.length) {
        tilesGrid.innerHTML = '<p class="panel-note">No subjects yet. Your teacher can add some from the teacher dashboard.</p>';
        return;
    }

    // One tile per subject straight from the database: the school's (teacher-made) subjects first,
    // then this student's personal ones (the API already returns them in that order).
    subjects.forEach((subject, index) => {
        const entry = progress ? progress.find(p => p.subject_id === subject.id) : null;
        const tone = subject.name in CLASSIC_TONES ? CLASSIC_TONES[subject.name] : index;
        renderPersonalSubject(subject, entry, null, subject.is_personal, tone);
    });
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
// "Your overview": lessons viewed, quizzes done + average score, time spent on quizzes, rank in your school.
function formatDuration(totalSeconds) {
    const seconds = Math.max(0, Math.round(totalSeconds || 0));
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
    if (m) return `${m}m ${String(s).padStart(2, "0")}s`;
    return `${s}s`;
}
function ordinal(n) {
    const rest = n % 100;
    if (rest >= 11 && rest <= 13) return `${n}th`;
    return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
}
async function loadOverview() {
    const set = (id, text) => { document.getElementById(id).textContent = text; };
    try {
        const o = await getJson("/learning/overview");
        const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
        const percentOf = (part, whole) => whole ? Math.round(part * 100 / whole) : 0;

        countUp(document.getElementById("ovLessons"), o.lessons_viewed, n => `${n} of ${o.lessons_available}`);
        setGauge("ovLessonsGauge", percentOf(o.lessons_viewed, o.lessons_available));
        set("ovLessonsSub", o.lessons_available ? `${plural(o.lessons_available, "lesson")} available` : "No lessons available yet");

        countUp(document.getElementById("ovQuizzes"), o.quizzes_done, n => `${n} of ${o.quizzes_available}`);
        setGauge("ovQuizzesGauge", percentOf(o.quizzes_done, o.quizzes_available));
        set("ovQuizzesSub", o.quiz_attempts
            ? `Average score ${o.average_percent}% over ${plural(o.quiz_attempts, "attempt")}`
            : "No quizzes taken yet");

        countUp(document.getElementById("ovTime"), o.quiz_attempts ? o.seconds : 0, formatDuration);
        set("ovTimeSub", o.quiz_attempts ? "Total time spent answering quizzes" : "Starts counting when you take a quiz");

        set("ovRank", o.rank ? `#${o.rank}` : "Unranked");
        set("ovRankSub", o.rank
            ? `${ordinal(o.rank)} of ${plural(o.ranked_students, "student")} in your school`
            : "Take a quiz to get on the school ranking");
    } catch {
        document.getElementById("overviewGrid").hidden = true;      // a bonus panel: the page works without it
        document.querySelector(".ov-title").hidden = true;
    }
}
loadOverview();

