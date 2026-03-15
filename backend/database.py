import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# --- CẤU HÌNH LINH HOẠT ---
# Lấy DB_PASSWORD từ .env, mặc định là 'ragpassword' nếu không thấy
DB_PASSWORD = os.getenv("DB_PASSWORD", "ragpassword")

# LOGIC QUAN TRỌNG: 
# Nếu chạy trong Docker, ta sẽ set DB_HOST="db" ở file docker-compose.
# Nếu chạy local (uvicorn), hệ thống không tìm thấy biến DB_HOST nên sẽ dùng "localhost".
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "smartdoc_db")
DB_USER = os.getenv("DB_USER", "admin")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}"

# Khởi tạo engine với pool_pre_ping để tự động kết nối lại nếu DB khởi động chậm
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- ĐỊNH NGHĨA MODELS ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True) # UUID tạo từ FE
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)
    content = Column(Text) # Nội dung đã mã hóa PIN Zero-Knowledge
    timestamp = Column(DateTime, default=datetime.utcnow)

# Tự động tạo bảng nếu chưa có
Base.metadata.create_all(bind=engine)

# Dependency để lấy session database cho FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()