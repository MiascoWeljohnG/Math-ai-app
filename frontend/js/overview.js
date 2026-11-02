// Helpers for the overview cards (css/overview.css). Shared by landing.js (students) and
// school-admin-overview.js (school admin), so both pages animate the same way.
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Counts a number up from 0 with an ease-out curve; format(n) turns the running number into the text shown.
function countUp(element, target, format, duration = 1200) {
    if (prefersReducedMotion || !target) { element.textContent = format(target); return; }
    const start = performance.now();
    const step = now => {
        const t = Math.min(1, (now - start) / duration);
        element.textContent = format(Math.round(target * (1 - Math.pow(1 - t, 3))));
        if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}
// Fills a ring gauge (the stroke grows by CSS transition) and counts its percentage up alongside.
function setGauge(id, percent) {
    const gauge = document.getElementById(id);
    const pct = Math.max(0, Math.min(100, percent));
    gauge.setAttribute("aria-label", `${pct} percent`);
    const fill = gauge.querySelector(".g-fill");
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.strokeDashoffset = String(100 - pct); }));
    countUp(gauge.querySelector(".g-pct"), pct, n => `${n}%`);
}
