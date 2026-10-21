/**
 * Wraps any asynchronous action (like an API fetch or file upload) 
 * with automatic button loading state management.
 * 
 * @param {HTMLButtonElement} buttonEl - The button element being clicked.
 * @param {Function} asyncCallback - The async function to execute.
 * @returns {Promise<any>} - Returns the result of the async callback.
 */
async function withButtonLoading(buttonEl, asyncCallback) {
    if (!buttonEl) {
        console.warn("withButtonLoading: Button element not found.");
        return;
    }
    
    // Activate loading state
    buttonEl.classList.add("is-loading");
    buttonEl.disabled = true;
    
    try {
        const result = await asyncCallback();
        return result;
    } catch (error) {
        console.error("Action execution failed:", error);
        throw error; // Re-throw to be handled by the specific button logic
    } finally {
        // Always ensure button state is restored
        buttonEl.classList.remove("is-loading");
        buttonEl.disabled = false;
    }
}