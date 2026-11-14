// The teacher's notification bell (same look as the school admin's). It only ever shows:
//   upload_ok / upload_failed      a file you uploaded was read by the AI, or could not be
//   lesson_ready / lesson_failed   an AI-written lesson is done, or failed
//   quiz_violation                 a student's quiz was ended for violations and is now locked
//   retake_request                 that student sent feedback and asks to retake
// Needs js/auth.js (API), js/modal.js (uiConfirm), js/material-table.js (formatUploadDate), js/retake-requests.js.
(() => {
    const $ = (id) => document.getElementById(id);
    const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
    const WARN = new Set(["upload_failed", "lesson_failed", "quiz_violation", "retake_request"]);   // yellow dot: needs a look
    const OPEN_RETAKES = new Set(["quiz_violation", "retake_request"]);   // clicking these jumps to the requests table

    function ago(iso) {
        const seconds = Math.max(0, (Date.now() - new Date(iso)) / 1000);
        if (seconds < 60) return "just now";
        if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
        return typeof formatUploadDate === "function" ? formatUploadDate(iso) : new Date(iso).toLocaleDateString();
    }

    function item(n) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "bell-item" + (n.read ? "" : " unread") + (WARN.has(n.kind) ? " warn" : "");
        const title = document.createElement("span"); title.className = "b-title"; title.textContent = n.title;
        const msg = document.createElement("span"); msg.className = "b-msg"; msg.textContent = n.message;
        const time = document.createElement("span"); time.className = "b-time"; time.textContent = ago(n.created_at);
        el.append(title, msg, time);
        el.addEventListener("click", async () => {
            if (OPEN_RETAKES.has(n.kind)) {
                setOpen(false);
                if (typeof loadRetakeRequests === "function") loadRetakeRequests();
                $("retakeSection").scrollIntoView({ behavior: "smooth", block: "start" });
            }
            if (n.read) return;
            await fetch(`${API}/notifications/${n.id}/read`, { method: "POST", headers: auth() });
            load();
        });
        return el;
    }

    async function load() {
        try {
            const res = await fetch(`${API}/notifications`, { headers: auth() });
            if (!res.ok) return;
            const { unread, items } = await res.json();
            $("bellList").replaceChildren(...items.map(item));
            $("bellEmpty").style.display = items.length ? "none" : "block";
            $("bellBadge").textContent = unread > 99 ? "99+" : unread;
            $("bellBadge").style.display = unread ? "" : "none";
        } catch (_) { /* keep what's shown */ }
    }

    function setOpen(open) {
        $("bellPanel").classList.toggle("open", open);
        $("bellBtn").setAttribute("aria-expanded", open);
        if (open) load();
    }

    $("bellBtn").addEventListener("click", (e) => { e.stopPropagation(); setOpen(!$("bellPanel").classList.contains("open")); });
    document.addEventListener("click", (e) => { if (!$("bellWrap").contains(e.target)) setOpen(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
    $("bellReadAll").addEventListener("click", async () => {
        await fetch(`${API}/notifications/read-all`, { method: "POST", headers: auth() });
        load();
    });
    $("bellClear").addEventListener("click", async () => {
        if (!await uiConfirm("Remove every notification from your list?", { title: "Clear notifications", okText: "Clear", danger: true })) return;
        await fetch(`${API}/notifications`, { method: "DELETE", headers: auth() });
        load();
    });

    load();
    setInterval(load, 30000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
})();
