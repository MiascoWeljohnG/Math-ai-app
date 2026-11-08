function getHeaders() {
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

// --- Upload (mirrors admin.js's chip-based uploader, posting to /teacher/upload) ---
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const dropPlaceholder = document.getElementById("dropPlaceholder");
const uploadBtn = document.getElementById("uploadBtn");

let selectedFiles = [];

dropZone.addEventListener("click", (e) => {
    if (e.target.closest(".fremove")) return;
    fileInput.click();
});
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    addFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", (e) => {
    addFiles(e.target.files);
    fileInput.value = "";
});

function addFiles(fileList) {
    for (const file of fileList) {
        if (selectedFiles.some(f => f.name === file.name)) continue;
        selectedFiles.push(file);
    }
    renderChips();
}

function removeFile(name) {
    selectedFiles = selectedFiles.filter(f => f.name !== name);
    renderChips();
}

function renderChips() {
    dropZone.querySelectorAll(".file-chip").forEach(c => c.remove());
    dropPlaceholder.style.display = selectedFiles.length === 0 ? "block" : "none";
    for (const file of selectedFiles) {
        const chip = document.createElement("div");
        chip.className = "file-chip";
        const name = document.createElement("span");
        name.className = "fname";
        name.title = file.name;
        name.textContent = file.name;
        const removeButton = document.createElement("button");
        removeButton.className = "fremove";
        removeButton.type = "button";
        removeButton.title = "Remove";
        removeButton.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
        removeButton.setAttribute("aria-label", "Remove");
        removeButton.addEventListener("click", () => removeFile(file.name));
        chip.append(name, removeButton);
        dropZone.appendChild(chip);
    }
    uploadBtn.disabled = selectedFiles.length === 0;
}

async function uploadFiles() {
    if (!selectedFiles.length) return;
    const statusEl = document.getElementById("uploadStatus");
    statusEl.className = "status";
    statusEl.textContent = "Checking your school's available subjects...";
    statusEl.style.display = "block";

    await withButtonLoading(uploadBtn, async () => {
        const subjects = await loadUploadSubjects(`${API}/teacher/subjects`);
        populateUploadSubjects(document.getElementById("branchSelect"), subjects);
        statusEl.textContent = subjects.length ? "Select a subject, or leave Auto-detect (AI) to classify each file." : "No subjects are configured for this school. Uploading with AI auto-detection.";
        const branch = document.getElementById("branchSelect").value;
        const { message, savedNames } = await uploadWithTopics(`${API}/teacher/upload`, getHeaders(), selectedFiles, branch, subjects);

        statusEl.className = "status success";
        statusEl.textContent = message;
        selectedFiles = selectedFiles.filter(f => !savedNames.has(f.name));   // unfiled files stay selected
        renderChips();
        loadMyFiles();
        loadMaterialOptions();
    }).catch(err => {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
    });
}

// --- Files this teacher uploaded (the server only returns their own) ---
let myFiles = [];
const fileSearch = document.getElementById("fileSearch");
const fileSubjectFilter = document.getElementById("fileSubjectFilter");

// Draws the table from the files that match the search words and the chosen subject. The search and subject choice
// survive the automatic reloads, so a file finishing its indexing doesn't wipe what the teacher typed.
function renderMyFiles() {
    const wanted = fileSubjectFilter.value;
    const labels = new Map();   // one entry per subject whatever its capitals; the first spelling seen is the label
    for (const file of myFiles) {
        const key = file.branch.trim().toLowerCase();
        if (!labels.has(key)) labels.set(key, file.branch);
    }
    const subjects = [...labels.values()].sort((a, b) => a.localeCompare(b));
    fileSubjectFilter.replaceChildren(new Option("All subjects", ""), ...subjects.map(name => new Option(name, name)));
    fileSubjectFilter.value = subjects.includes(wanted) ? wanted : "";   // a subject that no longer has files falls back to All

    const subject = fileSubjectFilter.value.trim().toLowerCase();
    const words = fileSearch.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = myFiles.filter(file => {
        if (subject && file.branch.trim().toLowerCase() !== subject) return false;
        const text = `${file.display_name} ${file.branch}`.toLowerCase();
        return words.every(word => text.includes(word));
    });

    const note = document.getElementById("noFiles");
    note.textContent = myFiles.length ? "No files match your search." : "You haven't uploaded any files yet.";
    note.style.display = shown.length ? "none" : "block";
    document.getElementById("filesTable").style.display = shown.length ? "" : "none";
    document.getElementById("fileFilter").hidden = myFiles.length === 0;
    document.getElementById("fileCount").textContent = myFiles.length && shown.length !== myFiles.length
        ? `Showing ${shown.length} of ${myFiles.length} files.` : "";
    renderMaterialRows(document.querySelector("#filesTable tbody"), shown, false, requestFileDeletion, loadMyFiles);
    // renderMaterialRows only watches the files it was given; keep reloading while ANY file (even a hidden one) is still being read
    scheduleIndexingRefresh(myFiles, loadMyFiles);
}
fileSearch.addEventListener("input", renderMyFiles);
fileSubjectFilter.addEventListener("change", renderMyFiles);

let lastReadyCount = null;
let filesRetryTimer = null;

// A failed load must not look like "no files": say what happened, and try again by itself.
function showFilesProblem(message) {
    const note = document.getElementById("noFiles");
    note.textContent = message;
    note.style.display = "block";
    document.getElementById("filesTable").style.display = "none";
    clearTimeout(filesRetryTimer);
    filesRetryTimer = setTimeout(loadMyFiles, 8000);
}

// A teacher can't delete a file outright: Delete sends a request and the school admin decides.
// Marks the files already asked about (waiting for the admin, or recently kept) so the table can say so.
let deletionRefreshTimer = null;
async function attachDeletionStatus(files) {
    try {
        const res = await fetch(`${API}/file-deletions/mine`, { headers: getHeaders() });
        const status = new Map((res.ok ? await res.json() : []).map(item => [item.filename, item.status]));
        files.forEach(file => { file.deletion_status = status.get(file.filename) || null; });
    } catch (_) { /* the table still works without the notes */ }
    clearTimeout(deletionRefreshTimer);
    if (files.some(file => file.deletion_status === "pending")) deletionRefreshTimer = setTimeout(loadMyFiles, 15000);   // notice the answer
}

async function requestFileDeletion(file) {
    if (!await uiConfirm(`Ask your school admin to delete "${file.display_name}"?\n\nThe file is NOT deleted yet. It stays until the admin approves. Once deleted, the chatbot can no longer use it.`, { title: "Request file deletion", okText: "Continue", danger: true })) return;
    const reason = await uiPrompt("Why should it be deleted? (optional)", "", { title: "Reason", okText: "Send request" });
    if (reason === null) return;
    try {
        const response = await fetch(`${API}/file-deletions`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ filename: file.filename, reason: reason.trim() || null }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || "Couldn't send the request.");
        await uiAlert(result.message, { title: "Request sent" });
    } catch (error) {
        await uiAlert(error.message, { title: "Couldn't send the request" });
    }
    loadMyFiles();
}

