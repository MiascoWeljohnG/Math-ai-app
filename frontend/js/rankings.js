// Student rankings table, shared by landing.html (students) and teacher.html (monitoring).
// Needs js/auth.js (for API). Fills the branch dropdown, loads /learning/rankings and reloads on change.
// staff=true adds the username and attempts columns, which the server only sends to teachers/admins.
function initRankings({ select, body, empty, limit = 10, staff = false }) {
    const headers = { Authorization: `Bearer ${localStorage.getItem("token")}` };
    const clock = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}:` : "") +
        `${String(Math.floor((s % 3600) / 60)).padStart(2, s >= 3600 ? "0" : "")}:${String(s % 60).padStart(2, "0")}`;

    select.replaceChildren(new Option("All branches", ""));

    function row(entry) {
        const tr = document.createElement("tr");
        if (entry.you) tr.className = "you";
        const cells = [entry.rank, entry.name + (entry.you ? " (you)" : "")];
        if (staff) cells.push(entry.username);
        cells.push(entry.lessons_passed, `${entry.average_percent}%`, clock(entry.seconds));
        if (staff) cells.push(entry.attempts);
        for (const value of cells) {
            const td = document.createElement("td");
            td.textContent = value;      // names are user-supplied, so never innerHTML
            tr.append(td);
        }
        return tr;
    }

    async function load() {
        const query = new URLSearchParams({ limit });
        if (select.value) query.set("subject_id", select.value);
        try {
            const res = await fetch(`${API}/learning/rankings?${query}`, { headers });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't load the rankings.");
            if (select.options.length === 1) {
                data.branches.forEach(b => select.append(new Option(b.name, b.id)));
            }
            body.replaceChildren(...data.entries.map(row), ...(data.me ? [row(data.me)] : []));
            empty.hidden = data.entries.length > 0;
            empty.textContent = "No quiz scores yet" + (select.value ? " for this branch." : ".");
        } catch (error) {
            body.replaceChildren();
            empty.hidden = false;
            empty.textContent = error.message;
        }
    }

    select.addEventListener("change", load);
    return load();
}
