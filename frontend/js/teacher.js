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
    statusEl.textContent = "Uploading & ingesting...";
    statusEl.style.display = "block";

    await withButtonLoading(uploadBtn, async () => {
        const branch = document.getElementById("branchSelect").value;
        const { message, savedNames } = await uploadWithTopics(`${API}/teacher/upload`, getHeaders(), selectedFiles, branch);

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
async function loadMyFiles() {
    try {
        const res = await fetch(`${API}/teacher/files`, { headers: getHeaders() });
        if (!res.ok) return;
        const files = await res.json();
        document.getElementById("noFiles").style.display = files.length ? "none" : "block";
        document.getElementById("filesTable").style.display = files.length ? "" : "none";
        renderMaterialRows(document.querySelector("#filesTable tbody"), files, false);
    } catch (_) { /* leave table empty on failure */ }
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

let activeLessonSubjectId = null;
let editingLessonId = null;

function showLessonStatus(message, kind) {
    lessonStatus.className = `status ${kind}`;
    lessonStatus.textContent = message;
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
    await loadLessonList();
    refreshDeletionState();
});

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
            editButton.textContent = lesson.title;
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
    } catch (error) {
        showLessonStatus(error.message, "error");
    }
}

function markActiveLesson() {
    lessonListEl.querySelectorAll(".lesson-row").forEach(row => row.classList.toggle("active", Number(row.dataset.id) === editingLessonId));
}

function startNewLesson() {
    editingLessonId = null;
    markActiveLesson();
    lessonTitleInput.value = "";
    lessonTitlesInput.value = "";
    lessonDescriptionInput.value = "";
    lessonContentInput.value = "";
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
        lessonStatus.textContent = "";
        lessonStatus.className = "status";
        refreshLessonForm();
        lessonForm.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
    saveBtn.hidden = regenBtn.hidden = cancelBtn.hidden = !editing;
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
function readSource() {
    if (sourceMode() === "upload") {
        const file = sourceFileInput.files[0];
        if (!file) throw new Error("Choose a file to upload, or pick \"No file\".");
        return { file, filename: "" };
    }
    if (sourceMode() === "library") {
        if (!materialSelect.value) throw new Error("Choose one of your uploaded files, or pick \"No file\".");
        return { file: null, filename: materialSelect.value };
    }
    return { file: null, filename: "" };
}

function lessonRequest(source, fields) {
    const form = new FormData();
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    if (source.file) form.append("file", source.file);
    if (source.filename) form.append("filename", source.filename);
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
        showLessonStatus("Suggested from the uploaded file. Edit the fields; nothing has been saved.", "success");
    }).catch(error => showLessonStatus(error.message, "error"));
}

async function suggestTitles() {
    if (activeLessonSubjectId === null) return showLessonStatus("Choose a subject first.", "error");
    let source;
    try { source = readSource(); } catch (error) { return showLessonStatus(error.message, "error"); }
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
    try { source = readSource(); } catch (error) { return showLessonStatus(error.message, "error"); }

    const count = selectedCount();
    const description = lessonDescriptionInput.value.trim();
    const withQuiz = document.getElementById("withQuizInput").checked;
    const typed = typedTitles();
    let titles = typed, saved = [], quizFailures = 0;

    lessonSubjectSelect.disabled = true;
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
            showLessonStatus(`Lesson saved. Read it below and edit anything you like.${quizNote}`, quizFailures ? "error" : "success");
        } else {
            startNewLesson();
            showLessonStatus(`Done. ${saved.length} lessons saved.${quizNote} Review them before students see them.`, quizFailures ? "error" : "success");
        }
        loadStudents();
    }).catch(error => {
        const pending = titles.slice(saved.length);
        if (pending.length > 1) { setCount(pending.length); lessonTitlesInput.value = pending.join("\n"); }
        else if (pending.length === 1) { setCount(1); lessonTitleInput.value = pending[0]; }
        refreshLessonForm();
        const progress = saved.length ? ` ${saved.length} of ${titles.length} lesson(s) were saved before it stopped. The rest are still in the form, so you can press Generate again.` : "";
        showLessonStatus(`${error.message}${progress}`, "error");
    }).finally(() => {
        lessonSubjectSelect.disabled = false;
    });
}

// Edit mode: write new content from the title, description and file. Nothing is saved until Save changes.
async function regenerateContent() {
    const title = lessonTitleInput.value.trim();
    if (!title) return showLessonStatus("A lesson title is required.", "error");
    let source;
    try { source = readSource(); } catch (error) { return showLessonStatus(error.message, "error"); }
    if (lessonContentInput.value.trim() && !await uiConfirm(
        "Replace the current content with new AI-written content?\n\nNothing is saved until you press Save changes.",
        { title: "Rewrite content", okText: "Rewrite" })) return;
    await withButtonLoading(regenBtn, async () => {
        showLessonStatus("Writing the lesson… this can take a minute.", "info");
        const result = await postForm(lessonsUrl("/compose"),
            lessonRequest(source, { title, description: lessonDescriptionInput.value.trim(), save: "false" }));
        lessonContentInput.value = result.content;
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
            body: JSON.stringify({ title, content, description: lessonDescriptionInput.value.trim() }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Couldn't save this lesson.");
        startNewLesson();
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
    if (!writeLessons) return showLessonStatus(`Subject "${subject.name}" created. Add its first lesson below.`, "success");
    await writeLessonsFromFile(subject, file, withQuiz);
}

// Same two-step flow as the rest of the page: plan the titles, then one request per lesson.
// force=true skips the "is this file about this subject?" check, because the subject came from this very file.
async function writeLessonsFromFile(subject, file, withQuiz) {
    lessonSubjectSelect.disabled = true;
    let written = 0, total = 0, quizFailures = 0;
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
            await loadLessonList();
            if (withQuiz) {
                showLessonStatus(`Writing the quiz for lesson ${i + 1} of ${total}: ${titles[i]}…`, "info");
                try { await lessonPost(`${lesson.id}/quiz/generate`); } catch (_) { quizFailures++; }
            }
        }
        const quizNote = quizFailures ? ` ${quizFailures} quiz(zes) failed; open those lessons and press Generate quiz.` : "";
        showLessonStatus(`Done. ${written} lesson(s) saved to "${subject.name}".${quizNote} Review them before students see them.`, quizFailures ? "error" : "success");
        loadStudents();
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
async function loadMaterialOptions() {
    try {
        const response = await fetch(`${API}/materials`, { headers: getHeaders() });
        if (!response.ok) return;
        const files = await response.json();
        const chosen = materialSelect.value;
        materialSelect.replaceChildren(
            new Option(files.length ? "Choose an uploaded file…" : "No uploaded files yet", ""),
            ...files.map(file => new Option(`${file.display_name} (${file.branch})`, file.filename)),
        );
        if (files.some(file => file.filename === chosen)) materialSelect.value = chosen;
    } catch (_) { /* leave the list as it was */ }
}
loadMaterialOptions();

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
