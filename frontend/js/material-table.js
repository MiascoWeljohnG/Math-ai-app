// Used by admin.js and teacher.js: fills the "uploaded files" table and downloads a file
// with the signed-in user's token (a plain link can't send the login header).
function formatUploadDate(iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

async function downloadMaterial(file) {
    try {
        const res = await fetch(`${API}/materials/${encodeURIComponent(file.filename)}/file`, { headers: getHeaders() });
        if (!res.ok) throw new Error("missing");
        const link = document.createElement("a");
        link.href = URL.createObjectURL(await res.blob());
        link.download = file.display_name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 10000);
    } catch (_) {
        uiAlert("Couldn't download this file. It may have been removed from the server.");
    }
}

// A file is saved the moment it is uploaded, but the AI reads it in the background (it can take minutes).
// While any file says "indexing" the table reloads itself every few seconds; a failed file gets a Retry button.
let indexingRefreshTimer = null;
function scheduleIndexingRefresh(files, onRefresh) {
    clearTimeout(indexingRefreshTimer);
    if (onRefresh && files.some(file => file.index_status === "indexing")) {
        indexingRefreshTimer = setTimeout(onRefresh, 4000);
    }
}

async function retryIndexing(file, onRefresh) {
    try {
        const res = await fetch(`${API}/materials/${encodeURIComponent(file.filename)}/retry-index`, { method: "POST", headers: getHeaders() });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || "Couldn't restart the reading of this file.");
        }
    } catch (err) {
        uiAlert(err.message);
    }
    if (onRefresh) onRefresh();
}

// What the server says it is doing with a file right now (index_progress comes from indexing.py).
function progressText(progress) {
    if (!progress || !progress.phase) return "The AI is reading this file… it can take a few minutes.";
    if (progress.phase === "queued") return "Waiting in line…";
    if (progress.phase === "reading") return "Reading the pages…";
    const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
    if (progress.phase === "waiting") {
        return `Paused by the AI service's rate limit, continuing in about ${progress.seconds}s… (${percent}% done)`;
    }
    return `Learning the content: ${progress.done} of ${progress.total} sections (${percent}%)`;
}

// Teacher table: File | Branch | Uploaded.  Admin table (showUploader): File | Branch | Uploaded by | Uploaded.
// Pass onDelete (admin page only) to add a Delete button next to Download.
// Pass onRefresh (reloads the table) so it updates itself while files are being indexed and after a Retry.
function renderMaterialRows(tbody, files, showUploader, onDelete, onRefresh) {
    scheduleIndexingRefresh(files, onRefresh);
    tbody.replaceChildren(...files.map(file => {
        const row = document.createElement("tr");
        const add = (className, ...content) => {
            const cell = document.createElement("td");
            cell.className = className;
            cell.append(...content);
            row.append(cell);
        };
        const branch = document.createElement("span");
        branch.className = "tag";
        branch.textContent = file.branch;
        branch.title = file.branch;
        const nameCell = [file.display_name];
        // reading normally takes minutes; after 15 the job was probably lost (e.g. the server restarted)
        const waitedMinutes = file.uploaded_at ? (Date.now() - new Date(file.uploaded_at).getTime()) / 60000 : 0;
        // Only "stuck" if the server isn't working on it (no progress info). A big file can legitimately take longer.
        const working = Boolean(file.index_progress && file.index_progress.phase);
        const stuck = file.index_status === "indexing" && waitedMinutes > 15 && !working;
        if (file.index_status === "indexing") {
            const note = document.createElement("span");
            note.className = "cell-sub";
            note.textContent = stuck
                ? "This is taking longer than usual. Press Retry to start it again."
                : progressText(file.index_progress);
            nameCell.push(note);
            const progress = file.index_progress;
            if (progress && progress.total) {
                const bar = document.createElement("progress");
                bar.max = progress.total;
                bar.value = progress.done || 0;
                bar.style.cssText = "display:block;width:100%;max-width:260px;margin-top:0.35rem;";
                nameCell.push(bar);
            }
        } else if (file.index_status === "failed") {
            const note = document.createElement("span");
            note.className = "cell-sub";
            note.style.color = "var(--danger, #d64545)";
            note.textContent = file.index_error || "The AI couldn't read this file.";
            nameCell.push(note);
        }
        // Set by the teacher page from /file-deletions/mine; the admin tables never have it.
        if (file.deletion_status === "pending" || file.deletion_status === "rejected") {
            const note = document.createElement("span");
            note.className = "cell-sub";
            note.textContent = file.deletion_status === "pending"
                ? "Deletion requested. Waiting for your school admin to confirm."
                : "Your school admin chose to keep this file.";
            nameCell.push(note);
        }
        add("file-name", ...nameCell);
        add("", branch);
        if (showUploader) {
            const sub = document.createElement("span");
            sub.className = "cell-sub";
            sub.textContent = file.uploaded_by_name ? `@${file.uploaded_by}` : "";
            add("nowrap", file.uploaded_by_name || file.uploaded_by, sub);
        }
        add("nowrap", formatUploadDate(file.uploaded_at));
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary btn-sm";
        button.textContent = "Download";
        button.addEventListener("click", () => downloadMaterial(file));
        const actions = [button];
        if (file.index_status === "failed" || stuck) {
            const retry = document.createElement("button");
            retry.type = "button";
            retry.className = "btn btn-primary btn-sm";
            retry.style.marginLeft = "0.4rem";
            retry.textContent = "Retry";
            retry.addEventListener("click", () => retryIndexing(file, onRefresh));
            actions.push(retry);
        }
        if (onDelete) {
            const del = document.createElement("button");
            del.type = "button";
            del.className = "btn btn-danger btn-sm";
            del.style.marginLeft = "0.4rem";
            del.textContent = "Delete";
            if (file.deletion_status === "pending") {   // already asked: nothing more to press until the admin answers
                del.disabled = true;
                del.textContent = "Delete requested";
            }
            del.addEventListener("click", () => onDelete(file));
            actions.push(del);
        }
        add("nowrap", ...actions);
        return row;
    }));
}
