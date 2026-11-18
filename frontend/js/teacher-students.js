// Teacher page: Your Students (teacher-students.html). Share of lessons each student completed, per branch.
// Needs teacher-common.js, utils.js (formatName) and the students table markup of that page.
async function loadStudents() {
    try {
        const res = await fetch(`${API}/teacher/students`, { headers: getHeaders() });
        if (!res.ok) return;
        const students = await res.json();
        const tbody = document.querySelector("#studentsTable tbody");
        const noStudents = document.getElementById("noStudents");

        if (students.length === 0) {
            tbody.replaceChildren();
            noStudents.style.display = "block";
            return;
        }
        noStudents.style.display = "none";
        document.getElementById("studentsHead").replaceChildren(...["Student", "Email", ...students[0].progress.map(p => p.branch), "Mastery"].map(text => {
            const th = document.createElement("th");
            th.textContent = text;
            return th;
        }));

        const rows = students.map(s => {
            const name = formatName(s) || s.username;
            const row = document.createElement("tr");
            const nameCell = document.createElement("td");
            nameCell.textContent = name;
            row.append(nameCell);

            const emailCell = document.createElement("td");
            emailCell.textContent = s.email || "";
            row.append(emailCell);

            for (const item of s.progress) {
                const percent = Math.min(100, Math.max(0, Number(item.percent) || 0));
                const cell = document.createElement("td");
                const track = document.createElement("span");
                track.className = "mini-progress-track";
                const fill = document.createElement("span");
                fill.className = "mini-progress-fill";
                fill.style.width = `${percent}%`;
                track.append(fill);
                cell.append(track, document.createTextNode(`${percent}%`));
                row.append(cell);
            }

            // adaptive levels (rules in backend/adaptive.py): who is stuck, who is ahead
            const masteryCell = document.createElement("td");
            const stuck = document.createElement("span");
            stuck.textContent = `${s.levels.struggling} struggling`;
            if (s.levels.struggling) { stuck.style.color = "var(--danger, #e57373)"; stuck.style.fontWeight = "600"; }
            masteryCell.append(stuck, document.createTextNode(` · ${s.levels.mastered} mastered`));
            row.append(masteryCell);
            return row;
        });
        tbody.replaceChildren(...rows);
    } catch (_) { /* leave table empty on failure */ }
}
loadStudents();

