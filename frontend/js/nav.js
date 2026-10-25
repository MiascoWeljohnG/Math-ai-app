// Shared app sidebar. Include this on any logged-in page and call initNavDrawer().
//
//   Student pages:  initNavDrawer()                -> fixed list of pages (NAV_ITEMS below)
//   Dashboards:     initNavDrawer({ staff: true }) -> one link per `.section` on the page, which scrolls to it
//
// On desktop the sidebar is always visible; on phones it is a drawer opened with the hamburger button.
// The link for the page you are on is highlighted, and that highlight follows you as you navigate.

// Line icons (24x24, stroke = currentColor) so they follow the theme colour.
const navIcon = (paths) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;

const ICONS = {
    home:      navIcon('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/>'),
    modules:   navIcon('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>'),
    lessons:   navIcon('<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20v-3"/>'),
    roadmap:   navIcon('<circle cx="6" cy="19" r="2"/><circle cx="18" cy="5" r="2"/><path d="M8 19h7a3.5 3.5 0 0 0 0-7H9a3.5 3.5 0 0 1 0-7h7"/>'),
    profile:   navIcon('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    chat:      navIcon('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'),
    signout:   navIcon('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>'),
    // dashboard sections
    overview:  navIcon('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
    upload:    navIcon('<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>'),
    files:     navIcon('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
    chart:     navIcon('<path d="M5 21V10"/><path d="M12 21V4"/><path d="M19 21v-8"/>'),
    bell:      navIcon('<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'),
    users:     navIcon('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14.2a6.5 6.5 0 0 1 3.5 5.8"/>'),
    school:    navIcon('<path d="M3 21h18"/><path d="M5 21V9l7-5 7 5v12"/><path d="M10 21v-6h4v6"/>'),
    idcard:    navIcon('<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16a3 3 0 0 1 6 0"/><path d="M15 10h3M15 14h3"/>'),
    trash:     navIcon('<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>'),
    warning:   navIcon('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>'),
    dot:       navIcon('<circle cx="12" cy="12" r="3"/>'),
};

const NAV_ITEMS = [
    { label: "Home",     icon: ICONS.home,    href: "landing.html" },
    { label: "Modules",  icon: ICONS.modules, href: "materials.html" },
    { label: "Lessons",  icon: ICONS.lessons, href: "lessons.html" },
    { label: "Roadmap",  icon: ICONS.roadmap, href: "roadmap.html" },
    { label: "Profile",  icon: ICONS.profile, href: "profile.html" },
    { label: "iChatbot", icon: ICONS.chat,    href: "user.html" },
];

const ROLE_LABELS = { user: "Student", teacher: "Instructor", school_admin: "School admin", admin: "Administrator" };

// File name of the page we're on ("landing.html"). A bare "/" counts as Home.
function currentPageName() {
    const name = window.location.pathname.split("/").pop();
    return (name || "landing.html").toLowerCase();
}

function escapeNavText(text) {
    return String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Pick an icon for a dashboard section from its heading.
function iconForSection(title) {
    const t = title.toLowerCase();
    if (/danger|clear/.test(t)) return ICONS.warning;
    if (/upload/.test(t)) return ICONS.upload;
    if (/deletion/.test(t)) return ICONS.trash;
    if (/file|knowledge/.test(t)) return ICONS.files;
    if (/score|ranking|progress/.test(t)) return ICONS.chart;
    if (/reminder/.test(t)) return ICONS.bell;

    if (/school/.test(t) && !/teachers|students/.test(t)) return ICONS.school;
    if (/lesson/.test(t)) return ICONS.lessons;
    if (/user|student|teacher/.test(t)) return ICONS.users;
    return ICONS.dot;
}

// One nav item per dashboard section (a `.section` directly inside `.page`).
function staffItemsFromPage() {
    const sections = [...document.querySelectorAll(".page > .section")];
    const items = [{ label: "Overview", icon: ICONS.overview, target: document.querySelector(".page"), top: true }];
    sections.forEach((section, i) => {
        const h2 = section.querySelector("h2");
        if (!h2) return;
        const clone = h2.cloneNode(true);
        clone.querySelectorAll(".tag, svg").forEach(n => n.remove());
        const label = clone.textContent.replace(/\s+/g, " ").trim();
        if (!label) return;
        if (!section.id) section.id = `sec-${i + 1}`;
        items.push({ label, icon: iconForSection(label), target: section });
    });
    return items;
}

function initialsFor() {
    const first = (localStorage.getItem("first_name") || "").trim();
    const full = (localStorage.getItem("full_name") || "").trim();
    const username = (localStorage.getItem("username") || "").trim();
    return (first || full || username || "?").slice(0, 2).toUpperCase();
}

function profileAvatarHTML() {
    const photo = localStorage.getItem("profile_avatar") || "";
    const initials = initialsFor();
    return photo
        ? `<img class="avatar-photo" src="${escapeNavText(photo)}" alt="" aria-hidden="true">`
        : `<span class="avatar-initials" aria-hidden="true">${escapeNavText(initials)}</span>`;
}

function openAdminProfileModal() {
    const existing = document.getElementById("adminProfileModal");
    if (existing) { existing.remove(); return; }
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay admin-profile-overlay active";
    overlay.id = "adminProfileModal";
    overlay.innerHTML = `
        <section class="modal admin-profile-modal" role="dialog" aria-modal="true" aria-labelledby="adminProfileTitle">
            <button class="close-btn" type="button" aria-label="Close">&times;</button>
            <p class="admin-profile-eyebrow">ACCOUNT SETTINGS</p>
            <h2 id="adminProfileTitle">Your profile</h2>
            <p class="admin-profile-intro">Review your account details below. Choose Edit profile when you’re ready to make changes.</p>
            <section class="admin-profile-preview" id="adminProfilePreview" aria-label="Current profile information" aria-live="polite">
                <div class="admin-profile-preview-top"><div class="admin-profile-preview-avatar" id="adminPreviewInitials">?</div><button type="button" class="btn-primary" id="adminEditProfile">Edit profile</button></div>
                <dl class="admin-profile-preview-list">
                    <div><dt>Full name</dt><dd id="adminPreviewName">Loading…</dd></div>
                    <div><dt>Username</dt><dd id="adminPreviewUsername">Loading…</dd></div>
                    <div><dt>Email</dt><dd id="adminPreviewEmail">Loading…</dd></div>
                    <div><dt>School</dt><dd id="adminPreviewSchool">—</dd></div>
                </dl>
            </section>
            <form class="admin-profile-form" id="adminProfileForm" hidden>
                <button type="button" class="admin-profile-back" id="adminProfileBack">← Back to profile</button>
                <div class="admin-profile-grid">
                    <label>First name<input name="first_name" autocomplete="given-name" required maxlength="100"></label>
                    <label>Last name<input name="last_name" autocomplete="family-name" required maxlength="100"></label>
                    <label>Middle name <span>(optional)</span><input name="middle_name" autocomplete="additional-name" maxlength="100"></label>
                    <label>Email<input name="email" type="email" autocomplete="email" maxlength="254"></label>
                    <label class="admin-profile-wide">Username<input name="username" autocomplete="username" required maxlength="80"></label>
                </div>
                <p class="admin-profile-message" id="adminProfileMessage" role="status" aria-live="polite"></p>
                <div class="admin-profile-actions"><button type="submit" class="btn-primary">Save profile</button><button type="button" class="btn btn-secondary" data-close>Cancel</button></div>
            </form>
            <div class="admin-password-section">
                <button type="button" class="admin-password-toggle" id="adminPasswordToggle" aria-expanded="false" aria-controls="adminPasswordPanel">Change password</button>
                <div id="adminPasswordPanel" hidden>
                    <p>Confirm your current password before setting a new one.</p>
                    <form id="adminPasswordForm">
                        <label>Current password<input name="current_password" type="password" autocomplete="current-password" required></label>
                        <label>New password<input name="new_password" type="password" autocomplete="new-password" minlength="8" required></label>
                        <label>Confirm new password<input name="confirm_password" type="password" autocomplete="new-password" minlength="8" required></label>
                        <p class="admin-profile-message" id="adminPasswordMessage" role="status" aria-live="polite"></p>
                        <div class="admin-profile-actions"><button type="submit" class="btn-primary">Update password</button></div>
                    </form>
                </div>
            </div>
        </section>`;
    document.body.appendChild(overlay);
    const form = overlay.querySelector("#adminProfileForm");
    const preview = overlay.querySelector("#adminProfilePreview");
    const passForm = overlay.querySelector("#adminPasswordForm");
    const passToggle = overlay.querySelector("#adminPasswordToggle");
    const passPanel = overlay.querySelector("#adminPasswordPanel");
    passToggle.addEventListener("click", () => {
        const expanded = passToggle.getAttribute("aria-expanded") === "true";
        passToggle.setAttribute("aria-expanded", String(!expanded));
        passPanel.hidden = expanded;
    });
    const close = () => overlay.remove();
    const showEditor = () => { preview.hidden = true; form.hidden = false; form.elements.first_name.focus(); };
    const showPreview = () => { form.hidden = true; preview.hidden = false; overlay.querySelector("#adminEditProfile").focus(); };
    overlay.querySelector("#adminEditProfile").addEventListener("click", showEditor);
    overlay.querySelector("#adminProfileBack").addEventListener("click", showPreview);
    overlay.querySelector(".close-btn").addEventListener("click", close);
    overlay.querySelector("[data-close]").addEventListener("click", close);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    const escape = (e) => { if (e.key === "Escape") { close(); document.removeEventListener("keydown", escape); } };
    document.addEventListener("keydown", escape);
    const authHeaders = () => ({ "Authorization": `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" });
    const msg = (id, text, good = false) => { const el = overlay.querySelector(id); el.textContent = text; el.className = `admin-profile-message ${good ? "is-ok" : "is-error"}`; };
    fetch(`${API}/profile`, { headers: authHeaders() }).then(async res => {
        if (res.status === 401) { if (typeof logout === "function") logout(); throw new Error("Your session expired. Please sign in again."); }
        const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Couldn't load profile.");
        for (const key of ["first_name", "last_name", "middle_name", "email", "username"]) form.elements[key].value = data[key] || "";
        const name = [data.first_name, data.middle_name, data.last_name].filter(Boolean).join(" ") || "—";
        overlay.querySelector("#adminPreviewName").textContent = name;
        overlay.querySelector("#adminPreviewUsername").textContent = data.username || "—";
        overlay.querySelector("#adminPreviewEmail").textContent = data.email || "Not provided";
        overlay.querySelector("#adminPreviewSchool").textContent = data.school_name || localStorage.getItem("school_name") || "—";
        overlay.querySelector("#adminPreviewInitials").textContent = `${(data.first_name || "?")[0]}${(data.last_name || "")[0] || ""}`.toUpperCase();
    }).catch(err => msg("#adminProfileMessage", err.message));
    form.addEventListener("submit", async (e) => {
        e.preventDefault(); const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
        const body = Object.fromEntries(["first_name", "last_name", "middle_name", "email", "username"].map(k => [k, form.elements[k].value.trim()]));
        try {
            const res = await fetch(`${API}/profile/account`, { method: "PUT", headers: authHeaders(), body: JSON.stringify(body) });
            const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Couldn't save profile.");
            localStorage.setItem("username", data.username); localStorage.setItem("first_name", data.first_name); localStorage.setItem("full_name", data.display_name);
            drawer.querySelector(".nav-user-name").textContent = data.display_name;
            drawer.querySelector(".avatar-initials").textContent = `${data.first_name[0]}${data.last_name[0]}`.toUpperCase();
            overlay.querySelector("#adminPreviewName").textContent = [data.first_name, data.middle_name, data.last_name].filter(Boolean).join(" ") || "—";
            overlay.querySelector("#adminPreviewUsername").textContent = data.username || "—";
            overlay.querySelector("#adminPreviewEmail").textContent = data.email || "Not provided";
            overlay.querySelector("#adminPreviewInitials").textContent = `${(data.first_name || "?")[0]}${(data.last_name || "")[0] || ""}`.toUpperCase();
            msg("#adminProfileMessage", "Profile saved.", true);
            showPreview();
        } catch (err) { msg("#adminProfileMessage", err.message); } finally { submit.disabled = false; }
    });
    passForm.addEventListener("submit", async (e) => {
        e.preventDefault(); const submit = passForm.querySelector('[type="submit"]');
        const fresh = passForm.elements.new_password.value;
        if (fresh !== passForm.elements.confirm_password.value) return msg("#adminPasswordMessage", "The new passwords don't match.");
        if (fresh === passForm.elements.current_password.value) return msg("#adminPasswordMessage", "Choose a password you haven't used before.");
        submit.disabled = true;
        try {
            const res = await fetch(`${API}/profile/password`, { method: "PUT", headers: authHeaders(), body: JSON.stringify({ current_password: passForm.elements.current_password.value, new_password: fresh }) });
            const data = await res.json(); if (!res.ok) throw new Error(data.detail || "Couldn't update password.");
            passForm.reset(); msg("#adminPasswordMessage", "Password updated.", true);
        } catch (err) { msg("#adminPasswordMessage", err.message); } finally { submit.disabled = false; }
    });
    overlay.querySelector(".close-btn").focus();
}

function initNavDrawer(options = {}) {
    const staff = !!options.staff;
    const role = localStorage.getItem("role") || "user";
    const here = currentPageName();

    // Chat and Modules have their own inner sidebar, so the main one shrinks to an icon rail there.
    if (!staff && document.querySelector("#convoList, .file-panel")) document.body.classList.add("nav-rail");
    document.body.classList.add("has-sidebar");

    const overlay = document.createElement("div");
    overlay.className = "nav-drawer-overlay";

    const drawer = document.createElement("aside");
    drawer.className = "nav-drawer";
    drawer.setAttribute("aria-label", "Main menu");

    const items = staff ? staffItemsFromPage() : NAV_ITEMS;
    const itemsHtml = items.map((item, i) => {
        const label = escapeNavText(item.label);
        if (staff) {
            return `<a href="#" class="nav-drawer-item${i === 0 ? " active" : ""}" title="${label}">` +
                   `<span class="nav-icon">${item.icon}</span><span class="nav-label">${label}</span></a>`;
        }
        const isActive = item.href.toLowerCase() === here;
        return `<a href="${item.href}" class="nav-drawer-item${isActive ? " active" : ""}"${isActive ? ' aria-current="page"' : ""} title="${label}">` +
               `<span class="nav-icon">${item.icon}</span><span class="nav-label">${label}</span></a>`;
    }).join("");

    const displayName = localStorage.getItem("full_name") || localStorage.getItem("username") || "";
    const schoolName = localStorage.getItem("school_name");
    const roleLine = [ROLE_LABELS[role] || "Student", schoolName].filter(Boolean).join(" · ");
    const userTag = staff ? "button type=\"button\"" : "a";
    const userHref = staff ? "" : ' href="profile.html"';

    drawer.innerHTML = `
        <div class="nav-drawer-header"><a class="brand-lockup" href="${staff ? "#" : "landing.html"}"><span class="brand-mark" aria-hidden="true"></span>IsipNayan</a></div>
        <nav class="nav-drawer-items">${itemsHtml}</nav>
        <div class="nav-drawer-foot">
            <div class="nav-drawer-theme-row"><span>Theme</span>${themeSwitchHTML("navThemeSwitch")}</div>
            <button type="button" class="nav-theme-compact" aria-label="Toggle dark / light mode" title="Toggle dark / light mode">${navIcon('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>')}</button>
            <button type="button" class="nav-drawer-item nav-drawer-logout" title="Sign out"><span class="nav-icon">${ICONS.signout}</span><span class="nav-label">Sign out</span></button>
            <${userTag} class="nav-user"${userHref} aria-label="${staff ? "Open admin profile settings" : "Open profile"}">
                ${profileAvatarHTML()}
                <span class="nav-user-text"><span class="nav-user-name">${escapeNavText(displayName)}</span><span class="nav-user-role">${escapeNavText(roleLine)}</span></span>
            </${userTag}>
        </div>
    `;

    document.body.appendChild(overlay);
    document.body.appendChild(drawer);

    const openDrawer = () => { drawer.classList.add("open"); overlay.classList.add("open"); };
    const closeDrawer = () => { drawer.classList.remove("open"); overlay.classList.remove("open"); };

    overlay.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
    drawer.querySelector(".nav-drawer-logout").addEventListener("click", () => { if (typeof logout === "function") logout(); });
    if (staff) drawer.querySelector(".nav-user").addEventListener("click", openAdminProfileModal);
    window.refreshNavProfile = () => {
        const name = localStorage.getItem("full_name") || localStorage.getItem("username") || "";
        const navUser = drawer.querySelector(".nav-user");
        if (navUser) {
            navUser.innerHTML = `${profileAvatarHTML()}<span class="nav-user-text"><span class="nav-user-name">${escapeNavText(name)}</span><span class="nav-user-role">${escapeNavText(roleLine)}</span></span>`;
        }
    };
    drawer.querySelector(".nav-theme-compact").addEventListener("click", () => {
        toggleTheme();
        const sw = document.getElementById("navThemeSwitch");
        if (sw) sw.checked = document.documentElement.getAttribute("data-theme") === "dark";
    });
    wireThemeSwitch("navThemeSwitch");

    // Hamburger: student pages already have one in their header; dashboards get one added.
    let hamburgerBtn = document.getElementById("hamburgerBtn");
    if (!hamburgerBtn && staff) {
        const bar = document.querySelector(".page > .header");
        if (bar) {
            hamburgerBtn = document.createElement("button");
            hamburgerBtn.type = "button";
            hamburgerBtn.id = "hamburgerBtn";
            hamburgerBtn.className = "hamburger-btn staff-hamburger";
            hamburgerBtn.setAttribute("aria-label", "Menu");
            hamburgerBtn.innerHTML = "<span></span><span></span><span></span>";
            bar.prepend(hamburgerBtn);
        }
    }
    if (hamburgerBtn) hamburgerBtn.addEventListener("click", openDrawer);

    if (!staff) return;

    // ---- dashboards: links scroll to their section, and the current section stays highlighted ----
    const links = [...drawer.querySelectorAll(".nav-drawer-items .nav-drawer-item")];
    const setActive = (index) => links.forEach((a, i) => {
        a.classList.toggle("active", i === index);
        if (i === index) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    links.forEach((a, i) => a.addEventListener("click", (e) => {
        e.preventDefault();
        const item = items[i];
        if (item.top) window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
        else item.target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        setActive(i);
        closeDrawer();
    }));
    drawer.querySelector(".brand-lockup").addEventListener("click", (e) => { e.preventDefault(); links[0].click(); });

    // follow the scroll: the active link is the last section whose top has passed the upper third of the screen
    let ticking = false;
    window.addEventListener("scroll", () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            ticking = false;
            const line = window.innerHeight * 0.33;
            let current = 0;
            items.forEach((item, i) => { if (!item.top && item.target.getBoundingClientRect().top <= line) current = i; });
            setActive(current);
        });
    }, { passive: true });
}
