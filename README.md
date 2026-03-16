# a
uvicorn main:app --reload --port 8000
pip install -r requirements.txt

Chúng ta sẽ cài đặt thêm thư viện để đọc DOCX và hỗ trợ OCR cho ảnh:

ollama run qwen2.5:7b
OLLAMA_HOST=0.0.0.0:11434 ollama serve  Cho phép Ollama nhận kết nối từ Docker:

Mặc định Ollama chỉ nghe ở 127.0.0.1. Bạn cần đặt biến môi trường để nó cho phép Docker truy cập qua host.docker.internal.

npm run dev -- --mode production
OLLAMA_HOST=0.0.0.0:11434 ollama serve
npx cloudflared tunnel --url http://127.0.0.1:5173