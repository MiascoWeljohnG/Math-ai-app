// Added logic to auth.js for modals in signup.html

const API = (location.hostname === "localhost" || location.hostname === "127.0.0.1") 
    ? "http://localhost:8000" 
    : "https://isipnayan.onrender.com";

// Assuming you have a modal wrapper in signup.html for notifications
// You need to add this to signup.html:
// <div class="modal-overlay" id="signupModal"><div class="modal" style="text-align:center"><h2 id="signupModalTitle"></h2><p id="signupModalText"></p><button class="btn btn-primary" id="closeSignupModal">OK</button></div></div>

function showSignupModal(title, text) {
    const modal = document.getElementById("signupModal");
    if (!modal) return alert(title + ": " + text);
    document.getElementById("signupModalTitle").innerText = title;
    document.getElementById("signupModalText").innerText = text;
    modal.classList.add("active");
}

if (document.getElementById("closeSignupModal")) {
    document.getElementById("closeSignupModal").addEventListener("click", () => {
        document.getElementById("signupModal").classList.remove("active");
    });
}

const registerForm = document.getElementById("registerForm");
if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        // ... gather data ...
        const student_id = document.getElementById("regStudentId").value.trim();
        const full_name = document.getElementById("regFullName").value.trim();
        const email = document.getElementById("regEmail").value.trim();
        const password = document.getElementById("regPassword").value;
        const confirm = document.getElementById("regConfirm").value;
        const birthday = document.getElementById("regBirthday").value;
        
        if (password !== confirm) {
            return showSignupModal("Error", "Passwords do not match.");
        }
        
        try {
            const res = await fetch(`${API}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    student_id, full_name, email, birthday, password
                })
            });
            const data = await res.json();
            
            if (!res.ok) {
                // Check if the error is related to student number not in system
                if (data.detail && data.detail.includes("not registered")) {
                    showSignupModal("Pending for Request", "Your student number is not in the system. A request has been sent to the admin.");
                    // Notify admin endpoint (you need to implement this on your backend)
                    fetch(`${API}/auth/request-access`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ student_id, full_name, email })
                    });
                } else {
                    showSignupModal("Error", data.detail || "Registration failed.");
                }
                return;
            }
            
            showSignupModal("Success", "Account created successfully! You can now log in.");
            setTimeout(() => { window.location.href = "index.html"; }, 2000);
            
        } catch (err) {
            showSignupModal("Error", "Network error or server is down.");
        }
    });
}
