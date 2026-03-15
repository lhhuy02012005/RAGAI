import os
import bcrypt  # Dùng trực tiếp thay cho passlib
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt 
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db, User

SECRET_KEY = os.getenv("JWT_SECRET", "default_secret_key_if_missing")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Hàm xử lý mật khẩu mới ---
def verify_password(plain_password: str, hashed_password: str):
    # Bcrypt yêu cầu dữ liệu dạng bytes
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def get_password_hash(password: str):
    # Cắt ngắn mật khẩu nếu quá 72 ký tự để tránh lỗi Bcrypt
    password_bytes = password[:72].encode('utf-8')
    # Tạo salt và băm
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

# --- Giữ nguyên các hàm JWT bên dưới ---
def create_access_token(user_id: int, device_secret: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "ds": device_secret, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # ... (Giữ nguyên logic get_current_user của bạn)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None: raise credentials_exception
    except JWTError: raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None: raise credentials_exception
    return user