// A phone on the same Wi-Fi opens this site through the PC's LAN address (e.g. 192.168.1.20), so
// private addresses talk to the backend on that same machine; anything else uses the Render backend.
const IS_LOCAL_HOST = /^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(location.hostname);
const API = IS_LOCAL_HOST
    ? `http://${location.hostname}:8000`
    : "https://isipnayan.onrender.com"; // Render backend

// FastAPI answers validation problems with a list of {msg}; everything else is a plain string.
function detailText(data, fallback) {
    const d = data && data.detail;
    if (Array.isArray(d)) return d.map(e => (e.msg || "").replace(/^Value error, /, "")).filter(Boolean).join(" ") || fallback;
    return d || fallback;
}

const MAX_CERT_BYTES = 5 * 1024 * 1024;
// Cheap checks so a student learns about a wrong file before uploading it. The server re-checks everything
// (it reads the file's real type), so this is only a convenience.
function certificateProblem(file) {
    if (!file) return "Please attach your certificate of enrollment.";
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) return "The certificate must be a PDF, PNG or JPG file.";
    if (file.size > MAX_CERT_BYTES) return "The certificate must be under 5 MB.";
    return "";
}

// Where each role lands after login (and where it is sent when it opens a page that isn't its own)
function homeFor(role) {
    return { school_admin: "school-admin.html", teacher: "teacher.html" }[role] || "landing.html";
}

// --- SHOW / HIDE PASSWORD (works on any page with <button class="eye" data-target="inputId">) ---
// Inline SVGs (same artwork as img/view.svg and img/hide.svg) so they never fail to load
// and follow the theme colour through currentColor.
const EYE_SHOW = '<svg class="eye-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M512 160c320 0 512 352 512 352S832 864 512 864 0 512 0 512s192-352 512-352zm0 64c-225.28 0-384.128 208.064-436.8 288 52.608 79.872 211.456 288 436.8 288 225.28 0 384.128-208.064 436.8-288-52.608-79.872-211.456-288-436.8-288zm0 64a224 224 0 1 1 0 448 224 224 0 0 1 0-448zm0 64a160.192 160.192 0 0 0-160 160c0 88.192 71.744 160 160 160s160-71.808 160-160-71.744-160-160-160z"/></svg>';
const EYE_HIDE = '<svg class="eye-icon" viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true"><path d="M876.8 156.8c0-9.6-3.2-16-9.6-22.4-6.4-6.4-12.8-9.6-22.4-9.6-9.6 0-16 3.2-22.4 9.6L736 220.8c-64-32-137.6-51.2-224-60.8-160 16-288 73.6-377.6 176C44.8 438.4 0 496 0 512s48 73.6 134.4 176c22.4 25.6 44.8 48 73.6 67.2l-86.4 89.6c-6.4 6.4-9.6 12.8-9.6 22.4 0 9.6 3.2 16 9.6 22.4 6.4 6.4 12.8 9.6 22.4 9.6 9.6 0 16-3.2 22.4-9.6l704-710.4c3.2-6.4 6.4-12.8 6.4-22.4Zm-646.4 528c-76.8-70.4-128-128-153.6-172.8 28.8-48 80-105.6 153.6-172.8C304 272 400 230.4 512 224c64 3.2 124.8 19.2 176 44.8l-54.4 54.4C598.4 300.8 560 288 512 288c-64 0-115.2 22.4-160 64s-64 96-64 160c0 48 12.8 89.6 35.2 124.8L256 707.2c-9.6-6.4-19.2-16-25.6-22.4Zm140.8-96c-12.8-22.4-19.2-48-19.2-76.8 0-44.8 16-83.2 48-112 32-28.8 67.2-48 112-48 28.8 0 54.4 6.4 73.6 19.2L371.2 588.8ZM889.599 336c-12.8-16-28.8-28.8-41.6-41.6l-48 48c73.6 67.2 124.8 124.8 150.4 169.6-28.8 48-80 105.6-153.6 172.8-73.6 67.2-172.8 108.8-284.8 115.2-51.2-3.2-99.2-12.8-140.8-28.8l-48 48c57.6 22.4 118.4 38.4 188.8 44.8 160-16 288-73.6 377.6-176C979.199 585.6 1024 528 1024 512s-48.001-73.6-134.401-176Z"/><path d="M511.998 672c-12.8 0-25.6-3.2-38.4-6.4l-51.2 51.2c28.8 12.8 57.6 19.2 89.6 19.2 64 0 115.2-22.4 160-64 41.6-41.6 64-96 64-160 0-32-6.4-64-19.2-89.6l-51.2 51.2c3.2 12.8 6.4 25.6 6.4 38.4 0 44.8-16 83.2-48 112-32 28.8-67.2 48-112 48Z"/></svg>';

