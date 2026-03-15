import os
import tempfile
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader, UnstructuredImageLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

class RAGService:
    def __init__(self, vector_base_dir="./vector_stores"):
        self.vector_base_dir = vector_base_dir
        if not os.path.exists(self.vector_base_dir):
            os.makedirs(self.vector_base_dir)
        
        # Model embedding: Chạy local dùng CPU Mac rất ổn
        self.embedder = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )

        # --- LOGIC LINH HOẠT CHO OLLAMA ---
        # Nếu chạy trong Docker, biến OLLAMA_BASE_URL sẽ được lấy từ docker-compose (host.docker.internal)
        # Nếu chạy local (uvicorn), nó sẽ tự dùng localhost:11434
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        print(f"--- Kết nối Ollama tại: {ollama_url} ---")
        
        self.llm = ChatOllama(
            model="qwen2.5:7b", 
            base_url=ollama_url,
            num_ctx=4096 # Tăng cửa sổ ngữ cảnh để đọc tài liệu dài tốt hơn
        )
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

    def _get_user_path(self, user_id: int):
        user_path = os.path.join(self.vector_base_dir, f"user_{user_id}")
        if not os.path.exists(user_path):
            os.makedirs(user_path)
        return user_path

    def process_file(self, file_content: bytes, filename: str, user_id: int):
        ext = filename.split('.')[-1].lower()
        user_path = self._get_user_path(user_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            if ext == 'pdf': loader = PDFPlumberLoader(tmp_path)
            elif ext in ['docx', 'doc']: loader = Docx2txtLoader(tmp_path)
            elif ext in ['jpg', 'png']: loader = UnstructuredImageLoader(tmp_path)
            else: return 0

            docs = loader.load()
            chunks = self.text_splitter.split_documents(docs)
            
            if os.path.exists(os.path.join(user_path, "index.faiss")):
                vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
                vector_db.add_documents(chunks)
            else:
                vector_db = FAISS.from_documents(chunks, self.embedder)
            
            vector_db.save_local(user_path)
            return len(chunks)
        finally:
            os.remove(tmp_path)

    def get_answer(self, question_raw: str, user_id: int):
        user_path = self._get_user_path(user_id)
        index_path = os.path.join(user_path, "index.faiss")
        
        context = ""
        # 1. Tìm kiếm thông tin từ Vector DB (nếu có)
        if os.path.exists(index_path):
            try:
                vector_db = FAISS.load_local(
                    user_path, 
                    self.embedder, 
                    allow_dangerous_deserialization=True
                )
                # Lấy 3 đoạn văn bản có độ tương đồng cao nhất
                docs = vector_db.similarity_search(question_raw, k=3)
                context = "\n".join([f"- {doc.page_content}" for doc in docs])
                print(f"✅ Found context for user {user_id}")
            except Exception as e:
                print(f"❌ FAISS Error: {e}")

        # 2. Xây dựng Prompt "Pro" phân cấp rõ ràng
        if context:
            prompt = f"""
### VAI TRÒ
Bạn là SmartDoc AI - Một chuyên gia phân tích dữ liệu chuyên nghiệp và tận tâm.

### NGỮ CẢNH HỖ TRỢ
{context}

### CHỈ DẪN TRẢ LỜI
1. ƯU TIÊN: Kiểm tra 'NGỮ CẢNH HỖ TRỢ' để trả lời câu hỏi. 
2. LINH HOẠT: Nếu ngữ cảnh không đủ thông tin hoặc không liên quan, hãy sử dụng kiến thức chuyên sâu của bạn để giải đáp.
3. PHONG CÁCH: Trả lời bằng tiếng Việt, văn phong chuyên nghiệp, trình bày rõ ràng (dùng gạch đầu dòng nếu cần).

### CÂU HỎI CỦA NGƯỜI DÙNG
{question_raw}

### CÂU TRẢ LỜI:
"""
        else:
            # Prompt khi hoàn toàn không có tài liệu
            prompt = f"""
### VAI TRÒ
Bạn là SmartDoc AI - Trợ lý thông minh cao cấp.

### CHỈ DẪN
Hãy trả lời câu hỏi dưới đây một cách chi tiết, chính xác bằng kiến thức của bạn. Trả lời bằng tiếng Việt.

### CÂU HỎI
{question_raw}

### CÂU TRẢ LỜI:
"""

        # 3. Thực thi gọi LLM
        try:
            response = self.llm.invoke(prompt)
            # Trả về nội dung text từ AI
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"🔥 Ollama Connection Error: {e}")
            return "Xin lỗi, tôi gặp trục trặc khi kết nối với bộ não AI. Vui lòng thử lại sau."
        user_path = self._get_user_path(user_id)
        index_path = os.path.join(user_path, "index.faiss")
        
        context = ""
        # Thử tìm kiếm tài liệu
        if os.path.exists(index_path):
            try:
                # Phải load_local với allow_dangerous_deserialization=True
                vector_db = FAISS.load_local(
                    user_path, 
                    self.embedder, 
                    allow_dangerous_deserialization=True
                )
                docs = vector_db.similarity_search(question_raw, k=3)
                context = "\n".join([doc.page_content for doc in docs])
                print(f"--- Đã tìm thấy ngữ cảnh cho User {user_id} ---")
            except Exception as e:
                print(f"--- Lỗi FAISS (có thể file hỏng): {e} ---")
                # Nếu lỗi FAISS, context vẫn rỗng và AI sẽ dùng kiến thức gốc

        # XÂY DỰNG PROMPT
        if context:
            prompt = f"""Sử dụng ngữ cảnh sau đây để trả lời câu hỏi. 
            Nếu trong ngữ cảnh không có thông tin, hãy dùng kiến thức hiểu biết của bạn để trả lời.
            Trả lời bằng tiếng Việt.

            Ngữ cảnh: {context}
            Câu hỏi: {question_raw}
            Trả lời:"""
        else:
            # Đây là phần giúp AI trả lời khi chưa có tài liệu
            prompt = f"Bạn là một trợ lý AI thông minh. Hãy trả lời câu hỏi sau bằng tiếng Việt: {question_raw}"

        try:
            # Gọi trực tiếp LLM
            response = self.llm.invoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"🔥 Lỗi kết nối Ollama: {e}")
            return "Xin lỗi, tôi không thể kết nối với bộ não AI lúc này."
        user_path = self._get_user_path(user_id)
        index_path = os.path.join(user_path, "index.faiss")
        
        context = ""
        # Nếu có tài liệu thì mới đi tìm kiến thức trong Vector DB
        if os.path.exists(index_path):
            try:
                vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
                # Tìm 3 đoạn văn bản liên quan nhất
                docs = vector_db.similarity_search(question_raw, k=3)
                context = "\n".join([doc.page_content for doc in docs])
            except Exception as e:
                print(f"Lỗi load FAISS: {e}")

        # Prompt linh hoạt: Có context thì dùng, không có thì trả lời tự do
        if context:
            prompt = f"""Bạn là một trợ lý AI thông minh. Sử dụng ngữ cảnh dưới đây để trả lời câu hỏi. 
            Nếu ngữ cảnh không chứa thông tin, hãy dùng kiến thức của bạn để trả lời nhưng ưu tiên ngữ cảnh trước.
            
            Ngữ cảnh: {context}
            Câu hỏi: {question_raw}
            Trả lời:"""
        else:
            prompt = f"Câu hỏi: {question_raw}\nTrả lời bằng Tiếng Việt chi tiết:"

        # Gọi LLM trả lời trực tiếp (dùng invoke)
        try:
            response = self.llm.invoke(prompt)
            # Tùy vào phiên bản langchain-ollama, response có thể là object hoặc string
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"Lỗi gọi Ollama: {e}")
            return "Xin lỗi, bộ não AI đang bận xử lý dữ liệu khác."

rag_logic = RAGService()