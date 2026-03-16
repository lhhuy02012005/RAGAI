import os
import tempfile
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader, UnstructuredImageLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

# Các thư viện cho Câu hỏi 6 & 7
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.memory import ConversationBufferWindowMemory
from langchain.chains import ConversationalRetrievalChain

class RAGService:
    def __init__(self, vector_base_dir="./vector_stores"):
        self.vector_base_dir = vector_base_dir
        os.makedirs(self.vector_base_dir, exist_ok=True)
        
        # Model embedding hỗ trợ đa ngôn ngữ [cite: 31, 132]
        self.embedder = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        # LLM Qwen2.5:7b tối ưu cho tiếng Việt [cite: 49, 97, 135]
        self.llm = ChatOllama(
            model="qwen2.5:7b", 
            base_url=ollama_url, 
            num_ctx=4096
        )
        
        # Memory lưu trữ theo từng cuộc hội thoại (Câu hỏi 6) [cite: 594, 616]
        self.memories = {}

    def _get_user_path(self, user_id: int):
        user_path = os.path.join(self.vector_base_dir, f"user_{user_id}")
        os.makedirs(user_path, exist_ok=True)
        return user_path

    # XỬ LÝ FILE (Câu hỏi 1, 4, 5) [cite: 140, 587, 602, 609]
    def process_file(self, file_content: bytes, filename: str, user_id: int, chunk_size=1200, chunk_overlap=200):
        ext = filename.split('.')[-1].lower()
        user_path = self._get_user_path(user_id)
        
        # Page-aware chunking (Câu hỏi 4 & 5) [cite: 17, 143, 603]
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Hỗ trợ đa dạng định dạng (Câu hỏi 1) [cite: 589]
            if ext == 'pdf': loader = PDFPlumberLoader(tmp_path)
            elif ext in ['docx', 'doc']: loader = Docx2txtLoader(tmp_path)
            elif ext in ['jpg', 'png']: loader = UnstructuredImageLoader(tmp_path)
            else: return 0

            docs = loader.load()
            chunks = []
            
            # Gán metadata số trang cho Citation (Câu hỏi 5) 
            for doc in docs:
                page = doc.metadata.get("page_number") or doc.metadata.get("page") or "N/A"
                page_chunks = splitter.split_documents([doc])
                for idx, chunk in enumerate(page_chunks):
                    chunk.metadata = {
                        "source": filename, 
                        "page": page, 
                        "chunk_id": f"{filename}_p{page}_c{idx}"
                    }
                    chunks.append(chunk)

            # Lưu vào FAISS Vector Store [cite: 82, 131, 145]
            index_path = os.path.join(user_path, "index.faiss")
            if os.path.exists(index_path):
                vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
                vector_db.add_documents(chunks)
            else:
                vector_db = FAISS.from_documents(chunks, self.embedder)
            
            vector_db.save_local(user_path)
            return len(chunks)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # TRẢ LỜI CÂU HỎI (HYBRID SEARCH & MEMORY) [cite: 615, 619]
    def get_answer(self, question_raw: str, user_id: int, conversation_id: str):
        user_path = self._get_user_path(user_id)
        index_file = os.path.join(user_path, "index.faiss")
        
        if not os.path.exists(index_file):
            return {"answer": self.llm.invoke(f"Trả lời bằng tiếng Việt: {question_raw}").content, "sources": []}

        try:
            # 1. Tải Vector Store (Semantic Search) [cite: 114]
            vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
            faiss_retriever = vector_db.as_retriever(search_kwargs={"k": 5})

            # 2. Hybrid Search: Kết hợp Vector và Keyword (Câu hỏi 7) [cite: 621, 622]
            all_docs = list(vector_db.docstore._dict.values()) 
            bm25_retriever = BM25Retriever.from_documents(all_docs)
            bm25_retriever.k = 5

            ensemble_retriever = EnsembleRetriever(
                retrievers=[faiss_retriever, bm25_retriever],
                weights=[0.7, 0.3] # Ưu tiên ngữ nghĩa 70%, từ khóa 30%
            )

            # 3. Quản lý Memory cho hội thoại (Câu hỏi 6) [cite: 616, 617]
            if conversation_id not in self.memories:
                self.memories[conversation_id] = ConversationBufferWindowMemory(
                    memory_key="chat_history",
                    output_key="answer", 
                    return_messages=True,
                    k=5 # Nhớ 5 lượt chat gần nhất
                )
            
            # 4. GIỮ NGUYÊN PROMPT CỦA NGƯỜI DÙNG [cite: 228, 240, 260]
            QA_PROMPT = PromptTemplate(
                template="""Bạn là SmartDoc AI - Một chuyên gia phân tích dữ liệu chuyên nghiệp. 
Hãy thực hiện trả lời câu hỏi theo quy trình tư duy sau:

BƯỚC 1: PHÂN LOẠI CÂU HỎI
- Kiểm tra xem câu hỏi có liên quan đến nội dung trong NGỮ CẢNH (tài liệu PDF) hay không.

BƯỚC 2: THỰC HIỆN TRẢ LỜI (CHỌN 1 TRONG 2 KỊCH BẢN TUYỆT ĐỐI KHÔNG CẦN CHO BIẾT BẠN ĐANG DÙNG KỊCH BẢN NÀO)

KỊCH BẢN A: Nếu câu hỏi CÓ TRONG NGỮ CẢNH (RAG Mode)
- Chỉ sử dụng thông tin từ NGỮ CẢNH để trả lời.
- TRÍCH DẪN NGAY sau mỗi ý: Ghi rõ [Nguồn: tên_file - Trang X] dựa trên thông tin có sẵn trong ngữ cảnh.
- Tuyệt đối không tự bịa ra số trang nếu ngữ cảnh không ghi rõ.

KỊCH BẢN B: Nếu câu hỏi KHÔNG CÓ TRONG NGỮ CẢNH (Kiến thức chung...)
- Trả lời bằng kiến thức chuyên môn của bạn một cách đầy đủ và sâu sắc.
- KHÔNG nhắc đến các cụm từ như "không có trong tài liệu", "ngữ cảnh không đề cập" hay "kiến thức hệ thống" hay "kiến thức chuyên môn" hãy trả lời trực tiếp vào câu hỏi luôn.
- TUYỆT ĐỐI KHÔNG trích dẫn bất kỳ Source/Trang nào từ tài liệu vào kịch bản này.
- Trình bày kiến thức một cách trực tiếp, đầy đủ.

NGỮ CẢNH:
{context}

LỊCH SỬ CHAT:
{chat_history}

CÂU HỎI: {question}
TRẢ LỜI BẮT BUỘC TIẾNG VIỆT:""",
                input_variables=["context", "chat_history", "question"]
            )

            # 5. Khởi tạo Chain hội thoại [cite: 116, 615]
            qa_chain = ConversationalRetrievalChain.from_llm(
                llm=self.llm,
                retriever=ensemble_retriever,
                memory=self.memories[conversation_id],
                return_source_documents=True, 
                combine_docs_chain_kwargs={"prompt": QA_PROMPT}, 
                verbose=True
            )

            # 6. Thực thi truy vấn [cite: 149]
            result = qa_chain.invoke({"question": question_raw})
            
            answer = result["answer"]
            source_docs = result["source_documents"]

            # 7. LOGIC LỌC SOURCE THEO NGỮ CẢNH TRẢ LỜI
            sources = []
            
            # Chỉ hiển thị source nếu AI đang thực hiện trích dẫn trang (Kịch bản A)
            if "Trang" in answer or "[Nguồn:" in answer:
                for doc in source_docs:
                    sources.append({
                        "page": doc.metadata.get("page", "N/A"),
                        "source": doc.metadata.get("source", "Tài liệu"),
                        "content": doc.page_content[:200]
                    })
            # Nếu là kiến thức chung (Kịch bản B), mảng sources sẽ rỗng 
            # giúp giao diện không hiển thị các nút "Source 1, 2..."

            return {"answer": answer, "sources": sources}

        except Exception as e:
            print(f"🔥 RAG Error: {e}")
            return {"answer": "Lỗi xử lý AI, vui lòng thử lại bằng tiếng Việt.", "sources": []}

rag_logic = RAGService()