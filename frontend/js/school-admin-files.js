// School admin page: Files from your school (school-files.html) - what the school's teachers uploaded, and re-indexing.
// Needs school-admin-common.js, material-table.js, modal.js and the files table markup of that page.
// --- Files uploaded by this school's teachers ---
async function loadFiles() {
    const res = await fetch(`${API}/school-admin/files`, { headers: getHeaders() });
    if (!res.ok) return;
    const files = await res.json();
    document.getElementById("noFiles").style.display = files.length ? "none" : "block";
    document.getElementById("filesTable").style.display = files.length ? "" : "none";
    renderMaterialRows(document.querySelector("#filesTable tbody"), files, true, deleteFile, loadFiles);
}

async function deleteFile(file) {
    if (!await uiConfirm(`Delete "${file.display_name}"?\n\nThe file and what the AI learned from it are removed. The original is moved to the Archived folder in Google Drive.`, { title: "Delete file", okText: "Delete", danger: true })) return;
    const res = await fetch(`${API}/school-admin/files/${encodeURIComponent(file.filename)}`, { method: "DELETE", headers: getHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) await uiAlert(data.detail || "Couldn't delete the file.", { title: "Delete file" });
    loadFiles();
    if (typeof loadAuditLog === "function") loadAuditLog();
    if (typeof loadAdminOverview === "function") loadAdminOverview();
}
loadFiles();

// Rebuild the shared material index; the endpoint accepts school admins via require_staff.
const reindexUploadsBtn = document.getElementById("reindexUploadsBtn");
const reindexStatus = document.getElementById("reindexStatus");
reindexUploadsBtn.addEventListener("click", async () => {
    reindexUploadsBtn.disabled = true;
    reindexStatus.className = "status info";
    reindexStatus.textContent = "Re-indexing the uploaded files…";
    try {
        const response = await fetch(`${API}/materials/reindex`, { method: "POST", headers: getHeaders() });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Re-index failed.");
        reindexStatus.className = "status success";
        reindexStatus.textContent = `Done. The AI now knows ${result.chunks} text chunks from your uploaded files.`;
    } catch (error) {
        reindexStatus.className = "status error";
        reindexStatus.textContent = error.message;
    } finally {
        reindexUploadsBtn.disabled = false;
    }
});
