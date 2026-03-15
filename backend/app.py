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
        if not os.path.exists(os.path.join(user_path, "index.faiss")):
            return "Bạn chưa nạp tài liệu cho bộ não AI của mình."

        vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
        
        template = """Sử dụng ngữ cảnh sau để trả lời. Trả lời chi tiết bằng Tiếng Việt.
        Ngữ cảnh: {context}
        Câu hỏi: {question}
        Trả lời:"""
        
        prompt = PromptTemplate(template=template, input_variables=["context", "question"])
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=vector_db.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": prompt}
        )
        # Sử dụng invoke thay vì run (LangChain chuẩn mới)
        result = qa_chain.invoke({"query": question_raw})
        return result["result"]

rag_logic = RAGService()