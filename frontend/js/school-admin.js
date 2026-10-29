// School admin page. The server decides which school this is from the signed-in account, so nothing
// here sends or trusts a school id.
function getHeaders() {   // material-table.js uses this for downloads too
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- Teachers & students of this school ---
let allUsers = [];

function renderUsers() {
    const filter = document.getElementById("roleFilter").value;
    const users = filter === "all" ? allUsers : allUsers.filter(u => u.role === filter);
    document.querySelector("#usersTable tbody").innerHTML = users.map(u => {
        return `<tr><td>${esc(u.username)}</td><td>${esc(u.last_name)}</td><td>${esc(u.first_name)}</td><td>${esc(u.middle_name)}</td><td>${esc(u.email)}</td><td>${esc(u.role.replace("_", " "))}${u.status && u.status !== "active" ? ` <span class="tag warn">${esc(u.status)}</span>` : ""}</td><td>${esc(u.created)}</td></tr>`;
    }).join("");
    document.getElementById("userCount").textContent = `Showing ${users.length} of ${allUsers.length}`;
}

async function loadUsers() {
    const res = await fetch(`${API}/school-admin/users`, { headers: getHeaders() });
    if (!res.ok) return;
    allUsers = await res.json();
    renderUsers();
}
document.getElementById("roleFilter").addEventListener("change", renderUsers);
loadUsers();

// --- Files uploaded by this school's teachers ---
async function loadFiles() {
    const res = await fetch(`${API}/school-admin/files`, { headers: getHeaders() });
    if (!res.ok) return;
    const files = await res.json();
    document.getElementById("noFiles").style.display = files.length ? "none" : "block";
    document.getElementById("filesTable").style.display = files.length ? "" : "none";
    renderMaterialRows(document.querySelector("#filesTable tbody"), files, true, deleteFile);
}

async function deleteFile(file) {
    if (!await uiConfirm(`Delete "${file.display_name}"?\n\nThe file and what the AI learned from it are removed. This can't be undone.`, { title: "Delete file", okText: "Delete", danger: true })) return;
    const res = await fetch(`${API}/school-admin/files/${encodeURIComponent(file.filename)}`, { method: "DELETE", headers: getHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) await uiAlert(data.detail || "Couldn't delete the file.", { title: "Delete file" });
    loadFiles();
    if (typeof loadAuditLog === "function") loadAuditLog();
}
loadFiles();

// --- Add a teacher to this school ---
const teacherModal = document.getElementById("teacherModal");
const teacherStatus = document.getElementById("teacherStatus");
const teacherFields = ["teacherUsername", "teacherLastName", "teacherFirstName", "teacherMiddleName", "teacherEmail", "teacherBirthday", "teacherPassword"];
document.getElementById("teacherBirthday").max = new Date().toISOString().slice(0, 10);
const teacherGuard = guardUnsaved(teacherModal, (discarded) => {
    if (discarded) { document.getElementById("teacherForm").reset(); teacherStatus.className = "status"; teacherStatus.textContent = ""; }
    teacherModal.classList.remove("active");
});
document.getElementById("openTeacherModalBtn").addEventListener("click", () => { teacherGuard.reset(); teacherModal.classList.add("active"); });
document.getElementById("closeTeacherModal").addEventListener("click", () => teacherGuard.requestClose());
teacherGuard.attachBackdrop(teacherModal);

document.getElementById("teacherForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const [username, last_name, first_name, middle_name, email, birthday, password] = teacherFields.map(id => document.getElementById(id).value.trim());
    try {
        const res = await fetch(`${API}/school-admin/create-teacher`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ username, last_name, first_name, middle_name, email, birthday, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        teacherStatus.className = "status success";
        teacherStatus.textContent = data.message;
        teacherFields.forEach(id => { document.getElementById(id).value = ""; });
        loadUsers();
        setTimeout(() => {
            teacherModal.classList.remove("active");
            teacherStatus.className = "status";
            teacherStatus.textContent = "";
        }, 1200);
    } catch (err) {
        teacherStatus.className = "status error";
        teacherStatus.textContent = err.message;
    }
});