function wirePasswordToggles() {
    document.querySelectorAll("button.eye[data-target]").forEach(btn => {
        const input = document.getElementById(btn.dataset.target);
        if (!input) return;
        const paint = () => {
            const shown = input.type === "text";
            btn.innerHTML = shown ? EYE_HIDE : EYE_SHOW;   // slashed eye = "click to hide"
            btn.setAttribute("aria-label", shown ? "Hide password" : "Show password");
            btn.setAttribute("aria-pressed", String(shown));
        };
        paint();   // starts as: password hidden, open eye
        btn.addEventListener("click", () => {
            input.type = input.type === "password" ? "text" : "password";
            paint();
            input.focus({ preventScroll: true });
        });
    });
}
wirePasswordToggles();

// --- LOGIN (only on index.html) ---
const authForm = document.getElementById("authForm");
if (authForm) {
    authForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value;
        const errorEl = document.getElementById("error");
        errorEl.className = "form-msg";

        try {
            const res = await fetch(`${API}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(detailText(data, "Something went wrong"));

            localStorage.setItem("token", data.access_token);
            localStorage.setItem("role", data.role);
            localStorage.setItem("username", username);
            if (data.full_name) localStorage.setItem("full_name", data.full_name);
            if (data.first_name) localStorage.setItem("first_name", data.first_name);

            if (data.school_name) localStorage.setItem("school_name", data.school_name);
            else localStorage.removeItem("school_name");   // the main pool has no school

            window.location.href = homeFor(data.role);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.className = "form-msg error";
        }
    });
}

// --- CREATE ACCOUNT (only on signup.html) ---
const registerForm = document.getElementById("registerForm");
if (registerForm) {
    // Today in the visitor's own timezone (toISOString alone would be UTC and can be a day off).
    const localToday = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

    // Date of birth: type it (MM/DD/YYYY) or pick it from a calendar that has separate Month and Year dropdowns.
    // The hidden #regBirthday keeps the YYYY-MM-DD value the rest of the form already uses.
    const dobText = document.getElementById("regDobText"), dobHidden = document.getElementById("regBirthday");
    const dobBtn = document.getElementById("dobCalBtn"), dobPop = document.getElementById("dobPop");
    const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const pad = (n) => String(n).padStart(2, "0");
    const now = new Date(), thisYear = now.getFullYear(), thisMonth = now.getMonth();
    const minYear = thisYear - 100;
    let viewY = thisYear, viewM = thisMonth;

    function parseDob(text) {   // "03/08/2003" -> "2003-03-08", or "" if it isn't a real date
        const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
        if (!m) return "";
        const mo = +m[1], d = +m[2], y = +m[3];
        const dt = new Date(y, mo - 1, d);
        if (y < 1900 || dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return "";
        return `${y}-${pad(mo)}-${pad(d)}`;
    }

    if (dobText && dobBtn && dobPop) {  // custom DOB widget; plain <input type="date"> still works without it
    dobText.addEventListener("input", () => {   // auto-insert the slashes while typing
        const dg = dobText.value.replace(/\D/g, "").slice(0, 8);
        const f = dg.slice(0, 2) + (dg.length > 2 ? "/" + dg.slice(2, 4) : "") + (dg.length > 4 ? "/" + dg.slice(4) : "");
        if (f !== dobText.value) dobText.value = f;
        dobHidden.value = parseDob(f);
    });

    function renderCal(focusSel) {
        const today = localToday(), sel = dobHidden.value;
        const monthOpts = MONTHS.map((m, i) => `<option value="${i}"${i === viewM ? " selected" : ""}${viewY === thisYear && i > thisMonth ? " disabled" : ""}>${m}</option>`).join("");
        const yearOpts = Array.from({ length: 101 }, (_, i) => thisYear - i).map((y) => `<option${y === viewY ? " selected" : ""}>${y}</option>`).join("");
        const lead = new Date(viewY, viewM, 1).getDay(), count = new Date(viewY, viewM + 1, 0).getDate();
        let days = "";
        for (let i = 0; i < lead; i++) days += "<span></span>";
        for (let d = 1; d <= count; d++) {
            const iso = `${viewY}-${pad(viewM + 1)}-${pad(d)}`;
            days += `<button type="button" class="dob-day${iso === sel ? " sel" : ""}${iso === today ? " today" : ""}" data-iso="${iso}"${iso > today ? " disabled" : ""}>${d}</button>`;
        }
        const prevOff = viewY === minYear && viewM === 0, nextOff = viewY === thisYear && viewM === thisMonth;
        dobPop.innerHTML =
            `<div class="dob-head">
                <button type="button" class="dob-nav" data-nav="-1" aria-label="Previous month"${prevOff ? " disabled" : ""}><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg></button>
                <select id="dobSelM" aria-label="Month">${monthOpts}</select>
                <select id="dobSelY" aria-label="Year">${yearOpts}</select>
                <button type="button" class="dob-nav" data-nav="1" aria-label="Next month"${nextOff ? " disabled" : ""}><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg></button>
            </div>
            <div class="dob-grid">${["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map((w) => `<span class="dow">${w}</span>`).join("")}${days}</div>`;
        if (focusSel) { const el = dobPop.querySelector(focusSel); if (el) el.focus(); }
    }

    function openCal() {
        const iso = dobHidden.value;
        viewY = iso ? Math.min(Math.max(+iso.slice(0, 4), minYear), thisYear) : thisYear;
        viewM = iso ? +iso.slice(5, 7) - 1 : thisMonth;
        if (viewY === thisYear && viewM > thisMonth) viewM = thisMonth;
        dobPop.hidden = false;   // must be visible before it can take focus
        renderCal(".dob-day.sel, .dob-day.today");
        dobBtn.setAttribute("aria-expanded", "true");
    }
    function closeCal(returnFocus) {
        dobPop.hidden = true;
        dobBtn.setAttribute("aria-expanded", "false");
        if (returnFocus) dobBtn.focus();
    }

    dobBtn.addEventListener("click", () => (dobPop.hidden ? openCal() : closeCal(false)));
    dobPop.addEventListener("click", (e) => {
        const nav = e.target.closest("[data-nav]"), day = e.target.closest("[data-iso]");
        if (nav) {
            viewM += +nav.dataset.nav;
            if (viewM < 0) { viewM = 11; viewY--; } else if (viewM > 11) { viewM = 0; viewY++; }
            renderCal(`[data-nav="${nav.dataset.nav}"]`);
        } else if (day) {
            const iso = day.dataset.iso;
            dobHidden.value = iso;
            dobText.value = `${iso.slice(5, 7)}/${iso.slice(8, 10)}/${iso.slice(0, 4)}`;
            closeCal(true);
        }
    });
    dobPop.addEventListener("change", (e) => {   // Month and Year are separate dropdowns
        if (e.target.id === "dobSelM") viewM = +e.target.value;
        if (e.target.id === "dobSelY") { viewY = +e.target.value; if (viewY === thisYear && viewM > thisMonth) viewM = thisMonth; }
        renderCal(`#${e.target.id}`);
    });
    document.addEventListener("click", (e) => {
        if (!dobPop.hidden && !dobPop.contains(e.target) && !dobBtn.contains(e.target)) closeCal(false);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !dobPop.hidden) closeCal(true); });
    }  // end custom date-of-birth widget

    // There are exactly two schools and the student always picks one.
    const schoolSelect = document.getElementById("regSchool");
    fetch(`${API}/schools`).then(r => r.json()).then(schools => {
        schoolSelect.replaceChildren(new Option("Choose your school", ""), ...schools.map(s => new Option(s.name, s.id)));
    }).catch(() => { schoolSelect.replaceChildren(new Option("Couldn't load the schools - refresh the page", "")); });

    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const student_id = document.getElementById("regStudentId").value.trim();
        const last_name = document.getElementById("regLastName").value.trim();
        const first_name = document.getElementById("regFirstName").value.trim();
        const middle_name = document.getElementById("regMiddleName").value.trim();   // optional
        const email = document.getElementById("regEmail").value.trim();
        const birthday = document.getElementById("regBirthday").value;   // YYYY-MM-DD
        const password = document.getElementById("regPassword").value;
        const confirm = document.getElementById("regConfirm").value;
        const errorEl = document.getElementById("regError");
        const submitBtn = document.getElementById("regSubmit");
        errorEl.className = "form-msg";

        const fail = (msg) => { errorEl.textContent = msg; errorEl.className = "form-msg error"; };

        if (dobText && dobText.value.trim() && !birthday) return fail("Please enter a valid date of birth (MM/DD/YYYY).");
        if (!student_id || !last_name || !first_name || !email || !birthday || !password || !confirm) return fail("Please fill in all fields.");
        if (!schoolSelect.value) return fail("Please choose your school.");
        if (!/^\S+@\S+\.\S+$/.test(email)) return fail("Please enter a valid email address.");
        if (birthday > localToday()) return fail("Date of birth cannot be in the future.");
        if (password.length < 8) return fail("Password must be at least 8 characters.");
        if (password !== confirm) return fail("Passwords do not match.");
        const certificate = document.getElementById("regCertificate").files[0];
        const certError = certificateProblem(certificate);
        if (certError) return fail(certError);
        if (!document.getElementById("regTerms").checked) return fail("Please agree to the Terms of Service and Privacy Policy.");

        submitBtn.disabled = true;
        try {
            // multipart (not JSON) because a file goes with it; the browser sets the Content-Type and boundary itself
            const body = new FormData();
            Object.entries({ student_id, last_name, first_name, middle_name, email, birthday, password, school_id: schoolSelect.value })
                .forEach(([k, v]) => body.append(k, v));
            body.append("certificate", certificate);
            const res = await fetch(`${API}/auth/register`, { method: "POST", body });
            const data = await res.json();
            if (!res.ok) throw new Error(detailText(data, "Registration failed"));

            // Nothing to log in to yet: the account waits for a school administrator. Say so in a popup, then go to login.
            registerForm.reset();
            errorEl.textContent = "";
            submitBtn.textContent = "Submitted";
            await uiAlert(
                `${data.message}\n\nYour school admin will check your certificate of enrollment and accept or reject it. ` +
                "If it is rejected you will see the reason when you try to log in, and you can send a new certificate.",
                { title: "Registration submitted", okText: "Go to login" });
            window.location.href = "login.html";
        } catch (err) {
            fail(err.message);
            submitBtn.disabled = false;
        }
    });
}

