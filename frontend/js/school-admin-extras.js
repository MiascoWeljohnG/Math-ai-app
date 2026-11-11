// School admin extras: deletion requests (subjects, lessons, modules), the notification bell and the audit log.
// Needs API, getHeaders(), esc(), formatUploadDate() and the uiAlert / uiConfirm popups.
function showNotification(title, message, isError = false) {
    uiAlert(message, { title });
}

// --- Deletion requests: a teacher asked to delete a subject, a lesson or a module (an uploaded file); the school admin decides ---
// One list, three kinds. Each kind has its own endpoint; the page merges them, oldest first, and a dropdown filters by kind.
const deletionList = document.getElementById("deletionList");
const deletionFilter = document.getElementById("deletionFilter");
let announcedDeletions = false;

const DELETION_KINDS = {
    subject: {
        badge: "Subject", plural: "subjects", path: "subject-deletions", keep: "Reject (keep subject)",
        title: r => r.subject_name,
        meta: r => `Requested by @${r.requested_by} on ${formatUploadDate(r.created_at)}. This also deletes ${countOf(r.lesson_count, "lesson")} and their quizzes.`,
        confirm: r => `Approve deleting the subject "${r.subject_name}"?\n\nThe subject, its lessons, quizzes and students' progress on it will be permanently deleted.`,
        needsMe: r => r.my_vote === null,
        note: r => r.my_vote === "approve" ? "You approved this." : "Waiting for your decision.",
    },
    lesson: {
        badge: "Lesson", plural: "lessons", path: "lesson-deletions", keep: "Reject (keep lesson)",
        title: r => r.lesson_title,
        meta: r => {
            const who = r.requested_by_name ? `${r.requested_by_name} (@${r.requested_by})` : `@${r.requested_by}`;
            const done = r.completions ? ` ${countOf(r.completions, "student")} completed it; their progress on it is deleted too.` : "";
            return `Requested by ${who} on ${formatUploadDate(r.created_at)}. Subject: ${r.subject_name}.${done}`;
        },
        confirm: r => `Approve deleting the lesson "${r.lesson_title}"?\n\nThe lesson, its quiz and students' progress on it will be permanently deleted.`,
        needsMe: () => true,
        note: () => "Waiting for your decision.",
    },
    module: {
        badge: "Module", plural: "modules", path: "file-deletions", keep: "Reject (keep module)",
        title: r => r.display_name,
        meta: r => {
            const who = r.requested_by_name ? `${r.requested_by_name} (@${r.requested_by})` : `@${r.requested_by}`;
            return `Requested by ${who} on ${formatUploadDate(r.created_at)}. Subject: ${r.branch}.`;
        },
        confirm: r => `Approve deleting the module "${r.display_name}"?\n\nThe file and what the AI learned from it will be removed. The original is moved to the Archived folder in Google Drive.`,
        needsMe: () => true,
        note: null,
    },
};
const DELETION_TYPES = Object.keys(DELETION_KINDS);
function countOf(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }
let deletionsByType = { subject: [], lesson: [], module: [] };   // what the server last said, per kind

function deletionCard(request) {
    const kind = DELETION_KINDS[request.type];
    const card = document.createElement("div");
    card.className = "req-card";
    card.dataset.type = request.type;

    const top = document.createElement("div");
    top.className = "req-top";
    const badge = document.createElement("span");
    badge.className = `tag type-${request.type}`;
    badge.textContent = kind.badge;
    const title = document.createElement("strong");
    title.textContent = `Delete "${kind.title(request)}"?`;
    top.append(badge, title);

    const meta = document.createElement("span");
    meta.className = "hint";
    meta.textContent = kind.meta(request);
    card.append(top, meta);

    if (request.reason) {
        const reason = document.createElement("span");
        reason.textContent = `Reason: ${request.reason}`;
        card.append(reason);
    }

    if (kind.note) {
        const note = document.createElement("span");
        note.className = "hint";
        note.textContent = kind.note(request);
        card.append(note);
    }

    const approved = request.type === "subject" && request.my_vote === "approve";
    const actions = document.createElement("div");
    actions.className = "req-actions";
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "btn btn-danger btn-sm";
    approve.textContent = approved ? "You approved" : "Approve deletion";
    approve.disabled = approved;
    approve.addEventListener("click", () => decideDeletion(request, true));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "btn btn-secondary btn-sm";
    reject.textContent = kind.keep;
    reject.addEventListener("click", () => decideDeletion(request, false));
    actions.append(approve, reject);
    card.append(actions);
    return card;
}

