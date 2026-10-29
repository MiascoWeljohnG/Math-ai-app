// Used by admin.js and teacher.js. With "Auto-detect" selected, the backend saves the files it is
// confident about and sends back the others as `needs_topic`; this asks the uploader which topic
// each of those belongs to, then re-submits them with that choice.
const TOPIC_CHOICES = ["Algebra", "Geometry", "Statistics", "Calculus", "General"];

function topicHint(item) {
    const percent = Math.round((item.confidence || 0) * 100);
    if (item.reason === "not_math") return "This doesn't look like a math document. Pick General if it's meant to be here anyway.";
    if (item.reason === "unavailable") return "The AI couldn't analyze this file right now.";
    if (item.guess) return `The AI isn't sure. Its best guess is ${item.guess} (${percent}% sure).`;
    return "The AI couldn't tell which topic this is.";
}

// Resolves to {"file name": "Algebra", ...}, or null if the uploader cancels.
function askTopics(items) {
    return new Promise((resolve) => {
        const dialog = document.createElement("dialog");
        dialog.style.cssText = "margin:auto; width:min(520px,92vw); padding:1.4rem 1.5rem; border:1px solid var(--field-border); border-radius:10px; background:var(--bg-elevated); color:var(--text); box-shadow:0 10px 40px rgba(0,0,0,.3);";
        const title = document.createElement("h3");
        title.style.cssText = "margin:0 0 .4rem; color:var(--heading);";
        title.textContent = "Which topic does this belong to?";
        const intro = document.createElement("p");
        intro.style.cssText = "margin:0 0 1rem; font-size:.85rem; color:var(--text-muted);";
        intro.textContent = "The AI wasn't sure enough to file these on its own. Choose a topic for each file.";
        dialog.append(title, intro);

        const selects = new Map();
        for (const item of items) {
            const row = document.createElement("div");
            row.style.cssText = "margin-bottom:.9rem;";
            const name = document.createElement("div");
            name.style.cssText = "font-weight:700; overflow-wrap:anywhere;";
            name.textContent = item.filename;
            const hint = document.createElement("div");
            hint.style.cssText = "font-size:.78rem; color:var(--text-muted); margin:.15rem 0 .4rem;";
            hint.textContent = topicHint(item);
            const select = document.createElement("select");
            select.style.cssText = "width:100%; padding:.5rem .7rem; border-radius:6px; border:1px solid var(--border); background:var(--bg-input); color:var(--text); font-size:.9rem;";
            for (const choice of TOPIC_CHOICES) select.add(new Option(choice === "General" ? "General (no specific branch)" : choice, choice));
            select.value = TOPIC_CHOICES.includes(item.guess) ? item.guess : "General";
            selects.set(item.filename, select);
            row.append(name, hint, select);
            dialog.append(row);
        }

        const buttons = document.createElement("div");
        buttons.style.cssText = "display:flex; gap:.6rem; justify-content:flex-end; margin-top:1rem;";
        const cancel = document.createElement("button");
        cancel.type = "button"; cancel.className = "btn"; cancel.textContent = "Cancel";
        const save = document.createElement("button");
        save.type = "button"; save.className = "btn btn-primary"; save.textContent = "Save with these topics";
        buttons.append(cancel, save);
        dialog.append(buttons);

        const finish = (value) => { dialog.close(); dialog.remove(); resolve(value); };
        cancel.addEventListener("click", () => finish(null));
        dialog.addEventListener("cancel", (e) => { e.preventDefault(); finish(null); });   // Esc
        save.addEventListener("click", () => finish(Object.fromEntries([...selects].map(([file, select]) => [file, select.value]))));
        document.body.append(dialog);
        dialog.showModal();
    });
}

async function postUpload(url, headers, files, branch, picked) {
    const formData = new FormData();
    formData.append("branch", branch);
    if (picked) formData.append("branches", JSON.stringify(picked));
    for (const file of files) formData.append("files", file);
    const res = await fetch(url, { method: "POST", headers, body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Upload failed. Please check the files.");
    return data;
}

// Upload `files`; if the AI wants a topic for some, ask and upload those too.
// Returns {message, savedNames: Set, skipped: [names the uploader left unfiled]}.
async function uploadWithTopics(url, headers, files, branch) {
    const first = await postUpload(url, headers, files, branch, null);
    const savedNames = new Set(first.uploaded.map(u => u.filename));
    let message = first.message;
    let skipped = [];
    if (first.needs_topic.length) {
        const picked = await askTopics(first.needs_topic);
        if (picked) {
            const pending = files.filter(f => f.name in picked);
            const second = await postUpload(url, headers, pending, branch, picked);
            second.uploaded.forEach(u => savedNames.add(u.filename));
            message = `Saved and indexed ${savedNames.size} file(s).`;
        } else {
            skipped = first.needs_topic.map(item => item.filename);
            message = `${first.message} Choose a topic (or Cancel to keep them selected) to save the rest.`;
        }
    }
    return { message, savedNames, skipped };
}
