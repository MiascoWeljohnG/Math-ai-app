const API = "http://localhost:8000";

// --- LOGIN (only on index.html) ---
const authForm = document.getElementById("authForm");
if (authForm) {
    authForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;
        const errorEl = document.getElementById("error");
        errorEl.style.display = "none";

        try {
            const res = await fetch(`${API}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Something went wrong");

            localStorage.setItem("token", data.access_token);
            localStorage.setItem("role", data.role);
            localStorage.setItem("username", username);

            if (data.role === "admin") {
                window.location.href = "admin.html";
            } else if (data.role === "teacher") {
                window.location.href = "teacher.html";
            } else {
                window.location.href = "landing.html";
            }
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = "block";
        }
    });
}

// --- REGISTER MODAL (only on index.html) ---
const registerModal = document.getElementById("registerModal");
if (registerModal) {
    document.getElementById("openRegister").addEventListener("click", () => {
        registerModal.classList.add("active");
    });
    document.getElementById("closeModal").addEventListener("click", () => {
        registerModal.classList.remove("active");
    });
    registerModal.addEventListener("click", (e) => {
        if (e.target === registerModal) registerModal.classList.remove("active");
    });

    // --- CALENDAR PICKER ---
    const calendarPicker = document.getElementById("calendarPicker");
    const calGrid = document.getElementById("calGrid");
    const calMonth = document.getElementById("calMonth");
    const calYear = document.getElementById("calYear");
    const regBirthday = document.getElementById("regBirthday");

    let calDate = new Date();
    let selectedDate = null;
    const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];

    monthNames.forEach((m, i) => {
        const opt = document.createElement("option");
        opt.value = i;
        opt.textContent = m;
        calMonth.appendChild(opt);
    });

    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 1900; y--) {
        const opt = document.createElement("option");
        opt.value = y;
        opt.textContent = y;
        calYear.appendChild(opt);
    }
    calYear.value = calDate.getFullYear();
    calMonth.value = calDate.getMonth();

    function renderCalendar() {
        const year = parseInt(calYear.value);
        const month = parseInt(calMonth.value);
        calDate = new Date(year, month, 1);
        calGrid.innerHTML = "";

        ["Su","Mo","Tu","We","Th","Fr","Sa"].forEach(d => {
            const el = document.createElement("div");
            el.className = "day-name";
            el.textContent = d;
            calGrid.appendChild(el);
        });

        const firstDay = new Date(year, month, 1).getDay();
        for (let i = 0; i < firstDay; i++) {
            const el = document.createElement("div");
            el.className = "day empty";
            calGrid.appendChild(el);
        }

        const daysInMonth = new Date(year, month + 1, 0).getDate();
        for (let d = 1; d <= daysInMonth; d++) {
            const el = document.createElement("div");
            el.className = "day";
            el.textContent = d;
            if (selectedDate && selectedDate.getDate() === d && selectedDate.getMonth() === month && selectedDate.getFullYear() === year) {
                el.classList.add("selected");
            }
            el.addEventListener("click", () => {
                selectedDate = new Date(year, month, d);
                const mm = String(month + 1).padStart(2, "0");
                const dd = String(d).padStart(2, "0");
                regBirthday.value = `${year}-${mm}-${dd}`;
                calendarPicker.classList.remove("active");
                renderCalendar();
            });
            calGrid.appendChild(el);
        }
    }

    regBirthday.addEventListener("focus", () => {
        calendarPicker.classList.add("active");
        renderCalendar();
    });

    document.addEventListener("click", (e) => {
        if (!calendarPicker.contains(e.target) && e.target !== regBirthday) {
            calendarPicker.classList.remove("active");
        }
    });

    regBirthday.addEventListener("input", () => {
        let val = regBirthday.value.replace(/[^0-9]/g, "");
        if (val.length >= 4) {
            const year = val.substring(0, 4);
            if (val.length >= 6) {
                const month = val.substring(4, 6);
                if (val.length >= 8) {
                    const day = val.substring(6, 8);
                    regBirthday.value = `${year}-${month}-${day}`;
                } else {
                    regBirthday.value = `${year}-${month}`;
                }
            } else {
                regBirthday.value = year;
            }
        }
        calendarPicker.classList.remove("active");
    });

    calMonth.addEventListener("change", renderCalendar);
    calYear.addEventListener("change", renderCalendar);
    document.getElementById("calPrev").addEventListener("click", () => {
        let m = parseInt(calMonth.value) - 1;
        if (m < 0) { m = 11; calYear.value = parseInt(calYear.value) - 1; }
        calMonth.value = m;
        renderCalendar();
    });
    document.getElementById("calNext").addEventListener("click", () => {
        let m = parseInt(calMonth.value) + 1;
        if (m > 11) { m = 0; calYear.value = parseInt(calYear.value) + 1; }
        calMonth.value = m;
        renderCalendar();
    });

    // --- REGISTER SUBMIT ---
    document.getElementById("registerForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const firstName = document.getElementById("regFirstName").value;
        const lastName = document.getElementById("regLastName").value;
        const middleName = document.getElementById("regMiddleName").value;
        const email = document.getElementById("regEmail").value;
        const birthday = regBirthday.value;
        const password = document.getElementById("regPassword").value;
        const confirm = document.getElementById("regConfirm").value;
        const errorEl = document.getElementById("regError");
        errorEl.style.display = "none";

        if (password !== confirm) {
            errorEl.textContent = "Passwords do not match";
            errorEl.style.display = "block";
            return;
        }
        if (!birthday) {
            errorEl.textContent = "Please enter or select your birthday";
            errorEl.style.display = "block";
            return;
        }

        const username = (firstName + lastName).toLowerCase().replace(/\s+/g, "");

        try {
            const res = await fetch(`${API}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: username,
                    first_name: firstName,
                    last_name: lastName,
                    middle_name: middleName,
                    email: email,
                    birthday: birthday,
                    password: password
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Registration failed");

            registerModal.classList.remove("active");
            alert("Account created! You can now log in.");
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = "block";
        }
    });
}

// --- PROTECT PAGES (works on all pages) ---
function requireAuth() {
    const token = localStorage.getItem("token");
    if (!token) window.location.href = "index.html";
}

function requireRole(expectedRole) {
    const token = localStorage.getItem("token");
    if (!token) { window.location.href = "index.html"; return; }
    if (localStorage.getItem("role") !== expectedRole) {
        window.location.href = "landing.html";
    }
}

function logout() {
    localStorage.clear();
    window.location.href = "index.html";
}   