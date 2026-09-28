import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine

from database import Base, engine, SessionLocal
from models import User
from auth import hash_password
from routes import auth_routes, admin_routes, user_routes, teacher_routes, materials_routes

Base.metadata.create_all(bind=engine)

# Create default admin on first run
db = SessionLocal()
if not db.query(User).filter(User.username == "admin").first():
    db.add(User(
        username="admin",
        first_name="Admin",
        last_name="User",
        middle_name="",
        email="admin@mail.com",
        birthday="2000-01-01",
        password_hash=hash_password("admin123"),
        role="admin",
    ))
    db.commit()
db.close()

app = FastAPI(title="Math AI App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(user_routes.router)
app.include_router(teacher_routes.router)
app.include_router(materials_routes.router)

@app.get("/")
def root():
    return {"message": "Math AI App is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)   