// Shared hamburger nav drawer. Include this + a <button id="hamburgerBtn">
// in any logged-in page's header, then call initNavDrawer(). Keeps the list
// of pages in one place so adding a page means editing this file once.
//
// The item for the page you're currently on stays highlighted (same look as
// the hover effect), and that highlight moves automatically as you navigate,
// because every page builds the drawer and marks its own item as active.

// Line icons (24x24, stroke = currentColor) so they follow the theme colour.
const navIcon = (paths) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;

const NAV_ITEMS = [
    { label: "Home",     icon: navIcon('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/>'), href: "landing.html" },
    { label: "Modules",  icon: navIcon('<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>'), href: "materials.html" },
    { label: "Lessons",  icon: navIcon('<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>'), href: "lessons.html" },
    { label: "Roadmap",  icon: navIcon('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'), href: "roadmap.html" },
    { label: "Profile",  icon: navIcon('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'), href: "profile.html" },
    { label: "iChatbot", icon: navIcon('<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'), href: "user.html" },
];

// File name of the page we're on ("landing.html"). A bare "/" counts as Home.
function currentPageName() {
    const name = window.location.pathname.split("/").pop();
    return (name || "landing.html").toLowerCase();
}

function initNavDrawer() {
    const overlay = document.createElement("div");
    overlay.className = "nav-drawer-overlay";

    const drawer = document.createElement("div");
    drawer.className = "nav-drawer";
    drawer.setAttribute("aria-label", "Main menu");

    const here = currentPageName();
    const itemsHtml = NAV_ITEMS.map(item => {
        const isActive = item.href.toLowerCase() === here;
        return `<a href="${item.href}" class="nav-drawer-item${isActive ? " active" : ""}"${isActive ? ' aria-current="page"' : ""}>` +
               `<span class="nav-icon">${item.icon}</span><span>${item.label}</span></a>`;
    }).join("");

    drawer.innerHTML = `
        <div class="nav-drawer-header"><img src="img/logo.png" alt="iSipnayan"></div>
        <div class="nav-drawer-items">${itemsHtml}</div>
        <div class="nav-drawer-theme-row">
            <span>Theme</span>
            ${themeSwitchHTML("navThemeSwitch")}
        </div>
        <button type="button" class="nav-drawer-logout">Logout</button>
    `;

    document.body.appendChild(overlay);
    document.body.appendChild(drawer);

    function openDrawer() {
        drawer.classList.add("open");
        overlay.classList.add("open");
    }
    function closeDrawer() {
        drawer.classList.remove("open");
        overlay.classList.remove("open");
    }

    overlay.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
    drawer.querySelector(".nav-drawer-logout").addEventListener("click", () => {
        if (typeof logout === "function") logout();
    });
    wireThemeSwitch("navThemeSwitch");

    const hamburgerBtn = document.getElementById("hamburgerBtn");
    if (hamburgerBtn) hamburgerBtn.addEventListener("click", openDrawer);
}