// --- SEND A NEW CERTIFICATE after a rejection (only on signup.html) ---
const resubmitForm = document.getElementById("resubmitForm");
if (resubmitForm) {
    document.getElementById("resubmitToggle").addEventListener("click", () => { resubmitForm.hidden = !resubmitForm.hidden; });
    resubmitForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = document.getElementById("rsMsg"), btn = document.getElementById("rsSubmit");
        const fail = (t) => { msg.textContent = t; msg.className = "form-msg error"; };
        const student_id = document.getElementById("rsStudentId").value.trim(), password = document.getElementById("rsPassword").value;
        const certificate = document.getElementById("rsCertificate").files[0];
        if (!student_id || !password) return fail("Enter your Student ID and password.");
        const problem = certificateProblem(certificate);
        if (problem) return fail(problem);
        btn.disabled = true;
        try {
            const body = new FormData();
            body.append("student_id", student_id); body.append("password", password); body.append("certificate", certificate);
            const res = await fetch(`${API}/auth/resubmit`, { method: "POST", body });
            const data = await res.json();
            if (!res.ok) throw new Error(detailText(data, "Could not send the certificate"));
            resubmitForm.reset();
            msg.textContent = "";
            await uiAlert(`${data.message}\n\nYou can log in once your school admin accepts it.`, { title: "Certificate sent", okText: "OK" });
        } catch (err) {
            fail(err.message);
        } finally {
            btn.disabled = false;
        }
    });
}