async function loadMyFiles() {
    try {
        const res = await fetch(`${API}/teacher/files`, { headers: getHeaders() });
        if (!res.ok) {
            showFilesProblem(`Couldn't load your files (server error ${res.status}). Your uploads are safe. Trying again…`);
            return;
        }
        const files = await res.json();
        await attachDeletionStatus(files);
        myFiles = files;
        renderMyFiles();
        if (typeof loadTeacherOverview === "function") loadTeacherOverview();
        // a file that just finished being read can now be picked for lessons
        const readyCount = files.filter(f => f.index_status === "ready").length;
        if (readyCount !== lastReadyCount) {
            if (lastReadyCount !== null) loadMaterialOptions();
            lastReadyCount = readyCount;
        }
    } catch (err) {
        console.error("Loading the teacher's files failed:", err);
        showFilesProblem("Couldn't reach the server (it may be waking up). Your uploads are safe. Trying again…");
    }
}
loadMyFiles();

// --- Students + progress ---
async function loadStudents() {
    try {
        const res = await fetch(`${API}/teacher/students`, { headers: getHeaders() });
        if (!res.ok) return;
        const students = await res.json();
        const tbody = document.querySelector("#studentsTable tbody");
        const noStudents = document.getElementById("noStudents");

        if (students.length === 0) {
            tbody.replaceChildren();
            noStudents.style.display = "block";
            return;
        }
        noStudents.style.display = "none";
        document.getElementById("studentsHead").replaceChildren(...["Student", "Email", ...students[0].progress.map(p => p.branch), "Mastery"].map(text => {
            const th = document.createElement("th");
            th.textContent = text;
            return th;
        }));

        const rows = students.map(s => {
            const name = formatName(s) || s.username;
            const row = document.createElement("tr");
            const nameCell = document.createElement("td");
            nameCell.textContent = name;
            row.append(nameCell);

            const emailCell = document.createElement("td");
            emailCell.textContent = s.email || "";
            row.append(emailCell);

            for (const item of s.progress) {
                const percent = Math.min(100, Math.max(0, Number(item.percent) || 0));
                const cell = document.createElement("td");
                const track = document.createElement("span");
                track.className = "mini-progress-track";
                const fill = document.createElement("span");
                fill.className = "mini-progress-fill";
                fill.style.width = `${percent}%`;
                track.append(fill);
                cell.append(track, document.createTextNode(`${percent}%`));
                row.append(cell);
            }

            // adaptive levels (rules in backend/adaptive.py): who is stuck, who is ahead
            const masteryCell = document.createElement("td");
            const stuck = document.createElement("span");
            stuck.textContent = `${s.levels.struggling} struggling`;
            if (s.levels.struggling) { stuck.style.color = "var(--danger, #e57373)"; stuck.style.fontWeight = "600"; }
            masteryCell.append(stuck, document.createTextNode(` · ${s.levels.mastered} mastered`));
            row.append(masteryCell);
            return row;
        });
        tbody.replaceChildren(...rows);
    } catch (_) { /* leave table empty on failure */ }
}
loadStudents();

const lessonSubjectSelect = document.getElementById("lessonSubjectSelect");
const lessonListEl = document.getElementById("lessonListEl");
const lessonForm = document.getElementById("lessonForm");
const lessonFormHeading = document.getElementById("lessonFormHeading");
const lessonTitleInput = document.getElementById("lessonTitleInput");
const lessonTitlesInput = document.getElementById("lessonTitlesInput");
const lessonDescriptionInput = document.getElementById("lessonDescriptionInput");
const lessonContentInput = document.getElementById("lessonContentInput");
const lessonStatus = document.getElementById("lessonStatus");
const lessonDialog = document.getElementById("lessonDialog");
const lessonListStatus = document.getElementById("lessonListStatus");   // status line under the lessons list (shown while the dialog is closed)
let lessonBusy = false;   // true while lessons are being written: the dialog can't be closed meanwhile

let activeLessonSubjectId = null;
let editingLessonId = null;

function showLessonStatus(message, kind) {
    const target = lessonDialog.open ? lessonStatus : lessonListStatus;
    target.className = `status ${kind}`;
    target.textContent = message;
}

