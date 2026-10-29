from database import SessionLocal
from models import User
from auth import hash_password
from models import ACTIVE

# Define your preferred passwords and school IDs
# Make sure these match the school IDs in your 'schools' table
admins = [
    {"username": "admin_school_a", "password": "admin123", "school_id": 1, "role": "school_admin"},
    {"username": "admin_school_b", "password": "admin456", "school_id": 2, "role": "school_admin"}
]

db = SessionLocal()

for admin_data in admins:
    # Check if user already exists
    existing_user = db.query(User).filter(User.username == admin_data["username"]).first()
    if existing_user:
        print(f"User {admin_data['username']} already exists.")
        continue

    # Create new admin user
    new_admin = User(
        username = admin_data["username"],
        password_hash = hash_password(admin_data["password"]),
        role = admin_data["role"],
        school_id = admin_data["school_id"],
        status=ACTIVE
    )
    db.add(new_admin)
    print(f"Created admin: {admin_data['username']}")

db.commit()
db.close()   