// Draw the list for the chosen filter, with the counts on the dropdown and the badge next to the title.
function renderDeletions() {
    const all = DELETION_TYPES.flatMap(type => deletionsByType[type].map(r => ({ ...r, type })))
        .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)) || a.id - b.id);
    const choice = DELETION_TYPES.includes(deletionFilter.value) ? deletionFilter.value : "all";
    const shown = choice === "all" ? all : all.filter(r => r.type === choice);

    deletionList.replaceChildren(...shown.map(deletionCard));
    const empty = document.getElementById("noDeletions");
    empty.style.display = shown.length ? "none" : "block";
    empty.textContent = choice === "all" || all.length === 0 ? "No pending requests." : `No ${DELETION_KINDS[choice].plural} are waiting for a decision.`;

    const count = document.getElementById("deletionCount");
    count.textContent = all.length;
    count.style.display = all.length ? "" : "none";
    document.getElementById("deletionFilterNote").textContent = all.length ? `Showing ${shown.length} of ${all.length}` : "";

    deletionFilter.querySelector('option[value="all"]').textContent = `All requests (${all.length})`;
    DELETION_TYPES.forEach(type => {
        const label = DELETION_KINDS[type].plural;
        deletionFilter.querySelector(`option[value="${type}"]`).textContent = `${label[0].toUpperCase()}${label.slice(1)} (${deletionsByType[type].length})`;
    });
}
deletionFilter.addEventListener("change", renderDeletions);

async function loadDeletionRequests() {
    // A kind that fails to load keeps what it showed before, so one bad endpoint never empties the whole list.
    await Promise.all(DELETION_TYPES.map(async type => {
        try {
            const res = await fetch(`${API}/${DELETION_KINDS[type].path}`, { headers: getHeaders() });
            if (res.ok) deletionsByType[type] = await res.json();
        } catch (_) { /* keep the last list */ }
    }));
    renderDeletions();

    // The notification: once per visit, tell this admin if requests still need their answer.
    const waiting = DELETION_TYPES.map(type => [type, deletionsByType[type].filter(r => DELETION_KINDS[type].needsMe(r)).length]).filter(([, n]) => n);
    const total = waiting.reduce((sum, [, n]) => sum + n, 0);
    if (total && !announcedDeletions) {
        announcedDeletions = true;
        const parts = waiting.map(([type, n]) => `${n} ${n === 1 ? DELETION_KINDS[type].badge.toLowerCase() : DELETION_KINDS[type].plural}`).join(", ");
        showNotification("Approval needed", `${total} deletion request${total === 1 ? " is" : "s are"} waiting for your decision (${parts}).`);
    }
}

async function decideDeletion(request, approve) {
    const kind = DELETION_KINDS[request.type];
    if (approve && !await uiConfirm(kind.confirm(request), { title: "Approve deletion", okText: "Approve", danger: true })) return;
    try {
        const res = await fetch(`${API}/${kind.path}/${request.id}/decision`, {
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
    if (request.type === "module" && typeof loadFiles === "function") loadFiles();
    if (typeof loadAuditLog === "function") loadAuditLog();
    if (typeof loadAdminOverview === "function") loadAdminOverview();
}

loadDeletionRequests();
setInterval(loadDeletionRequests, 30000);


// --- Notification bell: AI-unsure uploads, teacher uploads, deleted files, deletion requests ---
const bellBtn = document.getElementById("bellBtn");
const bellPanel = document.getElementById("bellPanel");
const bellBadge = document.getElementById("bellBadge");
const bellList = document.getElementById("bellList");
const WARN_KINDS = new Set(["needs_topic", "deletion_request", "file_deletion_request", "lesson_deletion_request"]);

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
    "file.delete.request": "Asked to delete a module (file)", "file.delete.approve": "Approved a module (file) deletion",
    "file.delete.reject": "Rejected a module (file) deletion",
    "lesson.delete": "Deleted a lesson", "lesson.delete.request": "Asked to delete a lesson",
    "lesson.delete.approve": "Approved a lesson deletion", "lesson.delete.reject": "Rejected a lesson deletion",
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
