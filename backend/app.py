import os
import tempfile
import hashlib
from datetime import datetime
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import FlashrankRerank
from langchain.memory import ConversationBufferWindowMemory

class RAGService:
    def __init__(self, vector_base_dir="./vector_stores"):
        self.vector_base_dir = vector_base_dir
        os.makedirs(self.vector_base_dir, exist_ok=True)
        
        # Q7 & Q9: Embedding & Re-ranking models
        self.embedder = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
        
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.llm = ChatOllama(model="qwen2.5:7b", base_url=ollama_url, temperature=0.1)
        
        # Q9: Re-ranking với Cross-Encoder
        try:
            self.compressor = FlashrankRerank(model="ms-marco-MultiBERT-L-12")
        except:
            self.compressor = None
            print("⚠️ Flashrank chưa được cài đặt.")
            
        self.memories = {}

    def _get_user_path(self, user_id: int):
        user_path = os.path.join(self.vector_base_dir, f"user_{user_id}")
        os.makedirs(user_path, exist_ok=True)
        return user_path

    # Q1, Q4, Q8: Xử lý DOCX, Chunking tùy chỉnh & Multi-doc Metadata
    def process_file(self, file_content: bytes, filename: str, user_id: int, chunk_size=1000, chunk_overlap=100):
        file_hash = hashlib.md5(file_content).hexdigest()
        ext = filename.split('.')[-1].lower()
        user_path = self._get_user_path(user_id)
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Q1: Hỗ trợ PDF và DOCX
            loader = PDFPlumberLoader(tmp_path) if ext == 'pdf' else Docx2txtLoader(tmp_path)
            docs = loader.load()
            chunks = []
            upload_date = datetime.now().strftime("%Y-%m-%d")

            for doc in docs:
                # Q5: Citation/Source tracking metadata
                raw_page = doc.metadata.get("page") or doc.metadata.get("page_number")
                page = int(raw_page) if raw_page is not None else "N/A"
                
                page_chunks = splitter.split_documents([doc])
                for idx, chunk in enumerate(page_chunks):
                    # Q8: Metadata filtering
                    chunk.metadata = {
                        "source": filename,
                        "file_hash": file_hash,
                        "page": page,
                        "upload_date": upload_date,
                        "user_id": user_id,
                        "chunk_id": f"{file_hash}_p{page}_c{idx}"
                    }
                    chunks.append(chunk)

            index_path = os.path.join(user_path, "index.faiss")
            if os.path.exists(index_path):
                vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
                # Chống trùng lặp (Upsert logic)
                all_docs = vector_db.docstore._dict
                ids_to_del = [id for id, d in all_docs.items() if d.metadata.get("file_hash") == file_hash]
                if ids_to_del: vector_db.delete(ids_to_del)
                vector_db.add_documents(chunks)
            else:
                vector_db = FAISS.from_documents(chunks, self.embedder)
            
            vector_db.save_local(user_path)
            return len(chunks)
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)

    # Q10: Query Rewriting
    def _rewrite_query(self, question, chat_history):
        if not chat_history: return question
        prompt = f"Lịch sử: {chat_history}\nCâu hỏi: {question}\nViết lại thành câu truy vấn độc lập."
        return self.llm.invoke(prompt).content

    def get_answer(self, question_raw: str, user_id: int, conversation_id: str):
        user_path = self._get_user_path(user_id)
        if not os.path.exists(os.path.join(user_path, "index.faiss")):
            return {"answer": self.llm.invoke(question_raw).content, "sources": [], "confidence": 0.3}

        if conversation_id not in self.memories:
            self.memories[conversation_id] = ConversationBufferWindowMemory(k=5, return_messages=True)
        chat_hist = self.memories[conversation_id].buffer
        
        optimized_query = self._rewrite_query(question_raw, chat_hist)

        # Hybrid Search
        vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
        faiss_retriever = vector_db.as_retriever(search_kwargs={"k": 8, "filter": {"user_id": user_id}})
        all_docs = list(vector_db.docstore._dict.values())
        bm25_retriever = BM25Retriever.from_documents(all_docs)
        bm25_retriever.k = 8
        ensemble = EnsembleRetriever(retrievers=[faiss_retriever, bm25_retriever], weights=[0.7, 0.3])

        if self.compressor:
            reranker = ContextualCompressionRetriever(base_compressor=self.compressor, base_retriever=ensemble)
            final_docs = reranker.get_relevant_documents(optimized_query)
        else:
            final_docs = ensemble.get_relevant_documents(optimized_query)

        # --- BẮT ĐẦU ĐOẠN THAY THẾ ---
        
        # 1. Chuẩn bị ngữ cảnh từ tài liệu
        context = "\n".join([f"[{d.metadata['source']} - P{d.metadata['page']}]: {d.page_content}" for d in final_docs])

        # 2. Q10: Self-RAG (Kiểm tra xem tài liệu có thực sự liên quan không)
        eval_prompt = f"Câu hỏi: {optimized_query}\nNgữ cảnh: {context}\nTrong ngữ cảnh có chứa thông tin để trả lời câu hỏi này không? Chỉ trả lời duy nhất từ YES hoặc NO."
        eval_msg = self.llm.invoke(eval_prompt).content.upper()

        # 3. Định nghĩa QA_PROMPT (đã cải tiến để linh hoạt)
        QA_PROMPT = """Bạn là trợ lý ảo thông minh SmartDoc AI. Hãy trả lời câu hỏi dựa trên các quy tắc sau:
        1. Nếu có thông tin trong 'NGỮ CẢNH TÀI LIỆU', hãy trả lời chi tiết và TRÍCH DẪN chính xác theo định dạng [Nguồn: tên file - Trang X].
        2. Nếu thuộc về KIẾN THỨC CHUNG hoặc ngữ cảnh không có thông tin, hãy dùng KIẾN THỨC CỦA BẠN để trả lời đầy đủ nhất.
        3. TUYỆT ĐỐI KHÔNG nói "Tài liệu không nhắc đến" nếu đó là kiến thức xã hội phổ thông.
        4. LUÔN TRẢ LỜI BẰNG TIẾNG VIỆT.

        NGỮ CẢNH TÀI LIỆU:
        {context}

        LỊCH SỬ TRÒ CHUYỆN:
        {chat_history}

        CÂU HỎI: {question}"""

        if "YES" in eval_msg:
            confidence = 0.95
            # Nếu có thông tin trong tài liệu, dùng Prompt có context
            final_input = QA_PROMPT.format(context=context, chat_history=chat_hist, question=question_raw)
            answer = self.llm.invoke(final_input).content
            
            # Chỉ lấy nguồn khi tài liệu thực sự có liên quan
            sources = []
            seen = set()
            for d in final_docs:
                key = f"{d.metadata['source']}_{d.metadata['page']}"
                if key not in seen:
                    sources.append({"source": d.metadata["source"], "page": d.metadata["page"], "content": d.page_content[:200]})
                    seen.add(key)
        else:
            confidence = 0.4
            # Nếu không có thông tin (hỏi Iran-Mỹ), yêu cầu AI trả lời bằng kiến thức xã hội
            router_prompt = f"Bạn là trợ lý thông minh. Hãy trả lời câu hỏi sau bằng kiến thức xã hội của bạn (không quan tâm đến tài liệu): {question_raw}. Lịch sử chat: {chat_hist}"
            answer = self.llm.invoke(router_prompt).content
            # Xóa sources vì tài liệu không liên quan đến câu hỏi xã hội này
            sources = []

        return {"answer": answer, "sources": sources, "confidence": confidence}
        
        # --- KẾT THÚC ĐOẠN THAY THẾ ---

rag_logic = RAGService()