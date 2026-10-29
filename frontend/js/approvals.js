// Pending student approvals. Shared by the main admin page and the school admin page; the server decides
// which students each reviewer may see (a school admin only gets their own school), so nothing here sends a
// school id. Needs API, getHeaders(), esc() and the uiConfirm / uiPrompt / uiAlert popups from modal.js.
function approvalName(s) {
    return [s.last_name, [s.first_name, s.middle_name].filter(Boolean).join(" ")].filter(Boolean).join(", ") || s.username;
}

async function loadApprovals() {
    const res = await fetch(`${API}/approvals/pending`, { headers: getHeaders() });
    if (!res.ok) return;
    const rows = await res.json();
    const count = document.getElementById("pendingCount");
    count.textContent = rows.length;
    count.style.display = rows.length ? "" : "none";
    document.getElementById("noPending").style.display = rows.length ? "none" : "block";
    document.getElementById("pendingTable").style.display = rows.length ? "" : "none";
    document.querySelector("#pendingTable tbody").innerHTML = rows.map(s => {
        const flags = [
            s.certificate_reused && `<span class="tag warn">Same file used by another account</span>`,
            s.attempt > 1 && `<span class="tag">Attempt ${s.attempt}</span>`,
        ].filter(Boolean).join(" ");
        const when = s.submitted ? new Date(s.submitted).toLocaleString() : "";
        const u = encodeURIComponent(s.username);
        return `<tr>
            <td>${esc(s.username)}</td><td>${esc(approvalName(s))}</td><td>${esc(s.email)}</td>
            <td>${esc(when)}</td><td style="display:flex; gap:0.3rem; flex-wrap:wrap;">${flags}</td>
            <td><button class="btn btn-secondary" type="button" onclick="viewCertificate('${u}')">View certificate</button></td>
            <td style="white-space:nowrap;">
                <button class="btn btn-primary" type="button" onclick="approveStudent('${u}')">Approve</button>
                <button class="btn btn-danger" type="button" onclick="rejectStudent('${u}')">Reject</button>
            </td></tr>`;
    }).join("");
}

async function viewCertificate(u) {
    // The file is only served to a signed-in reviewer, so it is fetched with the token and shown from a temporary
    // local URL. The tab is opened first, inside the click, so the browser's popup blocker allows it.
    const tab = window.open("", "_blank");
    const res = await fetch(`${API}/approvals/${u}/certificate`, { headers: getHeaders() });
    if (!res.ok) {
        if (tab) tab.close();
        const data = await res.json().catch(() => ({}));
        return uiAlert(data.detail || "Couldn't open the certificate.", { title: "Certificate" });
    }
    const url = URL.createObjectURL(await res.blob());
    if (tab) tab.location.href = url; else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function decide(u, action, body) {
    const res = await fetch(`${API}/approvals/${u}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getHeaders() },
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) await uiAlert(Array.isArray(data.detail) ? "Please give a reason of at least 3 characters." : (data.detail || "That didn't work."), { title: "Couldn't save" });
    loadApprovals();
    if (typeof loadUsers === "function") loadUsers();
}

async function approveStudent(u) {
    if (!await uiConfirm(`Approve ${decodeURIComponent(u)}? They will be able to log in right away.`, { title: "Approve student", okText: "Approve" })) return;
    decide(u, "approve");
}

async function rejectStudent(u) {
    const reason = await uiPrompt("Tell the student why (they will see this):", "", { title: "Reject registration" });
    if (reason === null) return;
    decide(u, "reject", { reason: reason.trim() });
}

loadApprovals();
