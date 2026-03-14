from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import io

from sympy import content 
from app import rag_logic

app = FastAPI()

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    # 1. Đọc nội dung file
    file_content = await file.read()
    print(f"Received file: {file.filename}, size: {len(file_content)} bytes , content: {file_content[:100]}") # In ra 100 bytes đầu tiên để debug
    # 2. Kiểm tra dung lượng
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File quá lớn! Vui lòng upload file dưới 10MB.")
    
    try:
        # 3. Truyền trực tiếp bytes vào hàm process_pdf mới
        count = rag_logic.process_pdf(file_content)
        return {"status": "ok", "chunks": count, "filename": file.filename}
    except Exception as e:
        # Nếu lỗi, in ra console để debug
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý PDF: {str(e)}")

@app.post("/ask")
async def ask(question: str = Form(...)):
    try:
        answer = rag_logic.get_answer(question)
        return {"answer": answer}
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi AI trả lời: {str(e)}")