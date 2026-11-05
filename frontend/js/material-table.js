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
        indexingRefreshTimer = setTimeout(onRefresh, 5000);
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
        const nameCell = [file.display_name];
        if (file.index_status === "indexing") {
            const note = document.createElement("span");
            note.className = "cell-sub";
            note.textContent = "The AI is reading this file… it can take a few minutes.";
            nameCell.push(note);
        } else if (file.index_status === "failed") {
            const note = document.createElement("span");
            note.className = "cell-sub";
            note.style.color = "var(--danger, #d64545)";
            note.textContent = file.index_error || "The AI couldn't read this file.";
            nameCell.push(note);
        }
        add("file-name", ...nameCell);
        add("", branch);
        if (showUploader) {
            const sub = document.createElement("span");
            sub.className = "cell-sub";
            sub.textContent = file.uploaded_by_name ? `@${file.uploaded_by}` : "";
            add("", file.uploaded_by_name || file.uploaded_by, sub);
        }
        add("nowrap", formatUploadDate(file.uploaded_at));
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary btn-sm";
        button.textContent = "Download";
        button.addEventListener("click", () => downloadMaterial(file));
        const actions = [button];
        if (file.index_status === "failed") {
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
            del.addEventListener("click", () => onDelete(file));
            actions.push(del);
        }
        add("nowrap", ...actions);
        return row;
    }));
}
