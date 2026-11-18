// School admin page: Teachers & Students (teachers-students.html) - everyone in the school, and the Add Teacher form.
// Needs school-admin-common.js, modal.js (guardUnsaved) and the users table + #teacherModal markup of that page.
// --- Teachers & students of this school ---
let allUsers = [];

// Display only: the database still stores "user", the table just shows "student".
function roleLabel(role) {
    return role === "user" ? "student" : String(role ?? "").replace("_", " ");
}

function renderUsers() {
    const filter = document.getElementById("roleFilter").value;
    const users = filter === "all" ? allUsers : allUsers.filter(u => u.role === filter);
    document.querySelector("#usersTable tbody").innerHTML = users.map(u => {
        return `<tr><td>${esc(u.username)}</td><td>${esc(u.last_name)}</td><td>${esc(u.first_name)}</td><td>${esc(u.middle_name)}</td><td>${esc(u.email)}</td><td>${esc(roleLabel(u.role))}${u.status && u.status !== "active" ? ` <span class="tag warn">${esc(u.status)}</span>` : ""}</td><td>${esc(u.created)}</td></tr>`;
    }).join("");
    document.getElementById("userCount").textContent = `Showing ${users.length} of ${allUsers.length}`;
}

async function loadUsers() {
    const res = await fetch(`${API}/school-admin/users`, { headers: getHeaders() });
    if (!res.ok) return;
    allUsers = await res.json();
    renderUsers();
}
document.getElementById("roleFilter").addEventListener("change", renderUsers);
loadUsers();

// --- Add a teacher to this school ---
const teacherModal = document.getElementById("teacherModal");
const teacherStatus = document.getElementById("teacherStatus");
const teacherFields = ["teacherUsername", "teacherLastName", "teacherFirstName", "teacherMiddleName", "teacherEmail", "teacherBirthday", "teacherPassword"];
document.getElementById("teacherBirthday").max = new Date().toISOString().slice(0, 10);
const teacherGuard = guardUnsaved(teacherModal, (discarded) => {
    if (discarded) { document.getElementById("teacherForm").reset(); teacherStatus.className = "status"; teacherStatus.textContent = ""; }
    teacherModal.classList.remove("active");
});
document.getElementById("openTeacherModalBtn").addEventListener("click", () => { teacherGuard.reset(); teacherModal.classList.add("active"); });
document.getElementById("closeTeacherModal").addEventListener("click", () => teacherGuard.requestClose());
teacherGuard.attachBackdrop(teacherModal);

document.getElementById("teacherForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const [username, last_name, first_name, middle_name, email, birthday, password] = teacherFields.map(id => document.getElementById(id).value.trim());
    try {
        const res = await fetch(`${API}/school-admin/create-teacher`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getHeaders() },
            body: JSON.stringify({ username, last_name, first_name, middle_name, email, birthday, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        teacherStatus.className = "status success";
        teacherStatus.textContent = data.message;
        teacherFields.forEach(id => { document.getElementById(id).value = ""; });
        loadUsers();
        setTimeout(() => {
            teacherModal.classList.remove("active");
            teacherStatus.className = "status";
            teacherStatus.textContent = "";
        }, 1200);
    } catch (err) {
        teacherStatus.className = "status error";
        teacherStatus.textContent = err.message;
    }
});

// "+ Add Teacher" on the other school admin pages links here with #add-teacher
if (location.hash === "#add-teacher") { teacherGuard.reset(); teacherModal.classList.add("active"); }
