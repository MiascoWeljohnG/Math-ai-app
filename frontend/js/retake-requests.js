// "Quiz retake requests" on the teacher page: students whose quiz was ended for violations and are locked out of it
// until a teacher approves their feedback. Reads /retake-requests, answers with /retake-requests/<id>/decision.
// Needs js/auth.js (API), js/modal.js (uiConfirm, uiPrompt) and the #retakeSection markup in teacher.html.
// Exposes loadRetakeRequests() so the notification bell can refresh the list when a new request arrives.
(() => {
    const $ = (id) => document.getElementById(id);
    const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
    const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
    const STATUS = {
        locked:   { text: "Waiting for the student's feedback", tone: "" },
        pending:  { text: "Needs your answer", tone: "warn" },
        approved: { text: "Approved, not retaken yet", tone: "good" },
        rejected: { text: "Rejected", tone: "warn" },
    };

    const say = (text, bad = false) => {
        $("retakeStatus").textContent = text;
        $("retakeStatus").style.color = bad ? "var(--danger)" : "";
    };

    async function call(path, options = {}) {
        const response = await fetch(API + path, { ...options, headers: { ...auth(), ...(options.headers || {}) } });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
        return body;
    }

    const cell = (...children) => {
        const td = document.createElement("td");
        td.append(...children);
        return td;
    };
    const text = (value) => document.createTextNode(value || "");   // names and feedback are user-written: never innerHTML

    function button(label, className, onClick) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `btn btn-sm ${className}`;
        b.textContent = label;
        b.addEventListener("click", onClick);
        return b;
    }

    async function decide(item, approve) {
        let note = null;
        if (approve) {
            const ok = await uiConfirm(`Let ${item.student} retake "${item.lesson}" once?`, { title: "Approve retake", okText: "Approve" });
            if (!ok) return;
        } else {
            note = await uiPrompt(`Tell ${item.student} why (they will see this). You can leave it empty.`, "", { title: "Reject retake", okText: "Reject" });
            if (note === null) return;   // dismissed
        }
        try {
            const result = await call(`/retake-requests/${item.id}/decision`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ approve, note: (note || "").trim() || null }),
            });
            say(result.message);
        } catch (error) {
            say(error.message, true);
        }
        loadRetakeRequests();
    }

    function row(item) {
        const tr = document.createElement("tr");
        const who = document.createElement("div");
        who.append(text(item.student));
        const user = document.createElement("div");
        user.className = "hint";
        user.textContent = `@${item.username}`;

        const quiz = document.createElement("div");
        quiz.append(text(item.lesson));
        const subject = document.createElement("div");
        subject.className = "hint";
        subject.textContent = item.subject;

        const feedback = document.createElement("div");
        feedback.className = "retake-feedback";
        feedback.textContent = item.feedback || "No feedback yet.";
        const stamp = document.createElement("div");
        stamp.className = "hint";
        stamp.textContent = item.requested_at ? `Sent ${when(item.requested_at)}` : `Quiz ended ${when(item.ended_at)}`;
        const note = document.createElement("div");
        note.className = "hint";
        if (item.teacher_note) note.textContent = `Your note: ${item.teacher_note}`;

        const tag = document.createElement("span");
        const info = STATUS[item.status] || { text: item.status, tone: "" };
        tag.className = `tag ${info.tone}`.trim();
        tag.textContent = info.text;
        const decided = document.createElement("div");
        decided.className = "hint";
        if (item.decided_by) decided.textContent = `by ${item.decided_by}, ${when(item.decided_at)}`;

        const actions = document.createElement("div");
        actions.className = "retake-actions";
        if (item.status === "pending") {
            actions.append(button("Approve", "btn-primary", () => decide(item, true)),
                           button("Reject", "btn-danger", () => decide(item, false)));
        }
        tr.append(cell(who, user), cell(quiz, subject), cell(text(String(item.violations))),
                  cell(feedback, stamp, note), cell(tag, decided), cell(actions));
        return tr;
    }

    let latest = 0;   // a slow answer must never overwrite a newer one
    window.loadRetakeRequests = async function loadRetakeRequests() {
        const mine = ++latest;
        try {
            const { pending, items } = await call("/retake-requests");
            if (mine !== latest) return;
            $("retakeRows").replaceChildren(...items.map(row));
            $("retakeWrap").hidden = items.length === 0;
            $("noRetakes").style.display = items.length ? "none" : "";
            $("retakeCount").hidden = pending === 0;
            $("retakeCount").textContent = `${pending} waiting`;
        } catch (error) {
            if (mine === latest) say(error.message, true);
        }
    };

    loadRetakeRequests();
    setInterval(loadRetakeRequests, 30000);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadRetakeRequests(); });
})();
