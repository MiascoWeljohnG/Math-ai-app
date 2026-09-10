function getHeaders() {
    return {
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

// --- Load users ---
async function loadUsers() {
    const res = await fetch(`${API}/admin/users`, { headers: getHeaders() });
    if (!res.ok) return;
    const users = await res.json();
    const tbody = document.querySelector("#usersTable tbody");
    tbody.innerHTML = users.map(u =>
        `<tr><td>${u.username}</td><td>${u.first_name || ""}</td><td>${u.last_name || ""}</td><td>${u.email || ""}</td><td>${u.birthday || ""}</td><td>${u.role}</td><td>${u.created}</td></tr>`
    ).join("");
}
loadUsers();

// --- Load files ---
// Filenames on disk are stored as "<32-char-hash>_<original-name>" (see
// admin_routes.py's upload_documents) so two uploads of the same original
// file never collide on disk. We strip that prefix to compare/display the
// name a human actually recognizes.
function stripHashPrefix(name) {
    return name.replace(/^[a-f0-9]{32}_/i, "");
}

let existingFileNames = new Set(); // normalized (hash-stripped, lowercased) names already in the KB

async function loadFiles() {
    const res = await fetch(`${API}/admin/files`, { headers: getHeaders() });
    if (!res.ok) return;
    const files = await res.json();
    const tbody = document.querySelector("#filesTable tbody");
    const noFiles = document.getElementById("noFiles");

    existingFileNames = new Set(files.map(f => stripHashPrefix(f).toLowerCase()));

    if (files.length === 0) {
        tbody.innerHTML = "";
        noFiles.style.display = "block";
    } else {
        noFiles.style.display = "none";
        tbody.innerHTML = files.map(f => `<tr><td>${stripHashPrefix(f)}</td></tr>`).join("");
    }
    renderChips(); // re-check duplicate status now that the KB list may have changed
}
loadFiles();

// --- File upload with removable chips + duplicate detection ---
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const dropPlaceholder = document.getElementById("dropPlaceholder");
const dupWarning = document.getElementById("dupWarning");
const uploadBtn = document.getElementById("uploadBtn");

let selectedFiles = []; // File objects currently staged for upload

dropZone.addEventListener("click", (e) => {
    if (e.target.closest(".fremove")) return; // don't reopen picker when removing a chip
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
    fileInput.value = ""; // so picking the same file again still fires "change"
});

function addFiles(fileList) {
    for (const file of fileList) {
        if (selectedFiles.some(f => f.name === file.name)) continue; // already staged
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

    if (selectedFiles.length === 0) {
        dropPlaceholder.style.display = "block";
    } else {
        dropPlaceholder.style.display = "none";
        for (const file of selectedFiles) {
            const isDup = existingFileNames.has(file.name.toLowerCase());
            const chip = document.createElement("div");
            chip.className = "file-chip" + (isDup ? " duplicate" : "");
            chip.innerHTML = `<span class="fname" title="${file.name}">${file.name}</span><button class="fremove" type="button" title="Remove">&times;</button>`;
            chip.querySelector(".fremove").addEventListener("click", () => removeFile(file.name));
            dropZone.appendChild(chip);
        }
    }

    const dupCount = selectedFiles.filter(f => existingFileNames.has(f.name.toLowerCase())).length;
    if (dupCount > 0) {
        dupWarning.textContent = `${dupCount} file${dupCount > 1 ? "s" : ""} already ${dupCount > 1 ? "exist" : "exists"} in the knowledge base. Remove ${dupCount > 1 ? "them" : "it"}, or continue to re-ingest anyway.`;
        dupWarning.classList.add("show");
    } else {
        dupWarning.classList.remove("show");
    }

    uploadBtn.disabled = selectedFiles.length === 0;
}

async function uploadFiles() {
    if (!selectedFiles.length) { alert("Select files first."); return; }

    const formData = new FormData();
    for (const file of selectedFiles) {
        formData.append("files", file);
    }

    const statusEl = document.getElementById("uploadStatus");
    statusEl.className = "status";
    statusEl.textContent = "Uploading & ingesting...";
    statusEl.style.display = "block";
    uploadBtn.disabled = true;

    try {
        const res = await fetch(`${API}/admin/upload`, {
            method: "POST",
            headers: getHeaders(),
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        statusEl.className = "status success";
        statusEl.textContent = data.message;
        selectedFiles = [];
        renderChips();
        loadFiles();
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
        uploadBtn.disabled = selectedFiles.length === 0;
    }
}

// --- Clear knowledge base ---
async function clearKB() {
    if (!confirm("This will DELETE all ingested documents. Are you sure?")) return;
    const res = await fetch(`${API}/admin/knowledge-base`, {
        method: "DELETE",
        headers: getHeaders(),
    });
    const data = await res.json();
    alert(data.message);
    loadFiles();
}   