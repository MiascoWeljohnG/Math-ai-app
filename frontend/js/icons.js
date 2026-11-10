// Small inline SVG icons for action buttons (Lucide-style outlines, drawn with currentColor
// so they follow the button's text colour in both light and dark themes).
const ICON_PATHS = {
    // arrow pointing down into a tray: "download this file"
    download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    // trash can: "delete"
    trash: '<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    // clock: "waiting for approval"
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    // page with a down arrow: "download as a PDF"
    filePdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6"/><path d="m9.5 15.5 2.5 2.5 2.5-2.5"/>',
};

// Returns an <svg> element. Decorative: the button around it carries the aria-label.
function makeIcon(name, size) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", size || 18);
    svg.setAttribute("height", size || 18);
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.classList.add("action-icon");
    svg.innerHTML = ICON_PATHS[name] || "";   // trusted constants above, never user text
    return svg;
}

// Turns a button into an icon-only button that still has a tooltip and a screen-reader name.
function setIconButton(button, name, label) {
    button.replaceChildren(makeIcon(name));
    button.title = label;
    button.setAttribute("aria-label", label);
}