// Password recovery pages submit only the signup username and the one-time token.
if (document.getElementById("forgotForm")) {
    document.getElementById("forgotForm").addEventListener("submit", async e => {
        e.preventDefault();
        const msg = document.getElementById("message");
        try {
            const res = await fetch(`${API}/auth/forgot-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: document.getElementById("username").value.trim() }) });
            const data = await res.json();
            if (!res.ok) throw new Error(detailText(data, "Unable to request a reset"));
            msg.textContent = data.message;
        } catch (err) { msg.textContent = err.message; }
    });
}
if (document.getElementById("resetForm")) {
    const token = new URLSearchParams(location.search).get("token") || "";
    document.getElementById("resetForm").addEventListener("submit", async e => {
        e.preventDefault();
        const msg = document.getElementById("message");
        try {
            const res = await fetch(`${API}/auth/reset-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, password: document.getElementById("newPassword").value }) });
            const data = await res.json();
            if (!res.ok) throw new Error(detailText(data, "Unable to reset password"));
            msg.textContent = data.message;
            document.getElementById("resetForm").hidden = true;
            document.getElementById("loginLink").hidden = false;
        } catch (err) { msg.textContent = err.message; }
    });
}

// --- PROTECT PAGES (works on all pages) ---
function requireAuth() {
    const token = localStorage.getItem("token");
    if (!token) window.location.href = "login.html";
}

function requireRole(expectedRole) {
    const token = localStorage.getItem("token");
    if (!token) { window.location.href = "login.html"; return; }
    if (localStorage.getItem("role") !== expectedRole) {
        window.location.href = homeFor(localStorage.getItem("role"));
    }
}

function logout() {
    const theme = localStorage.getItem("theme");   // keep the light/dark choice
    localStorage.clear();
    if (theme) localStorage.setItem("theme", theme);
    window.location.href = "login.html";
}

// Pages with <span id="schoolBadge"> show the school the signed-in account belongs to
document.addEventListener("DOMContentLoaded", () => {
    const badge = document.getElementById("schoolBadge"), name = localStorage.getItem("school_name");
    if (badge && name) { badge.textContent = name; badge.style.display = ""; }
});

// "Last, First Middle" for tables and pick-lists (the order the school uses). Empty when no name is set.
function formatName(person) {
    if (!person) return "";
    const given = [person.first_name, person.middle_name].filter(Boolean).join(" ");
    return [person.last_name, given].filter(Boolean).join(", ");
}
