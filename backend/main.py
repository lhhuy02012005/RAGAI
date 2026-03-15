import os
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime

# Import từ các file nội bộ
from database import get_db, ChatMessage, User, Conversation
from app import rag_logic
import auth

app = FastAPI(title="SmartDoc Enterprise AI")

# --- CẤU HÌNH CORS MẠNH TAY ---
# Cho phép tất cả để vượt qua lỗi Blocked by CORS khi dùng Cloudflare
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False, # Tắt cái này nếu dùng origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 1. ENDPOINT ĐĂNG KÝ ---
@app.post("/register")
async def register(
    username: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    try:
        db_user = db.query(User).filter(User.username == username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
        
        # auth.get_password_hash phải dùng bản bcrypt trực tiếp (đã sửa ở bước trước)
        hashed_pwd = auth.get_password_hash(password)
        new_user = User(username=username, hashed_password=hashed_pwd)
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Đảm bảo đường dẫn vector tồn tại
        user_path = os.path.join("vector_stores", f"user_{new_user.id}")
        os.makedirs(user_path, exist_ok=True)
        
        return {"message": "Đăng ký thành công"}
    except Exception as e:
        # Log lỗi ra terminal của Docker để bạn debug
        print(f"🔥 Register Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")

# --- 2. ENDPOINT ĐĂNG NHẬP ---
@app.post("/login")
async def login(
    username: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Tài khoản hoặc mật khẩu không chính xác")
    
    device_secret = os.urandom(16).hex()
    access_token = auth.create_access_token(user_id=user.id, device_secret=device_secret)
    
    return {
        "access_token": access_token,
        "device_secret": device_secret,
        "token_type": "bearer"
    }

# --- 3. ENDPOINT UPLOAD TÀI LIỆU ---
@app.post("/upload")
async def upload(
    file: UploadFile = File(...), 
    current_user: User = Depends(auth.get_current_user)
):
    try:
        content = await file.read()
        count = rag_logic.process_file(content, file.filename, current_user.id)
        return {"status": "ok", "filename": file.filename, "chunks": count}
    except Exception as e:
        print(f"🔥 Upload Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi xử lý file")

# --- 4. ENDPOINT HỎI ĐÁP AI ---
@app.post("/ask")
async def ask(
    conversation_id: str = Form(...),
    question_enc: str = Form(...),    
    question_raw: str = Form(...),    
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    # Tạo hội thoại trước
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        conv = Conversation(
            id=conversation_id, 
            user_id=current_user.id, 
            title=question_raw[:30] + "..."
        )
        db.add(conv)
        db.commit()

    # Lấy câu trả lời từ RAG
    try:
        answer_raw = rag_logic.get_answer(question_raw, current_user.id)
    except Exception as e:
        print(f"🔥 RAG Error: {e}")
        answer_raw = "AI đang bận, thử lại sau nhé."

    # Lưu lịch sử
    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="user", content=question_enc))
    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="bot", content=answer_raw))
    db.commit()
    
    return {"answer_raw": answer_raw}

# --- 5. LẤY LỊCH SỬ ---
@app.get("/history/{conversation_id}")
async def get_history(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.user_id == current_user.id
    ).order_by(ChatMessage.timestamp.asc()).all()
    return messages