import sqlite3
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
conn = sqlite3.connect("app.db")
conn.execute(
    "INSERT INTO users (username, first_name, last_name, middle_name, email, birthday, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    ("admin", "Admin", "User", "", "admin@mail.com", "2000-01-01", pwd.hash("admin123"), "admin", "2026-09-08")
)
conn.commit()
conn.close()
print("Admin created!")   