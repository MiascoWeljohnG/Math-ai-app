// Teacher page: Your Uploaded Files (teacher-files.html). The server only returns the files this teacher uploaded.
// Needs teacher-common.js, material-table.js and the files table markup of that page.
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
            if (lastReadyCount !== null && typeof loadMaterialOptions === "function") loadMaterialOptions();
            lastReadyCount = readyCount;
        }
    } catch (err) {
        console.error("Loading the teacher's files failed:", err);
        showFilesProblem("Couldn't reach the server (it may be waking up). Your uploads are safe. Trying again…");
    }
}
loadMyFiles();

