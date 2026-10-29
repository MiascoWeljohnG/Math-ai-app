const $ = (id) => document.getElementById(id);
const authHeaders = () => ({ "Authorization": `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" });

// Default silhouette used when there's no photo yet
const DEFAULT_AVATAR = "data:image/svg+xml;utf8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#5a6aa0"/><circle cx="50" cy="38" r="17" fill="#e8ebf5"/><path d="M15 100c0-22 15-36 35-36s35 14 35 36Z" fill="#e8ebf5"/></svg>');

// School-year dropdown: previous year through +3
(function fillSchoolYears() {
    const y = new Date().getFullYear();
    let html = '<option value="">Select</option>';
    for (let s = y - 1; s <= y + 2; s++) html += `<option>${s} - ${s + 1}</option>`;
    $("schoolYear").innerHTML = html;
})();

let original = null;     // last saved profile (for Cancel)
let avatarData = null;   // null = unchanged, "" = removed, "data:..." = new photo

function setSelect(sel, value) {
    // Keep values that aren't in the list (e.g. older/typed data) instead of dropping them.
    if (value && ![...sel.options].some(o => o.value === value || o.text === value)) {
        sel.add(new Option(value, value));
    }
    sel.value = value || "";
}

function fill(p) {
    $("lastName").value = p.last_name || "";
    $("firstName").value = p.first_name || "";
    $("middleName").value = p.middle_name || "";
    $("email").value = p.email || "";
    $("contact").value = p.contact_number || "";
    $("birthday").value = /^\d{4}-\d{2}-\d{2}$/.test(p.birthday || "") ? p.birthday : "";
    setSelect($("gender"), p.gender);
    $("address").value = p.address || "";
    $("studentId").value = p.student_id || "";
    // Accounts created through Sign up have their Student ID as the login, so it's locked.
    $("studentId").readOnly = !!p.student_id;
    setSelect($("gradeSection"), p.grade_section);
    setSelect($("strand"), p.strand);
    setSelect($("schoolYear"), p.school_year);
    $("avatarImg").src = p.avatar || DEFAULT_AVATAR;
    avatarData = null;
}

function showMsg(text, kind) {
    const el = $("profileMsg");
    el.textContent = text;
    el.className = `msg ${kind}`;
}

async function load() {
    try {
        const res = await fetch(`${API}/profile`, { headers: authHeaders() });
        if (res.status === 401) return logout();
        if (!res.ok) throw new Error();
        original = await res.json();
        fill(original);
        localStorage.setItem("profile_avatar", original.avatar || "");
        localStorage.setItem("full_name", original.display_name || "");
        localStorage.setItem("first_name", original.first_name || "");
        if (typeof refreshNavProfile === "function") refreshNavProfile();
    } catch (_) {
        showMsg("Couldn't load your profile. Is the server running?", "error");
    }
}

// --- Photo: shrink to a 256px square JPEG in the browser before saving ---
$("changePhoto").addEventListener("click", () => $("photoInput").click());
$("removePhoto").addEventListener("click", () => { avatarData = ""; $("avatarImg").src = DEFAULT_AVATAR; });
$("photoInput").addEventListener("change", () => {
    const file = $("photoInput").files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) return showMsg("Please choose an image file.", "error");
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
        const size = 256, canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        const s = Math.min(img.width, img.height);   // centre-crop to a square
        canvas.getContext("2d").drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
        avatarData = canvas.toDataURL("image/jpeg", 0.85);
        $("avatarImg").src = avatarData;
        URL.revokeObjectURL(url);
        $("photoInput").value = "";
    };
    img.onerror = () => showMsg("That image couldn't be read.", "error");
    img.src = url;
});

// --- Save / Cancel ---
$("profileForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const last_name = $("lastName").value.trim();
    const first_name = $("firstName").value.trim();
    const middle_name = $("middleName").value.trim();
    const email = $("email").value.trim();
    if (!last_name || !first_name) return showMsg("Last name and first name are required.", "error");
    if (email && !/^\S+@\S+\.\S+$/.test(email)) return showMsg("Please enter a valid email address.", "error");

    const body = {
        last_name, first_name, middle_name, email,
        contact_number: $("contact").value.trim(),
        birthday: $("birthday").value,
        gender: $("gender").value,
        address: $("address").value.trim(),
        student_id: $("studentId").value.trim(),
        grade_section: $("gradeSection").value,
        strand: $("strand").value,
        school_year: $("schoolYear").value,
    };
    if (avatarData !== null) body.avatar = avatarData;

    $("saveBtn").disabled = true;
    try {
        const res = await fetch(`${API}/profile`, { method: "PUT", headers: authHeaders(), body: JSON.stringify(body) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Couldn't save changes.");
        original = data;
        fill(data);
        localStorage.setItem("full_name", data.display_name);
        localStorage.setItem("first_name", data.first_name);
        localStorage.setItem("profile_avatar", data.avatar || "");
        if (typeof refreshNavProfile === "function") refreshNavProfile();
        showMsg("Profile saved.", "ok");
    } catch (err) {
        showMsg(err.message, "error");
    } finally {
        $("saveBtn").disabled = false;
    }
});

$("cancelBtn").addEventListener("click", () => {
    if (original) { fill(original); showMsg("Changes discarded.", "ok"); }
    else window.location.href = "landing.html";
});

load();
