// School admin overview: the four cards at the top of school-admin.html (styles: css/overview.css, helpers: overview.js).
// The numbers come from GET /school-admin/overview, which only ever counts the admin's own school.
//   1. Active accounts  - accounts that can sign in (ring = share of all the school's accounts)
//   2. Files uploaded   - files in the knowledge base
//   3. Active now       - people who used the system in the last few minutes (ring = share of active accounts)
//   4. Needs attention  - students waiting for approval + subject deletions waiting for a decision
let overviewShown = false;     // the first paint animates; the quiet refreshes after it only update the numbers

function plural(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }
function percentOf(part, whole) { return whole ? Math.round(part * 100 / whole) : 0; }
// " · " that sticks to the word before it, so a wrapped line never starts with a dangling dot.
function joinParts(parts) { return parts.join("\u00A0· "); }
// Short and unwrappable: "just now", "5 min ago", "3 h ago", then "Oct 29".
function shortAgo(iso) {
    const seconds = Math.max(0, (Date.now() - new Date(iso)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function paintValue(id, value) {
    const el = document.getElementById(id);
    if (!overviewShown) countUp(el, value, n => String(n));
    else el.textContent = String(value);
}

function paintGauge(id, percent, hint) {
    const gauge = document.getElementById(id);
    if (hint) gauge.title = hint;
    if (!overviewShown) { setGauge(id, percent); return; }
    const pct = Math.max(0, Math.min(100, percent));
    gauge.setAttribute("aria-label", `${pct} percent`);
    gauge.querySelector(".g-fill").style.strokeDashoffset = String(100 - pct);   // the CSS transition glides it there
    gauge.querySelector(".g-pct").textContent = `${pct}%`;
}

function paintAdminOverview(o) {
    const set = (id, text) => { document.getElementById(id).textContent = text; };
    const { accounts, files, online, attention } = o;

    paintValue("ovAccounts", accounts.active);
    paintGauge("ovAccountsGauge", percentOf(accounts.active, accounts.total),
        `${accounts.active} of ${plural(accounts.total, "account")} can sign in (the rest are pending or rejected)`);
    set("ovAccountsSub", joinParts([plural(accounts.students, "student"), plural(accounts.teachers, "teacher"), plural(accounts.admins, "admin")]));

    paintValue("ovFiles", files.total);
    if (!files.total) set("ovFilesSub", "No files uploaded yet");
    else {
        const parts = [`${files.this_week} added this week`];
        if (files.latest) parts.push(`latest ${shortAgo(files.latest)}`);
        set("ovFilesSub", joinParts(parts));
    }

    paintValue("ovOnline", online.now);
    paintGauge("ovOnlineGauge", percentOf(online.now, accounts.active),
        `Made a request in the last ${online.window_minutes} minutes: ${online.now} of ${plural(accounts.active, "active account")}`);
    set("ovOnlineSub", joinParts([`${plural(online.students, "student")} online`, `${plural(online.teachers, "teacher")} online`, `${online.today} seen in 24 h`]));

    const waiting = attention.approvals + attention.deletions;
    paintValue("ovAttention", waiting);
    if (!waiting) set("ovAttentionSub", "Nothing is waiting. You're all caught up.");
    else {
        const parts = [];
        if (attention.approvals) parts.push(plural(attention.approvals, "student approval"));
        if (attention.deletions) parts.push(plural(attention.deletions, "deletion request"));
        if (attention.oldest_approval_days >= 1) parts.push(`oldest waiting ${plural(attention.oldest_approval_days, "day")}`);
        set("ovAttentionSub", joinParts(parts));
    }
    // Jump to whichever list actually has something in it.
    document.getElementById("ovAttentionCard").setAttribute("href", !attention.approvals && attention.deletions ? "#deletionSection" : "#approvalSection");
    overviewShown = true;
}

async function loadAdminOverview() {
    try {
        const res = await fetch(`${API}/school-admin/overview`, { headers: getHeaders() });
        if (!res.ok) throw new Error("overview failed");
        paintAdminOverview(await res.json());
    } catch {
        if (!overviewShown) {   // a bonus panel: the page works without it
            document.getElementById("overviewGrid").hidden = true;
            document.querySelector(".ov-title").hidden = true;
        }                       // after the first success, a failed refresh just leaves the last numbers on screen
    }
}

loadAdminOverview();
// "Active now" changes by the minute, so keep it fresh while the tab is in view.
setInterval(() => { if (document.visibilityState === "visible") loadAdminOverview(); }, 60000);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadAdminOverview(); });
