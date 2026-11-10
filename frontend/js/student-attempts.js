// "View" on the teacher's Student Scores table: a popup listing every quiz attempt one student made.
// Needs js/auth.js (for API) and the #attemptsDialog markup in teacher.html. Reads /teacher/students/<username>/attempts.
// showStudentAttempts(entry, branch): entry is a rankings row ({username, name}); branch is {id, name} of the table's
// branch filter, so the popup shows the same branch the table is showing.
(function () {
    const $ = (id) => document.getElementById(id);
    const clock = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}:` : "") +
        `${String(Math.floor((s % 3600) / 60)).padStart(2, s >= 3600 ? "0" : "")}:${String(s % 60).padStart(2, "0")}`;
    const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
    let latest = 0;   // a slow answer for an earlier click must never overwrite a newer one

    function cell(text, className) {
        const td = document.createElement("td");
        td.textContent = text;          // lesson titles and names are user-supplied, so never innerHTML
        if (className) td.className = className;
        return td;
    }

    function resultCell(passed) {
        const td = document.createElement("td");
        const tag = document.createElement("span");
        tag.className = "tag " + (passed ? "good" : "warn");
        tag.textContent = passed ? "Passed" : "Failed";
        td.append(tag);
        return td;
    }

    function summaryChip(label, value) {
        const chip = document.createElement("div");
        chip.className = "attempts-chip";
        const strong = document.createElement("strong");
        strong.textContent = value;
        const small = document.createElement("span");
        small.textContent = label;
        chip.append(strong, small);
        return chip;
    }

    function show(data, branch) {
        const rows = data.attempts.map(a => {
            const tr = document.createElement("tr");
            tr.append(
                cell(when(a.at)), cell(a.branch), cell(a.lesson), cell(`#${a.attempt_no}`),
                cell(`${a.score}/${a.total} (${a.percent}%)`), resultCell(a.passed),
                cell(a.seconds == null ? "-" : clock(a.seconds)),
            );
            return tr;
        });
        $("attemptsBody").replaceChildren(...rows);
        $("attemptsTableWrap").hidden = rows.length === 0;
        $("attemptsSummary").hidden = rows.length === 0;
        $("attemptsSummary").replaceChildren(
            summaryChip("attempts", data.summary.attempts),
            summaryChip("passed", data.summary.passed),
            summaryChip("average score", `${data.summary.average_percent}%`),
            summaryChip("total time", clock(data.summary.seconds)),
        );
        $("attemptsEmpty").hidden = rows.length > 0;
        $("attemptsEmpty").textContent = "No quiz attempts yet" + (branch.id ? ` in ${branch.name}.` : ".");
        $("attemptsHint").textContent = (branch.id ? `${branch.name} · ` : "All branches · ") + "newest first" +
            (data.truncated ? " (only the latest are shown)" : "");
    }

    window.showStudentAttempts = async function showStudentAttempts(entry, branch = { id: "", name: "All branches" }) {
        const dialog = $("attemptsDialog");
        const mine = ++latest;
        $("attemptsTitle").textContent = `${entry.name} · quiz attempts`;
        $("attemptsHint").textContent = "Loading...";
        $("attemptsTableWrap").hidden = true;
        $("attemptsSummary").hidden = true;
        $("attemptsEmpty").hidden = true;
        if (!dialog.open) dialog.showModal();

        const query = branch.id ? `?subject_id=${encodeURIComponent(branch.id)}` : "";
        try {
            const res = await fetch(`${API}/teacher/students/${encodeURIComponent(entry.username)}/attempts${query}`, {
                headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(detailText(data, "Couldn't load the attempts."));
            if (mine === latest) show(data, branch);
        } catch (error) {
            if (mine !== latest) return;
            $("attemptsHint").textContent = "";
            $("attemptsEmpty").hidden = false;
            $("attemptsEmpty").textContent = error.message;
        }
    };

    $("attemptsClose").addEventListener("click", () => $("attemptsDialog").close());
})();
