// Shared hamburger nav drawer. Include this + a <button id="hamburgerBtn">
// in any logged-in page's header, then call initNavDrawer(). Keeps the
// "other tabs / branches" list in one place so adding a real feature later
// means editing this file once, not every page.

const NAV_ITEMS = [
    { label: "Math AI Chat", icon: "\u{1F4AC}", href: "user.html" },
    { label: "Course Materials", icon: "\u{1F4DA}", href: "materials.html" },
    // Reserved for a future branch of the site — swap comingSoon for a real
    // href once it exists.
    { label: "Coming soon", icon: "\u{1F9E9}", comingSoon: true },
];

function initNavDrawer() {
    const overlay = document.createElement("div");
    overlay.className = "nav-drawer-overlay";

    const drawer = document.createElement("div");
    drawer.className = "nav-drawer";

    const itemsHtml = NAV_ITEMS.map(item => {
        if (item.comingSoon) {
            return `<button type="button" class="nav-drawer-item placeholder">${item.icon} ${item.label}</button>`;
        }
        return `<a href="${item.href}" class="nav-drawer-item">${item.icon} ${item.label}</a>`;
    }).join("");

    drawer.innerHTML = `
        <div class="nav-drawer-header">Math AI</div>
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
    drawer.querySelectorAll(".placeholder").forEach(btn => {
        btn.addEventListener("click", () => alert("This section is coming soon — stay tuned!"));
    });
    drawer.querySelector(".nav-drawer-logout").addEventListener("click", () => {
        if (typeof logout === "function") logout();
    });
    wireThemeSwitch("navThemeSwitch");

    const hamburgerBtn = document.getElementById("hamburgerBtn");
    if (hamburgerBtn) hamburgerBtn.addEventListener("click", openDrawer);
}
