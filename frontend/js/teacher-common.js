// Shared by every teacher page: the sign-in header the API calls send. Load it right after auth.js.
function getHeaders() {
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

// Escape text before it goes into an innerHTML template (lesson titles, names).
function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
