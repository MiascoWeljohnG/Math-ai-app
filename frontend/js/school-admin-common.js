// Shared by every school admin page. The server decides which school this is from the signed-in account, so nothing
// here sends or trusts a school id.
function getHeaders() {   // material-table.js uses this for downloads too
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}

function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// A short popup for the result of an action (used by the deletion requests page).
function showNotification(title, message, isError = false) {
    uiAlert(message, { title });
}
