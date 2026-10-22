// Mobile-only behaviour. Everything here is a no-op on pages that don't have the elements,
// and the controls it adds are hidden on desktop by css/mobile.css, so desktop is unchanged.
(function () {
    const isMobile = () => window.matchMedia("(max-width: 820px)").matches;

    // ---------------- chat page: conversation list as a slide-in sheet ----------------
    const sidebar = document.querySelector(".sidebar");
    const convoList = document.getElementById("convoList");
    if (sidebar && convoList) {
        document.body.classList.add("chat-page");

        const overlay = document.createElement("div");
        overlay.className = "sheet-overlay";
        document.body.appendChild(overlay);

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "chat-toggle m-only";
        toggle.setAttribute("aria-label", "Show conversations");
        toggle.setAttribute("aria-expanded", "false");
        toggle.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> Chats';
        const header = document.querySelector(".app-header");
        if (header) header.appendChild(toggle);

        const setOpen = (open) => {
            sidebar.classList.toggle("open", open);
            overlay.classList.toggle("open", open);
            toggle.setAttribute("aria-expanded", String(open));
        };
        toggle.addEventListener("click", () => setOpen(!sidebar.classList.contains("open")));
        overlay.addEventListener("click", () => setOpen(false));
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
        // Picking a chat (or starting a new one) closes the sheet. Deleting one keeps it open.
        sidebar.addEventListener("click", (e) => {
            if (!isMobile()) return;
            if (e.target.closest(".del-btn")) return;
            if (e.target.closest(".title") || e.target.closest("#newChatBtn")) setOpen(false);
        });
        window.addEventListener("resize", () => { if (!isMobile()) setOpen(false); });
    }

    // ---------------- materials page: file list -> (Read | Ask) tabs ----------------
    const filePanel = document.querySelector(".file-panel");
    const viewerBody = document.querySelector(".viewer-body");
    const mainPane = document.querySelector(".main");
    if (filePanel && viewerBody && mainPane && document.getElementById("fileList")) {
        document.body.classList.add("materials-page");
        document.body.dataset.tab = "read";

        const bar = document.createElement("div");
        bar.className = "m-bar";
        bar.innerHTML =
            '<button type="button" class="m-back" aria-label="Back to the file list">&larr; Files</button>' +
            '<div class="m-tabs" role="tablist">' +
            '<button type="button" role="tab" data-tab="read">Read</button>' +
            '<button type="button" role="tab" data-tab="ask">Ask AI</button></div>' +
            '<a class="m-open" target="_blank" rel="noopener" hidden>Open PDF</a>';
        mainPane.insertBefore(bar, mainPane.firstChild);

        const setTab = (tab) => {
            document.body.dataset.tab = tab;
            bar.querySelectorAll("[data-tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
        };
        setTab("read");

        bar.querySelector(".m-back").addEventListener("click", () => document.body.classList.remove("viewing"));
        bar.querySelector(".m-tabs").addEventListener("click", (e) => {
            const b = e.target.closest("[data-tab]");
            if (b) setTab(b.dataset.tab);
        });
        // materials.js builds the .file-item buttons; opening one switches to the reader on phones.
        document.getElementById("fileList").addEventListener("click", (e) => {
            if (e.target.closest(".file-item") && isMobile()) {
                setTab("read");
                document.body.classList.add("viewing");
            }
        });
        window.addEventListener("resize", () => { if (!isMobile()) document.body.classList.remove("viewing"); });

        // Phones are poor at showing a PDF inside an <iframe> (Android Chrome often shows nothing, iOS
        // Safari only page 1), so offer the file in the phone's own PDF viewer. materials.js swaps the
        // iframe in and out of #pdfPane, so watch for it.
        const openLink = bar.querySelector(".m-open");
        const pdfPane = document.getElementById("pdfPane");
        if (pdfPane) {
            const sync = () => {
                const frame = pdfPane.querySelector("iframe");
                openLink.hidden = !frame;
                if (frame) openLink.href = frame.src;
            };
            new MutationObserver(sync).observe(pdfPane, { childList: true });
            sync();
        }
    }
})();
