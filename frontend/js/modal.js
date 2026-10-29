// Popup modals that replace the browser's native alert() / confirm() / prompt()
// (the ones headed "localhost says"). All three return a Promise, so call them
// with `await`:
//   await uiAlert("Saved.");
//   if (!await uiConfirm("Delete this?", { okText: "Delete", danger: true })) return;
//   const reason = await uiPrompt("Why?", "");   // string, or null if cancelled
// Styling uses the theme variables from css/theme.css, so dark mode just works.
(function () {
    const style = document.createElement("style");
    style.textContent = `
    /* A native <dialog> (showModal) so the popup also sits above other open dialogs, e.g. the add-subject one. */
    dialog.ui-modal-backdrop { position: fixed; inset: 0; width: 100%; height: 100%; max-width: none; max-height: none; margin: 0; border: 0;
        padding: 16px; box-sizing: border-box; background: rgba(0, 0, 0, 0.5); color: inherit; overflow: hidden; animation: ui-modal-fade 0.12s ease-out; }
    dialog.ui-modal-backdrop[open] { display: flex; align-items: center; justify-content: center; }
    dialog.ui-modal-backdrop::backdrop { background: transparent; }
    .ui-modal { width: 100%; max-width: 420px; max-height: 90vh; overflow-y: auto; box-sizing: border-box; padding: 22px;
        background: var(--bg-elevated, #fff); color: var(--text, #1b2a1d); border: 1px solid var(--border, #cfd8cf);
        border-radius: 14px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3); font-family: inherit; animation: ui-modal-pop 0.14s ease-out; }
    .ui-modal h2 { margin: 0 0 10px; font-size: 1.15rem; color: var(--heading, var(--text, #0b4a12)); }
    .ui-modal p { margin: 0; line-height: 1.5; white-space: pre-line; overflow-wrap: anywhere; }
    .ui-modal input { width: 100%; box-sizing: border-box; margin-top: 14px; padding: 10px 12px; font: inherit;
        color: var(--text, #1b2a1d); background: var(--bg-input, #fff); border: 1px solid var(--field-border, #2b2b2b); border-radius: 8px; }
    .ui-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
    .ui-modal-actions button { padding: 9px 18px; font: inherit; font-weight: 600; cursor: pointer; border-radius: 8px; border: 1px solid transparent; }
    .ui-modal-actions .ui-cancel { background: transparent; color: var(--text, #1b2a1d); border-color: var(--border, #cfd8cf); }
    .ui-modal-actions .ui-cancel:hover { background: var(--hover-bg, #e6f0df); }
    .ui-modal-actions .ui-ok { background: var(--accent, #65964f); color: #fff; }
    .ui-modal-actions .ui-ok:hover { background: var(--accent-hover, #55813f); }
    .ui-modal-actions .ui-ok.danger { background: var(--danger, #d64545); }
    .ui-modal-actions .ui-ok.danger:hover { background: var(--danger-hover, #b93636); }
    @keyframes ui-modal-fade { from { opacity: 0; } to { opacity: 1; } }
    @keyframes ui-modal-pop { from { opacity: 0; transform: translateY(8px) scale(0.98); } to { opacity: 1; transform: none; } }`;
    document.head.appendChild(style);

    // kind: "alert" | "confirm" | "prompt". Resolves with true/false, or the typed text / null for prompts.
    function openModal(kind, message, opts) {
        opts = opts || {};
        return new Promise(resolve => {
            const previouslyFocused = document.activeElement;
            const backdrop = document.createElement("dialog");
            backdrop.className = "ui-modal-backdrop";
            const modal = document.createElement("div");
            modal.className = "ui-modal";
            modal.setAttribute("role", kind === "alert" ? "alertdialog" : "dialog");
            modal.setAttribute("aria-modal", "true");

            const title = opts.title || (kind === "alert" ? "Notice" : kind === "confirm" ? "Please confirm" : "Enter details");
            const heading = document.createElement("h2");
            heading.textContent = title;
            const text = document.createElement("p");
            text.textContent = message; // textContent, so messages containing user text can't inject HTML
            modal.append(heading, text);

            let input = null;
            if (kind === "prompt") {
                input = document.createElement("input");
                input.type = "text";
                input.value = opts.defaultValue || "";
                modal.appendChild(input);
            }

            const actions = document.createElement("div");
            actions.className = "ui-modal-actions";
            let cancelBtn = null;
            if (kind !== "alert") {
                cancelBtn = document.createElement("button");
                cancelBtn.type = "button";
                cancelBtn.className = "ui-cancel";
                cancelBtn.textContent = opts.cancelText || "Cancel";
                actions.appendChild(cancelBtn);
            }
            const okBtn = document.createElement("button");
            okBtn.type = "button";
            okBtn.className = "ui-ok" + (opts.danger ? " danger" : "");
            okBtn.textContent = opts.okText || "OK";
            actions.appendChild(okBtn);
            modal.appendChild(actions);
            backdrop.appendChild(modal);
            document.body.appendChild(backdrop);
            backdrop.showModal();
            backdrop.addEventListener("cancel", e => { e.preventDefault(); dismiss(); }); // native Esc

            function close(value) {
                document.removeEventListener("keydown", onKey, true);
                backdrop.remove();
                if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
                resolve(value);
            }
            const accept = () => close(kind === "prompt" ? input.value : true);
            const dismiss = () => close(kind === "prompt" ? null : false);

            function onKey(e) {
                if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dismiss(); }
                else if (e.key === "Enter" && document.activeElement !== cancelBtn) { e.preventDefault(); e.stopPropagation(); accept(); }
                else if (e.key === "Tab") { // keep keyboard focus inside the popup
                    const items = [input, cancelBtn, okBtn].filter(Boolean);
                    const i = items.indexOf(document.activeElement);
                    e.preventDefault();
                    items[(i + (e.shiftKey ? items.length - 1 : 1)) % items.length].focus();
                }
            }
            document.addEventListener("keydown", onKey, true);
            okBtn.addEventListener("click", accept);
            if (cancelBtn) cancelBtn.addEventListener("click", dismiss);
            backdrop.addEventListener("mousedown", e => { if (e.target === backdrop) dismiss(); });

            (input || (opts.danger && cancelBtn) || okBtn).focus(); // dangerous actions start on Cancel
            if (input) input.select();
        });
    }

    window.uiAlert = (message, opts) => openModal("alert", message, opts);
    window.uiConfirm = (message, opts) => openModal("confirm", message, opts);
    window.uiPrompt = (message, defaultValue, opts) => openModal("prompt", message, Object.assign({ defaultValue }, opts));

    // ---- Unsaved-changes guard for popups that contain a form -------------------------------------
    //   const guard = guardUnsaved(overlay, (discarded) => overlay.classList.remove("active"));
    //   guard.reset();                    // when the popup opens, and after a successful save
    //   closeBtn.onclick = () => guard.requestClose();
    //   guard.attachBackdrop(overlay);    // clicking outside the popup goes through the same check
    // requestClose() closes straight away if nothing was typed; otherwise it asks "Leave without saving?" first.
    window.confirmDiscard = () => uiConfirm(
        "You've entered information that hasn't been saved yet. If you leave now, it will be lost.",
        { title: "Leave without saving?", okText: "Discard changes", cancelText: "Keep editing", danger: true });

    window.guardUnsaved = function (roots, closeFn) {
        const list = (Array.isArray(roots) ? roots : [roots]).filter(Boolean);
        const read = root => Array.from(root.querySelectorAll("input, select, textarea"))
            .map(el => (el.type === "checkbox" || el.type === "radio") ? String(el.checked) : el.value).join("\u0001");
        const baselines = new Map();
        const reset = root => (root ? [root] : list).forEach(r => baselines.set(r, read(r)));
        const isDirty = () => list.some(r => read(r) !== baselines.get(r));
        let asking = false, askedAt = 0;
        reset();

        async function requestClose(opts) {
            if (asking) return false;
            // the click that dismisses the "Keep editing" popup must not re-open the question
            if (opts && opts.fromBackdrop && Date.now() - askedAt < 400) return false;
            let discarded = false;
            if (isDirty()) {
                asking = true;
                const leave = await window.confirmDiscard();
                asking = false; askedAt = Date.now();
                if (!leave) return false;
                discarded = true;
            }
            closeFn(discarded);
            return true;
        }

        // Only a click that both started and ended on the dark backdrop counts, so dragging a text
        // selection out of the popup no longer closes it.
        function attachBackdrop(overlay) {
            let downOnBackdrop = false;
            overlay.addEventListener("mousedown", e => { downOnBackdrop = e.target === overlay; });
            overlay.addEventListener("click", e => {
                const hit = e.target === overlay && downOnBackdrop;
                downOnBackdrop = false;
                if (hit) requestClose({ fromBackdrop: true });
            });
        }
        return { isDirty, reset, requestClose, attachBackdrop };
    };
})();
