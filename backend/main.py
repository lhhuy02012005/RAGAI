import os
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import shutil

# Import từ các file nội bộ
from database import get_db, ChatMessage, User, Conversation
from app import rag_logic
import auth

app = FastAPI(title="SmartDoc Enterprise AI - OSSD 2026 Edition")
frontend_urls_raw = os.getenv("FRONTEND_URLS", "http://localhost:5173")
origins = [url.strip() for url in frontend_urls_raw.split(",")]
# --- CẤU HÌNH CORS ---
app.add_middleware(
    CORSMiddleware,
    # Thay vì dùng "*" (không an toàn), ta dùng danh sách origins cụ thể [cite: 121]
    allow_origins=origins, 
    # Cho phép gửi kèm Cookie hoặc thông tin xác thực nếu cần
    allow_credentials=True, 
    # Cho phép tất cả các phương thức (GET, POST, PUT, DELETE,...) 
    allow_methods=["*"],
    # Cho phép tất cả các headers 
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
        
        hashed_pwd = auth.get_password_hash(password)
        new_user = User(username=username, hashed_password=hashed_pwd)
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        user_path = os.path.join("vector_stores", f"user_{new_user.id}")
        os.makedirs(user_path, exist_ok=True)
        
        return {"message": "Đăng ký thành công"}
    except Exception as e:
        print(f"🔥 Register Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống đăng ký")

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

# --- 3. ENDPOINT UPLOAD ĐA TÀI LIỆU ---
# --- 3. ENDPOINT UPLOAD ĐA TÀI LIỆU ---
@app.post("/upload")
async def upload(
    files: List[UploadFile] = File(...), 
    chunk_size: int = Form(1000), 
    chunk_overlap: int = Form(100),
    current_user: User = Depends(auth.get_current_user)
):
    print(f"\n📢 [API] Nhận yêu cầu upload {len(files)} file từ User ID: {current_user.id}")
    results = []
    total_chunks = 0
    
    for file in files:
        try:
            print(f"🔄 [API] Đang đọc file: {file.filename}")
            content = await file.read()
            
            if not content:
                print(f"❌ [API] File {file.filename} rỗng!")
                continue

            # GỌI LOGIC XỬ LÝ
            count = rag_logic.process_file(
                file_content=content, 
                filename=file.filename, 
                user_id=current_user.id
            )
            
            total_chunks += count
            results.append({"filename": file.filename, "chunks": count, "status": "success"})
            print(f"✅ [API] Đã xử lý xong {file.filename}: {count} chunks")
            
        except Exception as e:
            print(f"🔥 [API] Lỗi khi xử lý {file.filename}: {str(e)}")
            results.append({"filename": file.filename, "status": "error", "reason": str(e)})
    
    return {"status": "ok", "total_files": len(files), "total_chunks": total_chunks, "details": results}

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
        conv = Conversation(id=conversation_id, user_id=current_user.id, title=question_raw[:30])
        db.add(conv)
        db.commit()

    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="user", content=question_enc))

    result = rag_logic.get_answer(question_raw, current_user.id, conversation_id)
    
    answer_text = result["answer"]
    sources = result["sources"]
    confidence = result.get("confidence", "N/A")

    db.add(ChatMessage(conversation_id=conversation_id, user_id=current_user.id, role="bot", content=answer_text))
    db.commit()
    
    return {"answer_raw": answer_text, "sources": sources, "confidence": confidence}

# --- 5. LẤY LỊCH SỬ HỘI THOẠI (Phân trang ngược) ---
@app.get("/history/{conversation_id}")
async def get_history(
    conversation_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    # Lấy tin nhắn mới nhất trước (desc), sau đó đảo ngược lại để hiển thị (asc)
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.user_id == current_user.id
    ).order_by(ChatMessage.timestamp.desc()).offset(skip).limit(limit).all()
    return messages[::-1] 

# --- 6. LẤY SIDEBAR (Phân trang) ---
@app.get("/conversations")
async def get_all_conversations(
    skip: int = 0,
    limit: int = 15,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth.get_current_user)
):
    return db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).offset(skip).limit(limit).all()

# --- 7. XÓA SẠCH LỊCH SỬ ---
@app.delete("/clear-history")
async def clear_history(current_user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.query(Conversation).filter(Conversation.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Đã xóa lịch sử"}

# --- 8. XÓA VECTOR STORE ---
@app.delete("/clear-vector-store")
async def clear_vector_store(current_user: User = Depends(auth.get_current_user)):
    user_path = rag_logic._get_user_path(current_user.id)
    if os.path.exists(user_path):
        shutil.rmtree(user_path)
        os.makedirs(user_path, exist_ok=True)
    return {"detail": "Đã xóa vector store"}