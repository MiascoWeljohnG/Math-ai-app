// Shared by every teacher page: the sign-in header the API calls send. Load it right after auth.js.
function getHeaders() {
    return { "Authorization": `Bearer ${localStorage.getItem("token")}` };
}
