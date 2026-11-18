// The school admin's notification bell, on every school admin page (markup: staff-header.js).
// Shows AI-unsure uploads, teacher uploads, deleted files and deletion requests.
// Needs school-admin-common.js and material-table.js (formatUploadDate).
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
