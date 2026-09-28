from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey
from datetime import date, datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    birthday = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")
    created_at = Column(Date, default=date.today)

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    date = Column(Date, default=date.today)
    count = Column(Integer, default=0)

class Conversation(Base):
    """One chat thread. A user can have many — this is what the 'New Chat'
    tabs in the sidebar switch between."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=False, default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    """A single message in a conversation. Persisting these is what makes
    chat history survive logout/refresh instead of living only in browser
    memory."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True, nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)   

class Material(Base):
    """One uploaded course file, tagged with the math branch it belongs to.
    `filename` is the name on disk (with the hash prefix), which is what the
    materials routes and the vector store's `source` metadata both use."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)
    branch = Column(String, nullable=False, default="General")
    uploaded_by = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
