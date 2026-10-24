function getHeaders() {
    return {
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

// Only the super admin may create admins. The login response says whether this account is one; this just decides
// whether the button is shown - the server refuses everyone else anyway.
document.addEventListener("DOMContentLoaded", () => {
    if (localStorage.getItem("is_super_admin") === "1") {
        document.getElementById("openAdminModalBtn").style.display = "inline-block";
    }
});


// --- Load users ---
let allUsers = [];

function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderUsers() {
    const filter = document.getElementById("roleFilter").value;
    const school = document.getElementById("schoolFilter").value;
    const inSchool = u => school === "all" || (school === "main" ? u.school_id == null : String(u.school_id) === school);
    const users = allUsers.filter(u => (filter === "all" || u.role === filter) && inSchool(u));
    const tbody = document.querySelector("#usersTable tbody");
    tbody.innerHTML = users.map(u =>
        `<tr><td>${esc(u.username)}</td><td>${esc(u.last_name)}</td><td>${esc(u.first_name)}</td><td>${esc(u.middle_name)}</td><td>${esc(u.email)}</td><td>${esc(u.birthday)}</td><td>${esc(u.school || "Main")}</td><td>${esc(u.role.replace("_", " "))}${u.status && u.status !== "active" ? ` <span class="tag warn">${esc(u.status)}</span>` : ""}</td><td>${esc(u.created)}</td></tr>`
    ).join("");
    document.getElementById("userCount").textContent = `Showing ${users.length} of ${allUsers.length}`;
}

async function loadUsers() {
    const res = await fetch(`${API}/admin/users`, { headers: getHeaders() });
    if (!res.ok) return;
    allUsers = await res.json();
    renderUsers();
}
document.getElementById("roleFilter").addEventListener("change", renderUsers);
document.getElementById("schoolFilter").addEventListener("change", renderUsers);
loadUsers();

// --- Schools: the list, the add form, and every school dropdown on the page ---
let schools = [];

function fillSelect(id, firstValue, firstLabel) {
    const el = document.getElementById(id), keep = el.value;
    el.replaceChildren(new Option(firstLabel, firstValue), ...schools.map(s => new Option(s.name, s.id)));
    if (keep) el.value = keep;
}

function schoolIdOf(selectId) {
    const value = document.getElementById(selectId).value;
    return value ? Number(value) : null;   // null = the main pool
}

async function loadSchools() {
    const res = await fetch(`${API}/schools`);
    if (!res.ok) return;
    schools = await res.json();
    document.getElementById("schoolList").replaceChildren(...schools.map(s => Object.assign(document.createElement("span"), { className: "tag", textContent: s.name })));
    document.getElementById("noSchools").style.display = schools.length ? "none" : "block";
    fillSelect("teacherSchool", "", "Choose a school");
    fillSelect("adminSchool", "", "Choose a school");
    fillSelect("schoolFilter", "all", "All schools");
    document.getElementById("schoolFilter").add(new Option("Main (no school)", "main"), 1);
}

loadSchools();

// --- Load files ---
function stripHashPrefix(name) {
    return name.replace(/^[a-f0-9]{32}_/i, "");
}

let existingFileNames = new Set(); 

async function loadFiles() {
    const res = await fetch(`${API}/admin/files`, { headers: getHeaders() });
    if (!res.ok) return;
    const files = await res.json();

    existingFileNames = new Set(files.map(f => stripHashPrefix(f.display_name).toLowerCase()));

    document.getElementById("noFiles").style.display = files.length ? "none" : "block";
    document.getElementById("filesTable").style.display = files.length ? "" : "none";
    renderMaterialRows(document.querySelector("#filesTable tbody"), files, true, deleteFile);
    renderChips(); 
}
loadFiles();

// --- Delete one file (asks first) ---
async function deleteFile(file) {
    const ok = await uiConfirm(
        `Delete "${file.display_name}"?\n\nThe file is removed from the knowledge base and the AI will no longer use it. This cannot be undone.`,
        { title: "Delete file", okText: "Delete", danger: true }
    );
    if (!ok) return;
    try {
        const res = await fetch(`${API}/admin/files/${encodeURIComponent(file.filename)}`, { method: "DELETE", headers: getHeaders() });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't delete this file.");
        showNotification("Deleted", data.message);
        loadFiles();
    } catch (err) {
        showNotification("Error", err.message, true);
    }
}

// --- File upload with removable chips + duplicate detection ---
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const dropPlaceholder = document.getElementById("dropPlaceholder");
const dupWarning = document.getElementById("dupWarning");
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
}

async function uploadFiles() {
    if (!selectedFiles.length) { 
        showNotification("No Files Selected", "Please select files to upload first.", true);
        return; 
    }

    const statusEl = document.getElementById("uploadStatus");
    statusEl.className = "status";
    statusEl.textContent = "Uploading & ingesting...";
    statusEl.style.display = "block";

    await withButtonLoading(uploadBtn, async () => {
        const branch = document.getElementById("branchSelect").value;
        const { message, savedNames } = await uploadWithTopics(`${API}/admin/upload`, getHeaders(), selectedFiles, branch);

        statusEl.className = "status success";
        statusEl.textContent = message;
        selectedFiles = selectedFiles.filter(f => !savedNames.has(f.name));   // unfiled files stay selected
        renderChips();
        loadFiles();
    }).catch(err => {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
    });
}

// --- Notification Modal ---
const notificationModal = document.getElementById("notificationModal");
const notificationTitle = document.getElementById("notificationTitle");
const notificationMessage = document.getElementById("notificationMessage");

function showNotification(title, message, isError = false) {
    notificationTitle.textContent = title;
    notificationTitle.style.color = isError ? "var(--danger)" : "var(--text)";
    notificationMessage.textContent = message;
    notificationModal.classList.add("active");
}

function hideNotification() {
    notificationModal.classList.remove("active");
}

document.getElementById("closeNotificationBtn").addEventListener("click", hideNotification);
notificationModal.addEventListener("click", (e) => {
    if (e.target === notificationModal) hideNotification();
});

// --- Clear knowledge base Modal ---
const clearKbModal = document.getElementById("clearKbModal");

function showClearKbModal() {
    clearKbModal.classList.add("active");
}

function hideClearKbModal() {
    clearKbModal.classList.remove("active");
}

document.getElementById("closeClearKbModal").addEventListener("click", hideClearKbModal);
document.getElementById("cancelClearKbBtn").addEventListener("click", hideClearKbModal);
clearKbModal.addEventListener("click", (e) => {
    if (e.target === clearKbModal) hideClearKbModal();
});

document.getElementById("confirmClearKbBtn").addEventListener("click", async () => {
    hideClearKbModal(); 
    
    try {
        const res = await fetch(`${API}/admin/knowledge-base`, {
            method: "DELETE",
            headers: getHeaders(),
        });
        const data = await res.json();
        
        showNotification("Success", data.message);
        loadFiles();
    } catch (err) {
        showNotification("Error", "Failed to clear knowledge base: " + err.message, true);
    }
});

function clearKB() {
    showClearKbModal();
}

// --- Create teacher account ---
async function createTeacher() {
    const username = document.getElementById("teacherUsername").value.trim();
    const last_name = document.getElementById("teacherLastName").value.trim();
    const first_name = document.getElementById("teacherFirstName").value.trim();
    const middle_name = document.getElementById("teacherMiddleName").value.trim();
    const email = document.getElementById("teacherEmail").value.trim();
    const birthday = document.getElementById("teacherBirthday").value;
    const password = document.getElementById("teacherPassword").value;
    const statusEl = document.getElementById("teacherStatus");

    if (!username || !last_name || !first_name || !password || !birthday) {
        statusEl.className = "status error";
        statusEl.textContent = "Username, last name, first name, birthday and password are required.";
        return;
    }

    try {
        const res = await fetch(`${API}/admin/create-teacher`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ username, last_name, first_name, middle_name, email, birthday, password, school_id: schoolIdOf("teacherSchool") }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        statusEl.className = "status success";
        statusEl.textContent = data.message;
        ["teacherUsername", "teacherLastName", "teacherFirstName", "teacherMiddleName", "teacherEmail", "teacherBirthday", "teacherPassword"].forEach(id => {
            document.getElementById(id).value = "";
        });
        loadUsers();

        setTimeout(() => {
            const modal = document.getElementById("teacherModal");
            if (modal) modal.classList.remove("active");
            statusEl.className = "status";
            statusEl.textContent = "";
        }, 1200);
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
    }
}
document.getElementById("teacherBirthday").max = new Date().toISOString().slice(0, 10);

// --- Create admin account ---
async function createAdmin() {
    const username = document.getElementById("adminUsername").value.trim();
    const last_name = document.getElementById("adminLastName").value.trim();
    const first_name = document.getElementById("adminFirstName").value.trim();
    const middle_name = document.getElementById("adminMiddleName").value.trim();
    const email = document.getElementById("adminEmail").value.trim();
    const birthday = document.getElementById("adminBirthday").value;
    const password = document.getElementById("adminPassword").value;
    const statusEl = document.getElementById("adminStatus");

    if (!username || !last_name || !first_name || !password || !birthday) {
        statusEl.className = "status error";
        statusEl.textContent = "Username, last name, first name, birthday and password are required.";
        return;
    }

    try {
        const res = await fetch(`${API}/admin/create-admin`, { // Endpoint for creating admins
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ username, last_name, first_name, middle_name, email, birthday, password, school_id: schoolIdOf("adminSchool") }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        statusEl.className = "status success";
        statusEl.textContent = data.message;
        ["adminUsername", "adminLastName", "adminFirstName", "adminMiddleName", "adminEmail", "adminBirthday", "adminPassword"].forEach(id => {
            document.getElementById(id).value = "";
        });
        loadUsers();

        setTimeout(() => {
            const modal = document.getElementById("adminModal");
            if (modal) modal.classList.remove("active");
            statusEl.className = "status";
            statusEl.textContent = "";
        }, 1200);
    } catch (err) {
        statusEl.className = "status error";
        statusEl.textContent = err.message;
    }
}
document.getElementById("adminBirthday").max = new Date().toISOString().slice(0, 10);


// --- Subject deletion requests: every admin has to approve before a subject disappears ---
const deletionList = document.getElementById("deletionList");
let announcedDeletions = false;

function deletionCard(request) {
    const card = document.createElement("div");
    card.className = "req-card";

    const title = document.createElement("strong");
    title.textContent = `Delete "${request.subject_name}"?`;

    const meta = document.createElement("span");
    meta.className = "hint";
    const lessons = `${request.lesson_count} lesson${request.lesson_count === 1 ? "" : "s"} and their quizzes`;
    meta.textContent = `Requested by @${request.requested_by} on ${formatUploadDate(request.created_at)}. This also deletes ${lessons}.`;
    card.append(title, meta);

    if (request.reason) {
        const reason = document.createElement("span");
        reason.textContent = `Reason: ${request.reason}`;
        card.append(reason);
    }

    const votes = document.createElement("span");
    votes.className = "hint";
    const approved = request.approved_by.length ? request.approved_by.map(name => `@${name}`).join(", ") : "nobody yet";
    const waiting = request.waiting_on.length ? ` Waiting on ${request.waiting_on.map(name => `@${name}`).join(", ")}.` : "";
    votes.textContent = `Approved by ${approved} (${request.approved_by.length} of ${request.admins_total}).${waiting}`;
    card.append(votes);

    const actions = document.createElement("div");
    actions.className = "req-actions";
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "btn btn-danger btn-sm";
    approve.textContent = request.my_vote === "approve" ? "You approved" : "Approve deletion";
    approve.disabled = request.my_vote === "approve";
    approve.addEventListener("click", () => decideDeletion(request, true));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "btn btn-secondary btn-sm";
    reject.textContent = "Reject (keep subject)";
    reject.addEventListener("click", () => decideDeletion(request, false));
    actions.append(approve, reject);
    card.append(actions);
    return card;
}

async function loadDeletionRequests() {
    try {
        const res = await fetch(`${API}/subject-deletions`, { headers: getHeaders() });
        if (!res.ok) return;
        const requests = await res.json();
        deletionList.replaceChildren(...requests.map(deletionCard));
        document.getElementById("noDeletions").style.display = requests.length ? "none" : "block";
        const count = document.getElementById("deletionCount");
        count.textContent = requests.length;
        count.style.display = requests.length ? "" : "none";

        // The notification: once per visit, tell this admin if a request still needs their answer.
        const needMe = requests.filter(request => request.my_vote === null).length;
        if (needMe && !announcedDeletions) {
            announcedDeletions = true;
            showNotification("Approval needed", `${needMe} subject deletion request${needMe === 1 ? " is" : "s are"} waiting for your decision.`);
        }
    } catch (_) { /* leave the list as it was */ }
}

async function decideDeletion(request, approve) {
    if (approve && !await uiConfirm(`Approve deleting "${request.subject_name}"?\n\nIf every admin approves, the subject, its lessons, quizzes and students' progress on it are permanently deleted.`, { title: "Approve deletion", okText: "Approve", danger: true })) return;
    try {
        const res = await fetch(`${API}/subject-deletions/${request.id}/decision`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ approve }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't save your decision.");
        showNotification(approve ? "Approved" : "Rejected", data.message);
    } catch (err) {
        showNotification("Error", err.message, true);
    }
    loadDeletionRequests();
}

loadDeletionRequests();
setInterval(loadDeletionRequests, 30000);


// --- Notification bell: AI-unsure uploads, teacher uploads, deleted files, deletion requests ---
const bellBtn = document.getElementById("bellBtn");
const bellPanel = document.getElementById("bellPanel");
const bellBadge = document.getElementById("bellBadge");
const bellList = document.getElementById("bellList");
const WARN_KINDS = new Set(["needs_topic", "deletion_request"]);

function timeAgo(iso) {
    const seconds = Math.max(0, (Date.now() - new Date(iso)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
    return formatUploadDate(iso);
}

function bellItem(n) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "bell-item" + (n.read ? "" : " unread") + (WARN_KINDS.has(n.kind) ? " warn" : "");
    const title = document.createElement("span"); title.className = "b-title"; title.textContent = n.title;
    const msg = document.createElement("span"); msg.className = "b-msg"; msg.textContent = n.message;
    const time = document.createElement("span"); time.className = "b-time"; time.textContent = timeAgo(n.created_at);
    item.append(title, msg, time);
    item.addEventListener("click", async () => {
        if (n.read) return;
        await fetch(`${API}/notifications/${n.id}/read`, { method: "POST", headers: getHeaders() });
        loadNotifications();
    });
    return item;
}

async function loadNotifications() {
    try {
        const res = await fetch(`${API}/notifications`, { headers: getHeaders() });
        if (!res.ok) return;
        const { unread, items } = await res.json();
        bellList.replaceChildren(...items.map(bellItem));
        document.getElementById("bellEmpty").style.display = items.length ? "none" : "block";
        bellBadge.textContent = unread > 99 ? "99+" : unread;
        bellBadge.style.display = unread ? "" : "none";
    } catch (_) { /* keep what's shown */ }
}

function setBellOpen(open) {
    bellPanel.classList.toggle("open", open);
    bellBtn.setAttribute("aria-expanded", open);
    if (open) loadNotifications();
}
bellBtn.addEventListener("click", (e) => { e.stopPropagation(); setBellOpen(!bellPanel.classList.contains("open")); });
document.addEventListener("click", (e) => { if (!document.getElementById("bellWrap").contains(e.target)) setBellOpen(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") setBellOpen(false); });
document.getElementById("bellReadAll").addEventListener("click", async () => {
    await fetch(`${API}/notifications/read-all`, { method: "POST", headers: getHeaders() });
    loadNotifications();
});
document.getElementById("bellClear").addEventListener("click", async () => {
    if (!await uiConfirm("Remove every notification from your list?", { title: "Clear notifications", okText: "Clear", danger: true })) return;
    await fetch(`${API}/notifications`, { method: "DELETE", headers: getHeaders() });
    loadNotifications();
});

loadNotifications();
setInterval(loadNotifications, 30000);