async function loadLessonSubjects(selectId) {
    try {
        const response = await fetch(`${API}/subjects`, { headers: getHeaders() });
        if (!response.ok) throw new Error("Couldn't load lesson subjects.");
        const subjects = (await response.json()).filter(subject => !subject.is_personal);
        lessonSubjectSelect.replaceChildren(...subjects.map(subject => new Option(subject.name, subject.id)));
        const keep = subjects.find(subject => subject.id === selectId);
        activeLessonSubjectId = keep ? keep.id : (subjects.length ? subjects[0].id : null);
        if (keep) lessonSubjectSelect.value = keep.id;
        if (activeLessonSubjectId === null) {
            lessonListEl.textContent = "No shared subjects are available.";
        } else {
            await loadLessonList();
        }
        await refreshDeletionState();
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

lessonSubjectSelect.addEventListener("change", async () => {
    activeLessonSubjectId = Number(lessonSubjectSelect.value);
    startNewLesson();
    if (materialsLoaded) renderMaterialOptions();   // the file list follows the subject
    await loadLessonList();
    refreshDeletionState();
});

// Lesson title, with the module (file) the AI used to write it underneath, when there is one.
function fillLessonTitle(button, lesson) {
    button.textContent = lesson.title;
    if (!lesson.source_name) return;
    const source = document.createElement("span");
    source.className = "lesson-source";
    source.textContent = `Module: ${lesson.source_name}`;
    source.title = lesson.source_name;
    button.append(source);
}

async function loadLessonList() {
    if (activeLessonSubjectId === null) return;
    try {
        const response = await fetch(
            `${API}/subjects/${activeLessonSubjectId}/lessons`,
            { headers: getHeaders() },
        );
        if (response.status === 404) {   // the admins deleted this subject while the page was open
            showLessonStatus("This subject no longer exists.", "error");
            return loadLessonSubjects();
        }
        if (!response.ok) throw new Error("Couldn't load lessons.");
        const lessons = await response.json();
        const rows = lessons.map(lesson => {
            const row = document.createElement("div");
            row.className = "lesson-row" + (lesson.id === editingLessonId ? " active" : "");
            row.dataset.id = lesson.id;
            const editButton = document.createElement("button");
            editButton.type = "button";
            editButton.className = "lesson-edit";
            fillLessonTitle(editButton, lesson);
            editButton.addEventListener("click", () => editLesson(lesson.id));
            const deleteButton = document.createElement("button");
            deleteButton.type = "button";
            deleteButton.className = "lesson-delete";
            deleteButton.textContent = "Delete";
            deleteButton.addEventListener("click", () => deleteLesson(lesson.id));
            row.append(editButton, deleteButton);
            return row;
        });
        if (rows.length === 0) {
            const empty = document.createElement("p");
            empty.className = "hint";
            empty.textContent = "No lessons yet.";
            rows.push(empty);
        }
        lessonListEl.replaceChildren(...rows);
        await loadDraftList();
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

function markActiveLesson() {
    [lessonListEl, draftListEl].forEach(list => list.querySelectorAll(".lesson-row").forEach(row => row.classList.toggle("active", Number(row.dataset.id) === editingLessonId)));
}

// --- Drafts: lessons the AI wrote stay hidden from students until the teacher approves them ---
const draftPanel = document.getElementById("draftPanel");
const draftListEl = document.getElementById("draftListEl");
let draftLessons = [];

async function loadDraftList() {
    if (activeLessonSubjectId === null) return;
    try {
        const response = await fetch(`${API}/subjects/${activeLessonSubjectId}/lessons/drafts`, { headers: getHeaders() });
        draftLessons = response.ok ? await response.json() : [];
    } catch (_) {
        draftLessons = [];   // the published list still works without it
    }
    renderDraftList();
    if (typeof loadTeacherOverview === "function") loadTeacherOverview();
}

function renderDraftList() {
    draftPanel.hidden = draftLessons.length === 0;
    document.getElementById("draftCount").textContent = draftLessons.length ? String(draftLessons.length) : "";
    draftListEl.replaceChildren(...draftLessons.map(lesson => {
        const row = document.createElement("div");
        row.className = "lesson-row" + (lesson.id === editingLessonId ? " active" : "");
        row.dataset.id = lesson.id;
        const openButton = document.createElement("button");
        openButton.type = "button";
        openButton.className = "lesson-edit";
        fillLessonTitle(openButton, lesson);
        openButton.addEventListener("click", () => editLesson(lesson.id));
        const approveButton = document.createElement("button");
        approveButton.type = "button";
        approveButton.className = "lesson-approve";
        approveButton.textContent = "Approve";
        approveButton.addEventListener("click", () => approveDraft(lesson.id));
        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "lesson-delete";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => deleteLesson(lesson.id));
        row.append(openButton, approveButton, deleteButton);
        return row;
    }));
}

async function postApprove(lessonId) {
    const response = await fetch(`${API}/subjects/${activeLessonSubjectId}/lessons/${lessonId}/approve`, { method: "POST", headers: getHeaders() });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Couldn't approve this lesson.");
}

async function approveDraft(lessonId) {
    try {
        await postApprove(lessonId);
        showLessonStatus("Approved. Students can open this lesson now.", "success");
        await loadLessonList();
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

async function approveAllDrafts() {
    const count = draftLessons.length;
    if (!count) return;
    if (!await uiConfirm(`Approve all ${count} draft lesson${count === 1 ? "" : "s"}?\n\nStudents will be able to open ${count === 1 ? "it" : "them"} straight away.`, { title: "Approve drafts", okText: "Approve all" })) return;
    let approved = 0;
    try {
        for (const lesson of [...draftLessons]) {
            await postApprove(lesson.id);
            approved += 1;
        }
        showLessonStatus(`Approved ${approved} lesson${approved === 1 ? "" : "s"}. Students can open them now.`, "success");
    } catch (error) {
        showLessonStatus(`${error.message} ${approved} of ${count} approved.`, "error");
    }
    await loadLessonList();
}
document.getElementById("approveAllBtn").addEventListener("click", approveAllDrafts);

// --- Right after the AI finishes writing: ask the teacher to accept or reject what it wrote ---
async function deleteLessonQuietly(lessonId) {   // no second "are you sure": the review popup was the question
    const response = await fetch(`${API}/subjects/${activeLessonSubjectId}/lessons/${lessonId}`, { method: "DELETE", headers: getHeaders() });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Couldn't delete this lesson.");
}

function lessonPreview(content) {
    const text = String(content || "").trim();
    return text.length > 700 ? `${text.slice(0, 700).trimEnd()}…` : text;
}

// `lessons` are the drafts the AI just saved (the objects the server returned). Accept publishes them to students,
// Reject deletes them (and their quizzes), and "Review first" / Esc / clicking outside leaves them as drafts.
async function reviewGeneratedLessons(lessons) {
    const drafts = lessons.filter(lesson => lesson && lesson.status === "draft");
    if (!drafts.length) return "none";
    const many = drafts.length > 1;
    const choice = await uiChoice(
        many
            ? `${drafts.length} lessons are ready:\n\n${drafts.map(lesson => `• ${lesson.title}`).join("\n")}\n\nAccept them to show them to students, or reject them to delete them. "Review one by one" keeps them as drafts.`
            : `"${drafts[0].title}" is ready.\n\nAccept it to show it to students, or reject it to delete it. "Review first" keeps it as a draft so you can read and edit it.`,
        {
            title: many ? "Accept these lessons?" : "Accept this lesson?",
            preview: many ? "" : lessonPreview(drafts[0].content),
            choices: [
                { value: "reject", label: many ? "Reject all" : "Reject", kind: "danger" },
                { value: "later", label: many ? "Review one by one" : "Review first", kind: "neutral" },
                { value: "accept", label: many ? "Accept all" : "Accept", kind: "primary" },
            ],
        });
    if (choice !== "accept" && choice !== "reject") return "later";

    const accepting = choice === "accept";
    let done = 0;
    let failure = "";
    for (const lesson of drafts) {
        try {
            await (accepting ? postApprove(lesson.id) : deleteLessonQuietly(lesson.id));
            done += 1;
        } catch (error) {
            failure = error.message;
            break;
        }
    }
    startNewLesson();
    if (lessonDialog.open) lessonDialog.close();   // the editor that showed the new lesson is no longer needed
    const noun = `lesson${done === 1 ? "" : "s"}`;
    if (failure) {
        showLessonStatus(`${failure} ${done} of ${drafts.length} ${accepting ? "accepted" : "rejected"}. The rest are still under "Drafts to review".`, "error");
    } else if (accepting) {
        showLessonStatus(`Accepted ${done} ${noun}. Students can open ${done === 1 ? "it" : "them"} now.`, "success");
    } else {
        showLessonStatus(`Rejected ${done} ${noun}. ${done === 1 ? "It was" : "They were"} deleted.`, "success");
    }
    await loadLessonList();
    return choice;
}

// "+ New lesson": a blank form in the modal.
function openNewLessonDialog() {
    startNewLesson();
    lessonListStatus.textContent = "";
    lessonListStatus.className = "status";
    if (!lessonDialog.open) lessonDialog.showModal();
}

function closeLessonDialog() {
    if (lessonBusy) return;
    if (lessonDialog.open) lessonDialog.close();
}

lessonDialog.addEventListener("cancel", event => { if (lessonBusy) event.preventDefault(); });   // Esc is ignored while the AI is writing
lessonDialog.addEventListener("close", () => startNewLesson());   // however it was closed, the next open starts clean

// --- Lesson content: rendered preview (what students see) / raw text editor ---
// Keeps markdown from eating the \( \) and \[ \] math brackets, same as the student lessons page.
function protectMath(text) {
    if (!text) return "";
    return text
        .replace(/\\\[/g, '\\\\[')         .replace(/\\\]/g, '\\\\]')
        .replace(/\\\(/g, '\\\\(')         .replace(/\\\)/g, '\\\\)');
}

function typesetMath(...elements) {
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise(elements).catch(err => console.log(err));
}

const lessonContentPreview = document.getElementById("lessonContentPreview");

// The module the content on screen was written from. Sent back on Save so it stays correct after a rewrite.
let lessonSourceName = "";
function setLessonSource(name) {
    lessonSourceName = name || "";
    const note = document.getElementById("lessonSourceNote");
    note.hidden = !lessonSourceName;
    note.textContent = lessonSourceName ? `Written from module: ${lessonSourceName}` : "";
}

// The textarea is always the source of truth (Save and Rewrite read it); the preview is just a view of it.
function setContentView(view) {
    const preview = view !== "edit";
    lessonContentPreview.hidden = !preview;
    lessonContentInput.hidden = preview;
    for (const [id, on] of [["contentTabPreview", preview], ["contentTabEdit", !preview]]) {
        const tab = document.getElementById(id);
        tab.classList.toggle("active", on);
        tab.setAttribute("aria-selected", String(on));
    }
    document.getElementById("contentViewHint").textContent = preview
        ? "This is how students will see the lesson. Press Edit text to change the Markdown and LaTeX."
        : "Markdown and LaTeX are supported. Press Preview to see how it will look.";
    if (preview) {
        if (lessonContentInput.value.trim()) {
            renderFinalMessage(lessonContentPreview, protectMath(lessonContentInput.value));
            typesetMath(lessonContentPreview);
        } else {
            lessonContentPreview.textContent = "The lesson content appears here.";
        }
        lessonContentPreview.scrollTop = 0;
    }
}

function startNewLesson() {
    editingLessonId = null;
    markActiveLesson();
    lessonTitleInput.value = "";
    lessonTitlesInput.value = "";
    lessonDescriptionInput.value = "";
    lessonContentInput.value = "";
    setLessonSource("");
    setContentView("preview");
    lessonStatus.textContent = "";
    lessonStatus.className = "status";
    refreshLessonForm();
}

async function editLesson(lessonId) {
    try {
        const response = await fetch(
            `${API}/subjects/${activeLessonSubjectId}/lessons/${lessonId}`,
            { headers: getHeaders() },
        );
        const lesson = await response.json();
        if (!response.ok) throw new Error(lesson.detail || "Couldn't load this lesson.");
        editingLessonId = lesson.id;
        markActiveLesson();
        lessonTitleInput.value = lesson.title;
        lessonDescriptionInput.value = lesson.description || "";
        lessonContentInput.value = lesson.content;
        setLessonSource(lesson.source_name);
        lessonStatus.textContent = "";
        lessonStatus.className = "status";
        refreshLessonForm();
        lessonListStatus.textContent = "";
        lessonListStatus.className = "status";
        if (!lessonDialog.open) lessonDialog.showModal();
        setContentView("preview");
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

async function deleteLesson(lessonId) {
    if (!await uiConfirm("Delete this lesson?", { title: "Delete lesson", okText: "Delete", danger: true })) return;
    try {
        const response = await fetch(
            `${API}/subjects/${activeLessonSubjectId}/lessons/${lessonId}`,
            { method: "DELETE", headers: getHeaders() },
        );
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Couldn't delete this lesson.");
        if (editingLessonId === lessonId) startNewLesson();
        showLessonStatus("Lesson deleted.", "success");
        await loadLessonList();
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

// --- The create-lessons form: optional file, 1-6 lessons, a description the AI writes the content from ---
const sourceUploadRow = document.getElementById("sourceUploadRow");
const sourceLibraryRow = document.getElementById("sourceLibraryRow");
const sourceFileInput = document.getElementById("lessonFileInput");
const materialSelect = document.getElementById("materialSelect");
const pageRangeRow = document.getElementById("pageRangeRow");
const pageStartInput = document.getElementById("pageStartInput");
const pageEndInput = document.getElementById("pageEndInput");

// Drop zone for the lesson source file (same look as Upload Course Material, but one file; the hidden input still holds it).
const lessonDropZone = document.getElementById("lessonDropZone");
const lessonDropPlaceholder = document.getElementById("lessonDropPlaceholder");

function renderLessonFileChip() {
    lessonDropZone.querySelectorAll(".file-chip").forEach(chip => chip.remove());
    const file = sourceFileInput.files[0];
    lessonDropPlaceholder.style.display = file ? "none" : "block";
    if (!file) return;
    const chip = document.createElement("div");
    chip.className = "file-chip";
    const name = document.createElement("span");
    name.className = "fname";
    name.title = file.name;
    name.textContent = file.name;
    const removeButton = document.createElement("button");
    removeButton.className = "fremove";
    removeButton.type = "button";
    removeButton.title = "Remove";
    removeButton.setAttribute("aria-label", "Remove");
    removeButton.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    removeButton.addEventListener("click", () => { sourceFileInput.value = ""; renderLessonFileChip(); });
    chip.append(name, removeButton);
    lessonDropZone.appendChild(chip);
}

function setLessonFile(file) {
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    sourceFileInput.files = transfer.files;
    renderLessonFileChip();
}

lessonDropZone.addEventListener("click", event => {
    if (event.target.closest(".fremove")) return;
    sourceFileInput.click();
});
lessonDropZone.addEventListener("keydown", event => {
    if ((event.key === "Enter" || event.key === " ") && event.target === lessonDropZone) {
        event.preventDefault();
        sourceFileInput.click();
    }
});
lessonDropZone.addEventListener("dragover", event => { event.preventDefault(); lessonDropZone.classList.add("dragover"); });
lessonDropZone.addEventListener("dragleave", () => lessonDropZone.classList.remove("dragover"));
lessonDropZone.addEventListener("drop", event => {
    event.preventDefault();
    lessonDropZone.classList.remove("dragover");
    setLessonFile(event.dataTransfer.files[0]);
});
sourceFileInput.addEventListener("change", renderLessonFileChip);

const generateBtn = document.getElementById("generateBtn");
const regenBtn = document.getElementById("regenBtn");
const saveBtn = document.getElementById("saveBtn");
const cancelBtn = document.getElementById("cancelBtn");
const suggestTitlesBtn = document.getElementById("suggestTitlesBtn");

const selectedCount = () => Number(lessonForm.elements.lessonCount.value) || 1;
const sourceMode = () => lessonForm.elements.lessonSource.value;
const splitLines = text => text.split("\n").map(line => line.trim()).filter(Boolean);

function setCount(n) {
    lessonForm.elements.lessonCount.value = String(Math.min(6, Math.max(1, n)));
}

// Shows only the fields that make sense: creating (1 title or a list of titles) or editing one lesson.
function refreshLessonForm() {
    const editing = editingLessonId !== null;
    const count = editing ? 1 : selectedCount();
    const multi = count > 1;
    lessonFormHeading.textContent = editing ? "Edit lesson" : "Create lessons";
    document.getElementById("sourceLegend").textContent = editing ? "Source file for rewriting (optional)" : "Source file (optional)";
    document.getElementById("countField").hidden = editing;
    document.getElementById("titleSingleField").hidden = multi;
    document.getElementById("titleMultiField").hidden = !multi;
    document.getElementById("lessonContentField").hidden = !editing;
    document.getElementById("withQuizField").hidden = editing;
    generateBtn.hidden = editing;
    saveBtn.hidden = regenBtn.hidden = !editing;   // Cancel is always shown: it just closes the modal
    generateBtn.textContent = count === 1 ? "Generate lesson" : `Generate ${count} lessons`;
    lessonTitlesInput.rows = Math.max(3, count);
    document.getElementById("lessonDescriptionLabel").textContent = multi ? "Description of the lessons" : "Lesson description";
    document.getElementById("lessonDescriptionHint").textContent = editing
        ? "Changing this does not change the content until you press Rewrite content with AI."
        : multi
            ? `Describe what the ${count} lessons should cover together. The AI writes each one.`
            : "The AI writes the full lesson from this.";
    document.getElementById("titleSingleHint").hidden = editing;
    sourceUploadRow.hidden = sourceMode() !== "upload";
    sourceLibraryRow.hidden = sourceMode() !== "library";
    pageRangeRow.hidden = sourceMode() === "none";   // a page range only makes sense with a file
    if (materialsLoaded && sourceMode() === "library") renderMaterialOptions();
}

// Going from 1 lesson to several (or back) carries the typed title over.
lessonForm.addEventListener("change", event => {
    if (event.target.name === "lessonCount") {
        if (selectedCount() > 1 && lessonTitleInput.value.trim() && !lessonTitlesInput.value.trim()) {
            lessonTitlesInput.value = lessonTitleInput.value.trim();
        } else if (selectedCount() === 1 && !lessonTitleInput.value.trim()) {
            lessonTitleInput.value = splitLines(lessonTitlesInput.value)[0] || "";
        }
    }
    refreshLessonForm();
});

// The file the lessons are based on: { file, filename } (one of them, or neither). Throws if "upload"/"choose" is picked but empty.
// The optional page range, as { pageStart, pageEnd } ("" when empty). Throws on a range that can't be right,
// so the teacher hears about it before a slow AI request starts.
function readPageRange() {
    const start = pageStartInput.value.trim(), end = pageEndInput.value.trim();
    if (!start && !end) return { pageStart: "", pageEnd: "" };
    const first = Number(start || 1), last = Number(end || start);
    if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last < 1) {
        throw new Error("Page numbers must be whole numbers starting at 1.");
    }
    if (last < first) throw new Error(`The last page (${last}) is before the first page (${first}).`);
    return { pageStart: String(first), pageEnd: String(last) };
}

function readSource() {
    if (sourceMode() === "upload") {
        const file = sourceFileInput.files[0];
        if (!file) throw new Error("Choose a file to upload, or pick \"No file\".");
        return { file, filename: "", ...readPageRange() };
    }
    if (sourceMode() === "library") {
        if (!materialSelect.value) throw new Error("Choose one of your uploaded files, or pick \"No file\".");
        return { file: null, filename: materialSelect.value, ...readPageRange() };
    }
    return { file: null, filename: "", pageStart: "", pageEnd: "" };
}

// --- "View file contents": read the source file to see which pages the lessons should use ---
// A PDF opens in the browser's own PDF viewer (page numbers = the "From page / To page" numbers). Slides, Word
// and text files are shown as text, slide by slide, with buttons that fill in the page range.
const filePreviewDialog = document.getElementById("filePreviewDialog");
const filePreviewTitle = document.getElementById("filePreviewTitle");
const filePreviewHint = document.getElementById("filePreviewHint");
const filePreviewBody = document.getElementById("filePreviewBody");
let filePreviewUrl = null;
let filePreviewRun = 0;   // a slow file must not paint over a newer one

function closeFilePreview() { if (filePreviewDialog.open) filePreviewDialog.close(); }

filePreviewDialog.addEventListener("close", () => {
    filePreviewRun++;
    if (filePreviewUrl) { URL.revokeObjectURL(filePreviewUrl); filePreviewUrl = null; }
    filePreviewBody.replaceChildren();
});

function showFilePreviewNote(message) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = message;
    filePreviewBody.replaceChildren(note);
}

async function fetchJson(url) {
    const response = await fetch(url, { headers: getHeaders() });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Couldn't open this file.");
    return result;
}

function renderPdfPreview(blob) {
    filePreviewUrl = URL.createObjectURL(blob);
    const frame = document.createElement("iframe");
    frame.className = "fp-frame";
    frame.title = filePreviewTitle.textContent;
    frame.src = filePreviewUrl;
    filePreviewBody.replaceChildren(frame);
    filePreviewHint.textContent = "Scroll to find the pages you need, then type their numbers under \"Pages to use\" (page 1 is the first page of the file).";
}

function renderPagesPreview(data) {
    const setPage = (input, number) => { input.value = String(number); input.dispatchEvent(new Event("input", { bubbles: true })); };
    filePreviewHint.textContent = data.paged
        ? "Each slide shows the text the AI will read. Use the buttons to set the first and last slide for the lessons."
        : "This file type has no page numbers, so the whole file is used and \"Pages to use\" can't be applied. Use a PDF or PowerPoint file to pick pages.";
    filePreviewBody.replaceChildren(...data.pages.map(page => {
        const box = document.createElement("div");
        box.className = "fp-page";
        const head = document.createElement("div");
        head.className = "fp-page-head";
        const title = document.createElement("h3");
        title.textContent = page.number ? `Slide ${page.number}` : "Contents";
        head.appendChild(title);
        if (data.paged && page.number) {
            const pick = document.createElement("div");
            pick.className = "fp-pick";
            [["From here", pageStartInput], ["To here", pageEndInput]].forEach(([label, input]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-secondary btn-sm";
                button.textContent = label;
                button.addEventListener("click", () => {
                    setPage(input, page.number);
                    filePreviewHint.textContent = `Pages to use: ${pageStartInput.value || "…"} to ${pageEndInput.value || "…"}. You can keep browsing or press Close.`;
                });
                pick.appendChild(button);
            });
            head.appendChild(pick);
        }
        const body = document.createElement("pre");
        body.textContent = page.text || "(no readable text on this slide)";   // textContent: file text can't inject HTML
        box.append(head, body);
        return box;
    }));
}

async function viewSourceFile() {
    let file = null, filename = "", name = "";
    if (sourceMode() === "upload") {
        file = sourceFileInput.files[0];
        if (!file) return showLessonStatus("Choose a file first, then press View file contents.", "error");
        name = file.name;
    } else if (sourceMode() === "library") {
        filename = materialSelect.value;
        if (!filename) return showLessonStatus("Choose an uploaded file first, then press View file contents.", "error");
        name = materialSelect.selectedOptions[0] ? materialSelect.selectedOptions[0].textContent.trim() : filename;
    } else {
        return;
    }
    const run = ++filePreviewRun;
    filePreviewTitle.textContent = name;
    filePreviewHint.textContent = "";
    showFilePreviewNote("Opening the file…");
    if (!filePreviewDialog.open) filePreviewDialog.showModal();
    try {
        const isPdf = (file ? file.name : filename).toLowerCase().endsWith(".pdf");
        if (isPdf) {
            let blob = file;
            if (!blob) {
                const response = await fetch(`${API}/materials/${encodeURIComponent(filename)}/file`, { headers: getHeaders() });
                if (!response.ok) throw new Error("Couldn't open this file.");
                blob = await response.blob();
            }
            if (run !== filePreviewRun) return;
            renderPdfPreview(new Blob([blob], { type: "application/pdf" }));
        } else {
            let data;
            if (file) {
                const form = new FormData();
                form.append("file", file);
                data = await postForm(`${API}/teacher/preview-file`, form);
            } else {
                data = await fetchJson(`${API}/materials/${encodeURIComponent(filename)}/preview`);
            }
            if (run !== filePreviewRun) return;
            renderPagesPreview(data);
        }
    } catch (error) {
        if (run === filePreviewRun) showFilePreviewNote(error.message);
    }
}

// A file picked with "Upload a file" is first saved to Your Uploaded Files (under the selected subject) when the box is
// ticked, and the lessons are then written from that saved copy. It is saved once per form, however many times the
// teacher presses Suggest/Generate. Without the tick, the file is only read to write the lessons, as before.
let lessonUpload = null;   // { file, promise }: the save in progress or done for the chosen file (a double click must not upload twice)

async function saveLessonFile(file) {
    showLessonStatus("Saving the file to Your Uploaded Files…", "info");
    const hint = ` Untick "Also save this file" to use it without saving.`;
    let result;
    try {
        result = await postUpload(`${API}/teacher/upload`, getHeaders(), [file], activeSubjectName(), null);
    } catch (error) {
        throw new Error(`The file couldn't be saved: ${error.message}${hint}`);
    }
    const saved = result.uploaded && result.uploaded[0];
    if (!saved || !saved.stored_name) throw new Error(`The file couldn't be saved. ${result.message || ""}${hint}`.replace("  ", " "));
    loadMyFiles();
    loadMaterialOptions();
    return saved.stored_name;
}

async function resolveSource() {
    const source = readSource();
    if (sourceMode() !== "upload" || !source.file || !document.getElementById("saveLessonFile").checked) return source;
    if (!lessonUpload || lessonUpload.file !== source.file) lessonUpload = { file: source.file, promise: saveLessonFile(source.file) };
    let stored;
    try {
        stored = await lessonUpload.promise;
    } catch (error) {
        lessonUpload = null;   // a failed save is tried again next time
        throw error;
    }
    return { file: null, filename: stored, pageStart: source.pageStart, pageEnd: source.pageEnd };
}

function lessonRequest(source, fields) {
    const form = new FormData();
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    if (source.file) form.append("file", source.file);
    if (source.filename) form.append("filename", source.filename);
    if (source.pageStart) form.append("page_start", source.pageStart);
    if (source.pageEnd) form.append("page_end", source.pageEnd);
    return form;
}

const lessonsUrl = (path = "") => `${API}/subjects/${activeLessonSubjectId}/lessons${path}`;

// Asks the AI for however many titles are still missing and returns typed + suggested titles, in order.
async function completeTitles(count, typed, description, source) {
    if (typed.length >= count) return typed.slice(0, count);
    const { titles } = await postForm(lessonsUrl("/plan"),
        lessonRequest(source, { count: count - typed.length, description, existing: typed.join("\n") }));
    return [...typed, ...titles];
}

function typedTitles() {
    return selectedCount() > 1 ? splitLines(lessonTitlesInput.value) : splitLines(lessonTitleInput.value).slice(0, 1);
}

async function suggestLessonFromMaterial() {
    if (activeLessonSubjectId === null) return showLessonStatus("Choose a subject first.", "error");
    const filename = materialSelect.value;
    if (!filename) return showLessonStatus("Choose an uploaded file first.", "error");
    await withButtonLoading(document.getElementById("suggestFromMaterialBtn"), async () => {
        showLessonStatus("Reading the file and suggesting a lesson… this can take a minute.", "info");
        const form = new FormData();
        form.append("filename", filename);
        const suggestion = await postForm(lessonsUrl("/suggest-from-file"), form);
        editingLessonId = null;
        lessonTitleInput.value = suggestion.title;
        lessonDescriptionInput.value = suggestion.description;
        lessonContentInput.value = suggestion.content;
        refreshLessonForm();
        document.getElementById("lessonContentField").hidden = false;
        setContentView("preview");
        showLessonStatus("Suggested from the uploaded file. Edit the fields; nothing has been saved.", "success");
    }).catch(error => showLessonStatus(error.message, "error"));
}

async function suggestTitles() {
    if (activeLessonSubjectId === null) return showLessonStatus("Choose a subject first.", "error");
    let source;
    try { source = await resolveSource(); } catch (error) { return showLessonStatus(error.message, "error"); }
    await withButtonLoading(suggestTitlesBtn, async () => {
        showLessonStatus("Planning the lessons… this can take a minute.", "info");
        const titles = await completeTitles(selectedCount(), typedTitles(), lessonDescriptionInput.value.trim(), source);
        lessonTitlesInput.value = titles.join("\n");
        showLessonStatus("Edit the titles if you like, then press Generate.", "success");
    }).catch(error => showLessonStatus(error.message, "error"));
}

// One request per lesson so a slow model never hits a timeout. Titles that were not written yet go back into
// the form when something fails, so pressing Generate again carries on.
async function generateLessons() {
    if (activeLessonSubjectId === null) return showLessonStatus("Choose a subject first.", "error");
    let source;
    try { source = await resolveSource(); } catch (error) { return showLessonStatus(error.message, "error"); }

    const count = selectedCount();
    const description = lessonDescriptionInput.value.trim();
    const withQuiz = document.getElementById("withQuizInput").checked;
    const typed = typedTitles();
    let titles = typed, saved = [], quizFailures = 0, finished = false;

    lessonSubjectSelect.disabled = true;
    lessonBusy = true;
    await withButtonLoading(generateBtn, async () => {
        if (typed.length < count) {
            showLessonStatus(`Planning ${count === 1 ? "the lesson" : `${count} lessons`}… this can take a minute.`, "info");
            titles = await completeTitles(count, typed, description, source);
        }
        for (let i = 0; i < titles.length; i++) {
            showLessonStatus(`Writing lesson ${i + 1} of ${titles.length}: ${titles[i]}…`, "info");
            const lesson = await postForm(lessonsUrl("/compose"),
                lessonRequest(source, { title: titles[i], description, series: titles.join("\n"), save: "true" }));
            saved.push(lesson);
            await loadLessonList();
            if (withQuiz) {
                showLessonStatus(`Writing the quiz for lesson ${i + 1} of ${titles.length}: ${titles[i]}…`, "info");
                try { await lessonPost(`${lesson.id}/quiz/generate`); } catch (_) { quizFailures++; }
            }
        }
        const quizNote = quizFailures ? ` ${quizFailures} quiz(zes) failed; open those lessons and press Generate quiz.` : "";
        if (saved.length === 1) {
            await editLesson(saved[0].id);   // open it so the teacher can read what the AI wrote
            showLessonStatus(`Lesson saved as a draft. Read it here and edit anything you like, then press Approve under "Drafts to review" so students can see it.${quizNote}`, quizFailures ? "error" : "success");
        } else {
            startNewLesson();
            lessonDialog.close();   // not closeLessonDialog(): lessonBusy is still set until the finally below
            showLessonStatus(`Done. ${saved.length} lessons saved as drafts.${quizNote} Review them under "Drafts to review" and press Approve so students can see them.`, quizFailures ? "error" : "success");
        }
        loadStudents();
        finished = true;
    }).catch(error => {
        const pending = titles.slice(saved.length);
        if (pending.length > 1) { setCount(pending.length); lessonTitlesInput.value = pending.join("\n"); }
        else if (pending.length === 1) { setCount(1); lessonTitleInput.value = pending[0]; }
        refreshLessonForm();
        const progress = saved.length ? ` ${saved.length} of ${titles.length} lesson(s) were saved before it stopped. The rest are still in the form, so you can press Generate again.` : "";
        showLessonStatus(`${error.message}${progress}`, "error");
    }).finally(() => {
        lessonBusy = false;
        lessonSubjectSelect.disabled = false;
    });

    // Everything (lessons and quizzes) is written: now the teacher decides. Only after a clean run; if it stopped
    // halfway, the drafts that were saved wait under "Drafts to review" as before.
    if (finished) await reviewGeneratedLessons(saved);
}

// Edit mode: write new content from the title, description and file. Nothing is saved until Save changes.
async function regenerateContent() {
    const title = lessonTitleInput.value.trim();
    if (!title) return showLessonStatus("A lesson title is required.", "error");
    let source;
    try { source = await resolveSource(); } catch (error) { return showLessonStatus(error.message, "error"); }
    if (lessonContentInput.value.trim() && !await uiConfirm(
        "Replace the current content with new AI-written content?\n\nNothing is saved until you press Save changes.",
        { title: "Rewrite content", okText: "Rewrite" })) return;
    await withButtonLoading(regenBtn, async () => {
        showLessonStatus("Writing the lesson… this can take a minute.", "info");
        const result = await postForm(lessonsUrl("/compose"),
            lessonRequest(source, { title, description: lessonDescriptionInput.value.trim(), save: "false" }));
        lessonContentInput.value = result.content;
        setLessonSource(result.source_name);
        setContentView("preview");
        showLessonStatus("New content is ready. Read it, then press Save changes.", "success");
    }).catch(error => showLessonStatus(error.message, "error"));
}

// Edit mode: save the title, description and content as they are in the form.
async function saveLesson() {
    if (activeLessonSubjectId === null || editingLessonId === null) return;
    const title = lessonTitleInput.value.trim();
    const content = lessonContentInput.value.trim();
    if (!title) return showLessonStatus("A lesson title is required.", "error");
    if (!content) return showLessonStatus("The content is empty. Press Rewrite content with AI first.", "error");
    await withButtonLoading(saveBtn, async () => {
        const response = await fetch(lessonsUrl(`/${editingLessonId}`), {
            method: "PUT",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ title, content, description: lessonDescriptionInput.value.trim(), source_name: lessonSourceName }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Couldn't save this lesson.");
        startNewLesson();
        lessonDialog.close();
        showLessonStatus("Lesson saved.", "success");
        await loadLessonList();
    }).catch(error => showLessonStatus(error.message, "error"));
}

loadLessonSubjects();

async function lessonPost(path, body) {
    const response = await fetch(`${API}/subjects/${activeLessonSubjectId}/lessons/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getHeaders() },
        body: body ? JSON.stringify(body) : undefined,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Request failed.");
    return result;
}


// --- Delete a subject: needs every admin's approval ---
const deleteSubjectBtn = document.getElementById("deleteSubjectBtn");
const deletionNote = document.getElementById("deletionNote");
let pendingDeletions = [];

async function refreshDeletionState() {
    let latest = pendingDeletions;
    try {
        const response = await fetch(`${API}/subject-deletions`, { headers: getHeaders() });
        if (response.ok) latest = await response.json();
    } catch (_) { /* keep what we had */ }
    const before = pendingDeletions;
    pendingDeletions = latest;

    const pending = pendingDeletions.find(request => request.subject_id === activeLessonSubjectId);
    deleteSubjectBtn.disabled = activeLessonSubjectId === null || Boolean(pending);
    deletionNote.textContent = pending
        ? `Deletion requested by ${pending.requested_by}. Waiting for admin approval (${pending.approved_by.length} of ${pending.admins_total} approved).`
        : "";

    // A request that was pending and now isn't was decided by the admins: reload the subjects and say how it went.
    const decided = before.filter(request => !pendingDeletions.some(p => p.id === request.id));
    if (decided.length) {
        await loadLessonSubjects(activeLessonSubjectId);
        const stillThere = id => [...lessonSubjectSelect.options].some(option => Number(option.value) === id);
        showLessonStatus(
            decided.map(r => stillThere(r.subject_id)
                ? `An admin rejected the request to delete "${r.subject_name}". It stays.`
                : `All admins approved. "${r.subject_name}" was deleted.`).join(" "),
            "success",
        );
        loadStudents();
    }
}

// --- New subject: type a name, or upload a file and let the AI fill in the details and write the lessons ---
const subjectDialog = document.getElementById("subjectDialog");
const subjectFileInput = document.getElementById("subjectFileInput");
const subjectNameInput = document.getElementById("subjectNameInput");
const subjectDescInput = document.getElementById("subjectDescInput");
const subjectLessonsInput = document.getElementById("subjectLessonsInput");
const subjectQuizInput = document.getElementById("subjectQuizInput");
const subjectCreateBtn = document.getElementById("subjectCreateBtn");
const subjectDialogStatus = document.getElementById("subjectDialogStatus");
let suggestRun = 0;   // lets a slow answer be ignored if the file changed or the dialog was closed meanwhile

function showSubjectStatus(message, kind) {
    subjectDialogStatus.className = `status ${kind}`;
    subjectDialogStatus.textContent = message;
}

async function postForm(url, form) {
    const response = await fetch(url, { method: "POST", headers: getHeaders(), body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Request failed.");
    return result;
}

function addSubject() {
    subjectFileInput.value = subjectNameInput.value = subjectDescInput.value = "";
    subjectCreateBtn.disabled = false;
    showSubjectStatus("", "");
    subjectDialog.showModal();
    subjectNameInput.focus();
}

subjectDialog.addEventListener("close", () => { suggestRun++; });

// Choosing a file asks the AI for a name and description. They stay editable.
subjectFileInput.addEventListener("change", async () => {
    const run = ++suggestRun;
    const file = subjectFileInput.files[0];
    if (!file) { subjectCreateBtn.disabled = false; return; }
    subjectCreateBtn.disabled = true;
    showSubjectStatus("Reading the file to suggest a name and description… this can take a minute.", "info");
    try {
        const form = new FormData();
        form.append("file", file);
        const suggestion = await postForm(`${API}/subjects/suggest`, form);
        if (run !== suggestRun) return;
        subjectNameInput.value = suggestion.name;
        subjectDescInput.value = suggestion.description;
        showSubjectStatus("Filled in from the file. Edit anything you like, then press Create subject.", "success");
    } catch (error) {
        if (run === suggestRun) showSubjectStatus(`${error.message} You can still type the name yourself.`, "error");
    } finally {
        if (run === suggestRun) subjectCreateBtn.disabled = false;
    }
});

async function createSubject() {
    const name = subjectNameInput.value.trim();
    if (!name) return showSubjectStatus("Enter a subject name.", "error");
    const file = subjectFileInput.files[0];
    const writeLessons = Boolean(file) && subjectLessonsInput.checked;
    const withQuiz = subjectQuizInput.checked;
    
    let subject;
    await withButtonLoading(subjectCreateBtn, async () => {
        try {
            subject = await postJson(`${API}/subjects/shared`, { name, description: subjectDescInput.value.trim() || null });
        } catch (error) {
            showSubjectStatus(error.message, "error");   // e.g. 'A subject called "Algebra" already exists'
            throw error;
        }
    }).catch(() => { return; });
    
    if (!subject) return;

    subjectDialog.close();
    await loadLessonSubjects(subject.id);
    startNewLesson();
    if (!writeLessons) return showLessonStatus(`Subject "${subject.name}" created. Add its first lesson with + New lesson.`, "success");
    await writeLessonsFromFile(subject, file, withQuiz);
}

// Same two-step flow as the rest of the page: plan the titles, then one request per lesson.
// force=true skips the "is this file about this subject?" check, because the subject came from this very file.
async function writeLessonsFromFile(subject, file, withQuiz) {
    lessonSubjectSelect.disabled = true;
    let written = 0, total = 0, quizFailures = 0;
    const savedLessons = [];
    try {
        if (activeLessonSubjectId !== subject.id) throw new Error("Couldn't open the new subject.");
        showLessonStatus(`Subject "${subject.name}" created. Planning lessons from ${file.name}… this can take a minute.`, "info");
        const plan = new FormData();
        plan.append("file", file);
        plan.append("count", "5");
        const { titles } = await postForm(`${API}/subjects/${subject.id}/lessons/outline-from-file`, plan);
        total = titles.length;
        for (let i = 0; i < total; i++) {
            showLessonStatus(`Writing lesson ${i + 1} of ${total}: ${titles[i]}…`, "info");
            const form = new FormData();
            form.append("file", file);
            form.append("topic", titles[i]);
            form.append("force", "true");
            const lesson = await postForm(`${API}/subjects/${subject.id}/lessons/generate-from-file`, form);
            written++;
            savedLessons.push(lesson);
            await loadLessonList();
            if (withQuiz) {
                showLessonStatus(`Writing the quiz for lesson ${i + 1} of ${total}: ${titles[i]}…`, "info");
                try { await lessonPost(`${lesson.id}/quiz/generate`); } catch (_) { quizFailures++; }
            }
        }
        const quizNote = quizFailures ? ` ${quizFailures} quiz(zes) failed; open those lessons and press Generate quiz.` : "";
        showLessonStatus(`Done. ${written} lesson(s) saved to "${subject.name}" as drafts.${quizNote} Review them under "Drafts to review" and press Approve so students can see them.`, quizFailures ? "error" : "success");
        loadStudents();
        await reviewGeneratedLessons(savedLessons);
    } catch (error) {
        showLessonStatus(`${error.message} The subject "${subject.name}" was created; ${written} of ${total} lesson(s) were saved before it stopped.`, "error");
    } finally {
        lessonSubjectSelect.disabled = false;
    }
}

async function requestSubjectDeletion() {
    if (activeLessonSubjectId === null) return showLessonStatus("Choose a subject first.", "error");
    const name = lessonSubjectSelect.selectedOptions[0].textContent;
    if (!await uiConfirm(`Ask the admins to delete "${name}" with all of its lessons and quizzes?\n\nNothing is deleted until EVERY admin approves.`, { title: "Request deletion", okText: "Continue", danger: true })) return;
    const reason = await uiPrompt("Why should it be deleted? (optional)", "", { title: "Reason", okText: "Send request" });
    if (reason === null) return;
    try {
        const response = await fetch(`${API}/subject-deletions`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ subject_id: activeLessonSubjectId, reason: reason.trim() || null }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Couldn't send the request.");
        showLessonStatus(result.message, "success");
        if (result.status === "approved") await loadLessonSubjects();
        else await refreshDeletionState();
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

window.addEventListener("focus", refreshDeletionState);
setInterval(refreshDeletionState, 30000);

// --- The "Choose an uploaded file" list ---
let allMaterials = [];
let materialsLoaded = false;
const materialSearch = document.getElementById("materialSearch");
const materialSubjectOnly = document.getElementById("materialSubjectOnly");
const materialCount = document.getElementById("materialCount");
const normalized = text => String(text || "").trim().toLowerCase();

// The name of the subject picked at the top of the lessons section: uploaded files are filed under a subject's name.
function activeSubjectName() {
    const option = lessonSubjectSelect.selectedOptions && lessonSubjectSelect.selectedOptions[0];
    return option ? option.textContent.trim() : "";
}

// Shows the uploaded files that match the search words and, when ticked, belong to the selected subject.
function renderMaterialOptions() {
    const chosen = materialSelect.value;
    const subject = normalized(activeSubjectName());
    const onlySubject = Boolean(materialSubjectOnly.checked && subject);
    const words = normalized(materialSearch.value).split(/\s+/).filter(Boolean);
    const matches = allMaterials.filter(file => {
        if (onlySubject && normalized(file.branch) !== subject) return false;
        const text = normalized(`${file.display_name} ${file.branch}`);
        return words.every(word => text.includes(word));
    });
    const placeholder = !allMaterials.length ? "No uploaded files yet"
        : matches.length ? "Choose an uploaded file…" : "No files match";
    materialSelect.replaceChildren(
        new Option(placeholder, ""),
        ...matches.map(file => new Option(onlySubject ? file.display_name : `${file.display_name} (${file.branch})`, file.filename)),
    );
    if (matches.some(file => file.filename === chosen)) materialSelect.value = chosen;
    document.getElementById("materialSubjectOnlyLabel").textContent = subject
        ? `Only files in ${activeSubjectName()}` : "Only this subject's files";
    if (!allMaterials.length) materialCount.textContent = "";
    else if (matches.length) materialCount.textContent = `Showing ${matches.length} of ${allMaterials.length} file${allMaterials.length === 1 ? "" : "s"}.`;
    else if (onlySubject && !words.length) materialCount.textContent = `No files are filed under ${activeSubjectName()} yet. Untick the box above to see all ${allMaterials.length}, or upload one.`;
    else materialCount.textContent = `No files match. ${allMaterials.length} in total.`;
}
materialSearch.addEventListener("input", renderMaterialOptions);
materialSubjectOnly.addEventListener("change", renderMaterialOptions);

async function loadMaterialOptions() {
    try {
        const response = await fetch(`${API}/materials`, { headers: getHeaders() });
        if (!response.ok) return;
        allMaterials = await response.json();
        materialsLoaded = true;
        renderMaterialOptions();
    } catch (_) { /* leave the list as it was */ }
}
loadMaterialOptions();

async function initUploadSubjects() {
    const branchSelect = document.getElementById("branchSelect");
    if (!branchSelect) return;
    try {
        const subjects = await loadUploadSubjects(`${API}/teacher/subjects`);
        populateUploadSubjects(branchSelect, subjects);
    } catch (_) {
        // Fall back gracefully to existing select state if fetch fails
    }
}
initUploadSubjects();

async function postJson(url, body) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getHeaders() },
        body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Request failed.");
    return result;
}

refreshLessonForm();
