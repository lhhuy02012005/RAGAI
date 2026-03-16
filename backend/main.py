import os
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import shutil

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
    chunk_size: int = Form(1000), 
    chunk_overlap: int = Form(100),
    current_user: User = Depends(auth.get_current_user)
):
    content = await file.read()
    count = rag_logic.process_file(content, file.filename, current_user.id, chunk_size, chunk_overlap)
    return {"status": "ok", "chunks": count}

# --- 4. ENDPOINT HỎI ĐÁP AI ---
@app.post("/ask")
async def ask(
    conversation_id: str = Form(...),
    question_enc: str = Form(...),    
    question_raw: str = Form(...),    
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        conv = Conversation(id=conversation_id, user_id=current_user.id, title=question_raw[:30] + "...")
        db.add(conv)
        db.commit()

    # Lưu tin nhắn người dùng (Zero-Knowledge)
    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="user", content=question_enc))

    # GỌI RAG LOGIC: Bây giờ truyền 3 tham số để dùng được Memory (Câu hỏi 6)
    result = rag_logic.get_answer(question_raw, current_user.id, conversation_id)
    
    answer_text = result["answer"]
    sources = result["sources"]

    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="bot", content=answer_text))
    db.commit()
    
    return {"answer_raw": answer_text, "sources": sources}
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


# --- 6. LẤY DANH SÁCH TẤT CẢ HỘI THOẠI (DÀNH CHO SIDEBAR) ---
@app.get("/conversations")
async def get_all_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    # Lấy danh sách các cuộc hội thoại của User này, mới nhất xếp lên trên
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).all()
    
    return conversations

# --- 7. XÓA LỊCH SỬ ---
@app.delete("/clear-history")
async def clear_history(current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.query(Conversation).filter(Conversation.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Đã xóa lịch sử chat"}

# --- 8. XÓA VECTO STORE ---
@app.delete("/clear-vector-store")
async def clear_vector_store(
    current_user: User = Depends(auth.get_current_user) # SỬA TẠI ĐÂY
):
    user_path = rag_logic._get_user_path(current_user.id)
    if os.path.exists(user_path):
        shutil.rmtree(user_path)
        os.makedirs(user_path, exist_ok=True)
    return {"detail": "Đã xóa toàn bộ tài liệu đã upload"}