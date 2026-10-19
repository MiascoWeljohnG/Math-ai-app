// Registered student numbers: paste a list, see who has signed up, remove typos.
// Shared by the main admin page (any school) and the school admin page (their own school only);
// the server decides which school applies. Needs getHeaders() and esc() from the page's own script.
let registryBase = "";

function initRegistry(base) {   // base: "/admin" or "/school-admin"
    registryBase = base;
    loadRegistry();
}

async function loadRegistry() {
    const res = await fetch(`${API}${registryBase}/registered-students`, { headers: getHeaders() });
    if (!res.ok) return;
    const rows = await res.json();
    document.querySelector("#registryTable tbody").innerHTML = rows.map(r => `<tr>
        <td>${esc(r.student_number)}</td><td>${esc(r.school || "Main")}</td>
        <td>${r.signed_up ? "Signed up" : "Waiting to sign up"}</td>
        <td>${r.signed_up ? "" : `<button class="btn btn-secondary" type="button" onclick="removeRegistered(${r.id})">Remove</button>`}</td>
    </tr>`).join("");
    document.getElementById("registryTable").style.display = rows.length ? "" : "none";
    document.getElementById("registryCount").textContent = rows.length
        ? `${rows.length} registered, ${rows.filter(r => r.signed_up).length} signed up`
        : "No student numbers registered yet.";
}

async function addRegistered() {
    const box = document.getElementById("registryNumbers"), status = document.getElementById("registryStatus");
    const schoolSelect = document.getElementById("registrySchool");   // only on the main admin page
    const body = { numbers: box.value };
    if (schoolSelect) body.school_id = schoolSelect.value ? Number(schoolSelect.value) : null;
    const res = await fetch(`${API}${registryBase}/registered-students`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getHeaders() },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
        status.className = "status error";
        status.textContent = data.detail;
        return;
    }
    const skipped = data.skipped.slice(0, 5).map(s => `${s.number} (${s.reason})`).join(", ");
    const more = data.skipped.length > 5 ? ` and ${data.skipped.length - 5} more` : "";
    status.className = "status success";
    status.textContent = `Added ${data.added}.` + (data.skipped.length ? ` Skipped ${data.skipped.length}: ${skipped}${more}.` : "");
    box.value = "";
    loadRegistry();
}

async function removeRegistered(id) {
    if (!await uiConfirm("Remove this student number from the list?", { title: "Remove student number", okText: "Remove" })) return;
    const res = await fetch(`${API}${registryBase}/registered-students/${id}`, { method: "DELETE", headers: getHeaders() });
    if (!res.ok) {
        const status = document.getElementById("registryStatus");
        status.className = "status error";
        status.textContent = (await res.json()).detail;
        return;
    }
    loadRegistry();
}
