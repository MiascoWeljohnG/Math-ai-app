// School admin extras: subject-deletion requests, the notification bell and the audit log.
// Needs API, getHeaders(), esc(), formatUploadDate() and the uiAlert / uiConfirm popups.
function showNotification(title, message, isError = false) {
    uiAlert(message, { title });
}

// --- Subject deletion requests from this school's teachers: the school admin decides ---
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
    votes.textContent = request.my_vote === "approve" ? "You approved this." : "Waiting for your decision.";
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
    if (approve && !await uiConfirm(`Approve deleting "${request.subject_name}"?\n\nThe subject, its lessons, quizzes and students' progress on it will be permanently deleted.`, { title: "Approve deletion", okText: "Approve", danger: true })) return;
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

// --- Audit log: what happened in this school (the server only returns this school's events) ---
const AUDIT_LABEL = {
    "student.register": "Student signed up", "student.resubmit": "Student sent a new certificate",
    "student.approve": "Approved a student", "student.reject": "Rejected a student", "certificate.view": "Opened a certificate",
    "teacher.create": "Created a teacher account", "file.delete": "Deleted a file",
    "subject.delete.request": "Asked to delete a subject", "subject.delete.approve": "Approved a subject deletion",
    "subject.delete.reject": "Rejected a subject deletion",
};

async function loadAuditLog() {
    const res = await fetch(`${API}/school-admin/audit-log?limit=100`, { headers: getHeaders() });
    if (!res.ok) return;
    const rows = await res.json();
    document.getElementById("noAudit").style.display = rows.length ? "none" : "block";
    document.getElementById("auditTable").style.display = rows.length ? "" : "none";
    document.querySelector("#auditTable tbody").innerHTML = rows.map(r =>
        `<tr><td class="nowrap">${esc(formatUploadDate(r.at))}</td><td>${esc(r.actor)}</td><td>${esc(AUDIT_LABEL[r.action] || r.action)}</td><td>${esc(r.target)}</td><td>${esc(r.detail)}</td></tr>`
    ).join("");
}
loadAuditLog();
document.getElementById("auditRefresh").addEventListener("click", loadAuditLog);
