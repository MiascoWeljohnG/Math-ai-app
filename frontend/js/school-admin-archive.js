// School admin pages: Archive (archive.html) and File deletion (deletion-request.html).
// What a teacher deletes (a file, a lesson or a subject) waits in the archive for 30 days. archive.html lists all of it;
// deletion-request.html lists what has passed the 30 days, and the admin deletes that for good. The server only ever returns the admin's own school.
// Needs school-admin-common.js, material-table.js (formatUploadDate) and modal.js. Each page only has some of the markup below; the rest is skipped.
const ARCHIVE_KIND_LABEL = { file: "File", lesson: "Lesson", subject: "Subject" };
const archiveTable = document.getElementById("archiveTable");
const archiveFilter = document.getElementById("archiveFilter");
const dueList = document.getElementById("dueList");

function archiveWho(item) {
    return item.archived_by_name ? `${item.archived_by_name} (@${item.archived_by})` : `@${item.archived_by}`;
}
function archiveSubtitle(item) {   // what else the admin needs to recognise it: a lesson's subject, a file's branch, a subject's lesson count
    return item.context ? (item.kind === "lesson" ? `Subject: ${item.context}` : item.kind === "file" ? `Branch: ${item.context}` : item.context) : "";
}
function timeLeft(item) {
    return item.due ? "Ready to delete" : `${item.days_left} day${item.days_left === 1 ? "" : "s"} left`;
}

// ---- Archive page: everything, newest first ----
let archiveItems = [];
function renderArchive() {
    const choice = archiveFilter.value;
    const shown = choice === "all" ? archiveItems : archiveItems.filter(item => item.kind === choice);
    archiveTable.querySelector("tbody").innerHTML = shown.map(item => `<tr>
        <td class="file-name">${esc(item.title)}<span class="cell-sub">${esc(archiveSubtitle(item))}</span>${item.reason ? `<span class="cell-sub">Reason: ${esc(item.reason)}</span>` : ""}</td>
        <td><span class="tag">${esc(ARCHIVE_KIND_LABEL[item.kind] || item.kind)}</span></td>
        <td class="nowrap">${esc(archiveWho(item))}</td>
        <td class="nowrap">${esc(formatUploadDate(item.archived_at))}</td>
        <td class="nowrap">${item.due ? `<a href="deletion-request.html">Ready to delete</a>` : esc(timeLeft(item))}</td>
    </tr>`).join("");
    archiveTable.style.display = shown.length ? "" : "none";
    const empty = document.getElementById("noArchive");
    empty.style.display = shown.length ? "none" : "block";
    empty.textContent = archiveItems.length ? "Nothing of this type is in the archive." : "The archive is empty.";
    const count = document.getElementById("archiveCount");
    count.textContent = archiveItems.length;
    count.style.display = archiveItems.length ? "" : "none";
    document.getElementById("archiveNote").textContent = archiveItems.length ? `Showing ${shown.length} of ${archiveItems.length}` : "";
}

async function loadArchive() {
    try {
        const res = await fetch(`${API}/archive`, { headers: getHeaders() });
        if (res.ok) archiveItems = await res.json();   // a failed refresh keeps what is on screen
    } catch (_) { /* keep the last list */ }
    renderArchive();
}

// ---- File deletion page: what has passed its 30 days ----
let dueItems = [];
function dueCard(item) {
    const card = document.createElement("div");
    card.className = "req-card";
    const top = document.createElement("div");
    top.className = "req-top";
    const badge = document.createElement("span");
    badge.className = `tag type-${item.kind === "file" ? "module" : item.kind}`;   // colours of dashboard.css
    badge.textContent = ARCHIVE_KIND_LABEL[item.kind] || item.kind;
    const title = document.createElement("strong");
    title.textContent = item.title;
    top.append(badge, title);

    const meta = document.createElement("span");
    meta.className = "hint";
    meta.textContent = [`Deleted by ${archiveWho(item)} on ${formatUploadDate(item.archived_at)}.`, archiveSubtitle(item)].filter(Boolean).join(" ");
    card.append(top, meta);
    if (item.reason) {
        const reason = document.createElement("span");
        reason.textContent = `Reason: ${item.reason}`;
        card.append(reason);
    }
    const actions = document.createElement("div");
    actions.className = "req-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-danger btn-sm";
    button.textContent = "Delete permanently";
    button.addEventListener("click", () => purgeItem(item));
    actions.append(button);
    card.append(actions);
    return card;
}

function renderDue() {
    dueList.replaceChildren(...dueItems.map(dueCard));
    document.getElementById("noDue").style.display = dueItems.length ? "none" : "block";
    const count = document.getElementById("dueCount");
    count.textContent = dueItems.length;
    count.style.display = dueItems.length ? "" : "none";
    document.getElementById("purgeAllBtn").style.display = dueItems.length > 1 ? "" : "none";
}

async function loadDueItems() {
    try {
        const res = await fetch(`${API}/archive?due=true`, { headers: getHeaders() });
        if (res.ok) dueItems = (await res.json()).reverse();   // oldest first: the one waiting longest is on top
    } catch (_) { /* keep the last list */ }
    renderDue();
}

function afterPurge() {
    loadDueItems();
    if (typeof loadAdminOverview === "function") loadAdminOverview();
    if (typeof loadAuditLog === "function") loadAuditLog();
}

async function postPurge(path, okTitle) {
    try {
        const res = await fetch(`${API}/archive/${path}`, { method: "POST", headers: getHeaders() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Couldn't delete it.");
        await uiAlert(data.message, { title: okTitle });
    } catch (err) {
        await uiAlert(err.message, { title: "Couldn't delete" });
    }
    afterPurge();
}

async function purgeItem(item) {
    const what = { file: "file", lesson: "lesson", subject: "subject" }[item.kind] || "item";
    const detail = item.kind === "file"
        ? "The original file is removed too (with Google Drive it goes to the Drive trash)."
        : item.kind === "subject" ? `The subject and ${item.context || "its lessons"} are removed for good.` : "The lesson and its quiz are removed for good.";
    if (!await uiConfirm(`Permanently delete the ${what} "${item.title}"?\n\n${detail}\n\nThis can't be undone.`, { title: "Delete permanently", okText: "Delete permanently", danger: true })) return;
    await postPurge(`${item.id}/purge`, "Deleted");
}

async function purgeAllDue() {
    if (!dueItems.length) return;
    if (!await uiConfirm(`Permanently delete all ${dueItems.length} items on this list?\n\nThis can't be undone.`, { title: "Delete all", okText: "Delete all", danger: true })) return;
    await postPurge("purge-due", "Deleted");
}

if (archiveTable) {
    archiveFilter.addEventListener("change", renderArchive);
    loadArchive();
    setInterval(loadArchive, 60000);
}
if (dueList) {
    document.getElementById("purgeAllBtn").addEventListener("click", purgeAllDue);
    loadDueItems();
    setInterval(loadDueItems, 60000);
}
