// The top bar of the school admin and teacher pages: the dashboard name, the school badge, the notification bell and,
// on the school admin pages, the "+ Add Teacher" shortcut. Every page has one empty <div class="header" id="staffHeader">
// followed by this script, so the bar (and the bell's markup) is written once, here.
//
//   data-title        the dashboard name ("School Admin", "Teacher Dashboard")
//   data-add-teacher  "button" opens the Add Teacher form on this page; "link" goes to the page that has it
//
// The bell itself is wired by school-admin-bell.js / teacher-bell.js, which each page loads after this one.
(function () {
    const bar = document.getElementById("staffHeader");
    if (!bar) return;
    const escapeText = (text) => String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    let addTeacher = "";
    if (bar.dataset.addTeacher === "button") {
        addTeacher = `<button class="btn btn-secondary" id="openTeacherModalBtn" type="button">+ Add Teacher</button>`;
    } else if (bar.dataset.addTeacher === "link") {
        addTeacher = `<a class="btn btn-secondary" id="openTeacherModalBtn" href="teachers-students.html#add-teacher">+ Add Teacher</a>`;
    }

    // "Teacher Dashboard" becomes "<span id="dashboardOwner">Teacher</span> Dashboard" so nav.js can swap in the person's name.
    const title = bar.dataset.title || "";
    const owned = /^(\w+) Dashboard$/.exec(title);
    const heading = owned ? `<span id="dashboardOwner">${escapeText(owned[1])}</span> Dashboard` : escapeText(title);

    bar.innerHTML = `
        <h1>${heading} <span class="tag" id="schoolBadge" style="display:none;"></span></h1>
        <div class="header-actions">
            ${addTeacher}
            <div class="bell-wrap" id="bellWrap">
                <button type="button" class="btn btn-secondary bell-btn" id="bellBtn" aria-label="Notifications" aria-haspopup="true" aria-expanded="false">
                    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
                    <span class="bell-badge" id="bellBadge" style="display:none;">0</span>
                </button>
                <div class="bell-panel" id="bellPanel" role="dialog" aria-label="Notifications">
                    <div class="bell-head">
                        <strong>Notifications</strong>
                        <span class="bell-head-actions">
                            <button type="button" class="link-btn" id="bellReadAll">Mark all read</button>
                            <button type="button" class="link-btn" id="bellClear">Clear</button>
                        </span>
                    </div>
                    <div class="bell-list" id="bellList"></div>
                    <p class="empty bell-empty" id="bellEmpty">You're all caught up.</p>
                </div>
            </div>
        </div>`;
})();
