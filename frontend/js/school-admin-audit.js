// School admin page: Audit log (audit-log.html) - what happened in this school (the server only returns this school's events).
// Needs school-admin-common.js, material-table.js (formatUploadDate) and the #auditTable and filter markup of that page.
const AUDIT_LABEL = {
    "student.register": "Student signed up", "student.resubmit": "Student sent a new certificate",
    "student.approve": "Approved a student", "student.reject": "Rejected a student", "certificate.view": "Opened a certificate",
    "teacher.create": "Created a teacher account", "file.delete": "Deleted a file",
    "subject.delete.request": "Asked to delete a subject", "subject.delete.approve": "Approved a subject deletion",
    "subject.delete.reject": "Rejected a subject deletion",
    "file.delete.request": "Asked to delete a module (file)", "file.delete.approve": "Approved a module (file) deletion",
    "file.delete.reject": "Rejected a module (file) deletion",
    "file.archive": "Teacher deleted a file (moved to the archive)", "lesson.archive": "Teacher deleted a lesson (moved to the archive)",
    "subject.archive": "Teacher deleted a subject (moved to the archive)", "archive.purge": "Permanently deleted an archived item",
    "lesson.delete": "Deleted a lesson", "lesson.delete.request": "Asked to delete a lesson",
    "lesson.delete.approve": "Approved a lesson deletion", "lesson.delete.reject": "Rejected a lesson deletion",
    "quiz.retake.approve": "Approved a quiz retake", "quiz.retake.reject": "Rejected a quiz retake",
    "school_admin.create": "Created a school admin account",
    "users.view": "Opened the accounts list", "approvals.view": "Opened pending approvals",
    "subject.delete.view": "Opened subject deletion requests", "file.delete.view": "Opened module deletion requests",
    "roster.view": "Opened the student roster", "scores.view": "Opened student scores",
};

// "What" filter: each choice stands for one or more action codes (* is a wildcard, handled by the server).
const AUDIT_WHAT = {
    signups: ["student.register", "student.resubmit"],
    decisions: ["student.approve", "student.reject"],
    certificates: ["certificate.view"],
    accounts: ["*.create"],
    requests: ["subject.delete.request", "lesson.delete.request", "file.delete.request"],
    verdicts: ["*.delete.approve", "*.delete.reject"],
    deleted: ["file.delete", "lesson.delete", "*.archive", "archive.purge"],
    retakes: ["quiz.retake.*"],
    views: ["*.view"],
};

// "When" filter: a time window in the browser's own time zone, sent to the server as exact (UTC) times.
function auditWindow(choice) {
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    const daysBefore = (date, n) => { const d = new Date(date); d.setDate(d.getDate() - n); return d; };
    const now = new Date();
    switch (choice) {
        case "today": return { since: startOfToday };
        case "yesterday": return { since: daysBefore(startOfToday, 1), until: startOfToday };
        case "week": return { since: daysBefore(now, 7) };
        case "month": return { since: daysBefore(now, 30) };
        case "year": return { since: daysBefore(now, 365) };
        default: return {};
    }
}

const AUDIT_LIMIT = 500;   // the most the server returns

function auditQuery() {
    const params = new URLSearchParams({ limit: AUDIT_LIMIT });
    const when = auditWindow(document.getElementById("auditWhen").value);
    if (when.since) params.set("since", when.since.toISOString());
    if (when.until) params.set("until", when.until.toISOString());
    const who = document.getElementById("auditWho").value;
    if (who !== "all") params.set("role", who);
    const what = AUDIT_WHAT[document.getElementById("auditWhat").value];
    if (what) params.set("actions", what.join(","));
    return params;
}

function markActiveFilters() {
    ["auditWhen", "auditWho", "auditWhat"].forEach(id => {
        const el = document.getElementById(id);
        el.classList.toggle("is-active", el.value !== "all");
    });
}

function auditFiltered() {
    return ["auditWhen", "auditWho", "auditWhat"].some(id => document.getElementById(id).value !== "all");
}

async function loadAuditLog() {
    const res = await fetch(`${API}/school-admin/audit-log?${auditQuery()}`, { headers: getHeaders() });
    if (!res.ok) return;
    const rows = await res.json();
    const filtered = auditFiltered();
    markActiveFilters();
    const empty = document.getElementById("noAudit");
    empty.textContent = filtered ? "No events match these filters." : "Nothing has happened yet.";
    empty.style.display = rows.length ? "none" : "block";
    // the table stays visible even with no rows, because its header holds the filters
    document.getElementById("auditClear").style.display = filtered ? "" : "none";
    document.getElementById("auditCount").textContent = !rows.length ? ""
        : rows.length >= AUDIT_LIMIT ? `Showing the latest ${rows.length} events`
        : `${rows.length} event${rows.length === 1 ? "" : "s"}`;
    document.querySelector("#auditTable tbody").innerHTML = rows.map(r =>
        `<tr><td class="nowrap">${esc(formatUploadDate(r.at))}</td><td>${esc(r.actor)}</td><td>${esc(AUDIT_LABEL[r.action] || r.action)}</td><td>${esc(r.target)}</td><td>${esc(r.detail)}</td></tr>`
    ).join("");
}
loadAuditLog();
document.getElementById("auditRefresh").addEventListener("click", loadAuditLog);
["auditWhen", "auditWho", "auditWhat"].forEach(id => document.getElementById(id).addEventListener("change", loadAuditLog));
document.getElementById("auditClear").addEventListener("click", () => {
    ["auditWhen", "auditWho", "auditWhat"].forEach(id => { document.getElementById(id).value = "all"; });
    loadAuditLog();
});
