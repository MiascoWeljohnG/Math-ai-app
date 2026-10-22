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

// Teacher table: File | Branch | Uploaded.  Admin table (showUploader): File | Branch | Uploaded by | Uploaded.
// Pass onDelete (admin page only) to add a Delete button next to Download.
function renderMaterialRows(tbody, files, showUploader, onDelete) {
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
        add("file-name", file.display_name);
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
