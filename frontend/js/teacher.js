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
        chip.innerHTML = `<span class="fname" title="${file.name}">${file.name}</span><button class="fremove" type="button" title="Remove">&times;</button>`;
        chip.querySelector(".fremove").addEventListener("click", () => removeFile(file.name));
        dropZone.appendChild(chip);
    }
    uploadBtn.disabled = selectedFiles.length === 0;
}

async function uploadFiles() {
    if (!selectedFiles.length) return;
    const formData = new FormData();
    formData.append("branch", document.getElementById("branchSelect").value);
    for (const file of selectedFiles) formData.append("files", file);

    const statusEl = document.getElementById("uploadStatus");
    statusEl.className = "status";
    statusEl.textContent = "Uploading & ingesting...";
    statusEl.style.display = "block";
    uploadBtn.disabled = true;

    try {
        const res = await fetch(`${API}/teacher/upload`, {
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
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
        uploadBtn.disabled = selectedFiles.length === 0;
    }
}

// --- Students + progress ---
async function loadStudents() {
    try {
        const res = await fetch(`${API}/teacher/students`, { headers: getHeaders() });
        if (!res.ok) return;
        const students = await res.json();
        const tbody = document.querySelector("#studentsTable tbody");
        const noStudents = document.getElementById("noStudents");

        if (students.length === 0) {
            tbody.innerHTML = "";
            noStudents.style.display = "block";
            return;
        }
        noStudents.style.display = "none";

        tbody.innerHTML = students.map(s => {
            const cells = s.progress.map(p =>
                `<td><span class="mini-progress-track"><span class="mini-progress-fill" style="width:${p.percent}%"></span></span>${p.percent}%</td>`
            ).join("");
            const name = [s.first_name, s.last_name].filter(Boolean).join(" ") || s.username;
            return `<tr><td>${name}</td><td>${s.email || ""}</td>${cells}</tr>`;
        }).join("");
    } catch (_) { /* leave table empty on failure */ }
}
loadStudents();
