// Teacher reminders: pick a student (or everyone), write a note, optional due date.
// Uses the same /learning/reminders API the students' Roadmap page reads.
(() => {
    const $ = (id) => document.getElementById(id);
    const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
    const say = (text, bad = false) => {
        $("reminderStatus").textContent = text;
        $("reminderStatus").style.color = bad ? "var(--danger)" : "";
    };

    async function call(path, options = {}) {
        const response = await fetch(API + path, { ...options, headers: { ...auth(), ...(options.headers || {}) } });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
        return body;
    }

    async function loadStudents() {
        const students = await call("/teacher/students");
        const everyone = new Option("Everyone", "");
        $("reminderTarget").replaceChildren(everyone, ...students.map(s =>
            new Option(`${[s.first_name, s.last_name].filter(Boolean).join(" ") || s.username} (${s.username})`, s.username)));
    }

    async function loadReminders() {
        const reminders = await call("/learning/reminders");
        $("noReminders").style.display = reminders.length ? "none" : "";
        $("reminderRows").replaceChildren(...reminders.map(r => {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-danger";
            remove.textContent = "Delete";
            remove.addEventListener("click", async () => {
                try { await call(`/learning/reminders/${r.id}`, { method: "DELETE" }); await loadReminders(); }
                catch (error) { say(error.message, true); }
            });
            const row = document.createElement("tr");
            [r.to, r.message, r.due_date || "—"].forEach(text => {
                const cell = document.createElement("td");
                cell.textContent = text;
                row.append(cell);
            });
            const last = document.createElement("td");
            last.append(remove);
            row.append(last);
            return row;
        }));
    }

    $("reminderSend").addEventListener("click", async () => {
        const message = $("reminderMessage").value.trim();
        if (!message) return say("Write a message first.", true);
        try {
            await call("/learning/reminders", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message,
                    student_username: $("reminderTarget").value || null,
                    due_date: $("reminderDue").value || null,
                }),
            });
            $("reminderMessage").value = "";
            $("reminderDue").value = "";
            say("Reminder sent.");
            await loadReminders();
        } catch (error) {
            say(error.message, true);
        }
    });

    Promise.all([loadStudents(), loadReminders()]).catch(error => say(error.message, true));
})();
