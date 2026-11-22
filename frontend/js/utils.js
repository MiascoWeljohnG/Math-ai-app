/**
 * Wraps any asynchronous action (like an API fetch or file upload) 
 * with automatic button loading state management.
 * 
 * @param {HTMLButtonElement} buttonEl - The button element being clicked.
 * @param {Function} asyncCallback - The async function to execute.
 * @param {string} [loadingText] - Label shown next to the spinner while running (defaults to the button's own text).
 * @returns {Promise<any>} - Returns the result of the async callback.
 */
async function withButtonLoading(buttonEl, asyncCallback, loadingText) {
    if (!buttonEl) {
        console.warn("withButtonLoading: Button element not found.");
        return;
    }

    // Same 12-bar spinner as the login button, followed by the label (or loadingText, e.g. "Saving...")
    const spinner = '<span class="spinner" role="status"><span aria-hidden="true">' +
        Array.from({ length: 12 }, (_, i) => `<i style="--i:${i}"></i>`).join("") +
        '</span><span class="sr-only">Loading</span></span>';
    const originalHTML = buttonEl.innerHTML;
    const label = document.createElement("span");
    label.textContent = loadingText || buttonEl.textContent.trim();
    buttonEl.innerHTML = spinner;
    buttonEl.appendChild(label);
    buttonEl.classList.add("is-loading");
    buttonEl.disabled = true;
    buttonEl.setAttribute("aria-busy", "true");

    try {
        const result = await asyncCallback();
        return result;
    } catch (error) {
        console.error("Action execution failed:", error);
        throw error; // Re-throw to be handled by the specific button logic
    } finally {
        // Put the label back, unless the callback already rewrote the button's text itself
        if (buttonEl.querySelector(":scope > .spinner")) buttonEl.innerHTML = originalHTML;
        buttonEl.classList.remove("is-loading");
        buttonEl.removeAttribute("aria-busy");
        buttonEl.disabled = false;
    }
}

/**
 * A person's name as "Last, First Middle" (same style as the approvals list).
 * Returns "" when the account has no name filled in, so callers can fall back to the username.
 */
function formatName(person) {
    if (!person) return "";
    const given = [person.first_name, person.middle_name].filter(Boolean).join(" ");
    return [person.last_name, given].filter(Boolean).join(", ");
}
