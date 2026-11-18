// Teacher page: Upload Course Material (upload-material.html). Mirrors admin.js's chip-based uploader, posting to /teacher/upload.
// Needs teacher-common.js, utils.js, topic-picker.js and the drop zone markup of that page.
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
    }).catch(err => {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
    });
}

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
