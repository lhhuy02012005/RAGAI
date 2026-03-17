import os
import tempfile
import hashlib
from datetime import datetime
from collections import defaultdict
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader
from langchain_experimental.text_splitter import SemanticChunker # Nâng cấp bộ chia nhỏ
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import FlashrankRerank
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.document_transformers import LongContextReorder

class RAGService:
    def __init__(self, vector_base_dir="./vector_stores"):
        self.vector_base_dir = vector_base_dir
        os.makedirs(self.vector_base_dir, exist_ok=True)
        
        # Q7: Embedding 768 chiều [cite: 132, 203]
        self.embedder = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
        
        # Bộ chia nhỏ văn bản theo ngữ nghĩa (Semantic)
        self.semantic_splitter = SemanticChunker(self.embedder, breakpoint_threshold_type="percentile")
        
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.llm = ChatOllama(model="qwen2.5:7b", base_url=ollama_url, temperature=0.1)
        
        try:
            self.compressor = FlashrankRerank(model="ms-marco-MultiBERT-L-12")
        except:
            self.compressor = None
            
        self.memories = {}

    def process_file(self, file_content: bytes, filename: str, user_id: int, chunk_size: int = 1000, chunk_overlap: int = 100):
        file_hash = hashlib.md5(file_content).hexdigest()
        ext = filename.split('.')[-1].lower()
        user_path = self._get_user_path(user_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Sử dụng PDFPlumber để giữ layout [cite: 166-168]
            loader = PDFPlumberLoader(tmp_path) if ext == 'pdf' else Docx2txtLoader(tmp_path)
            docs = loader.load()
            upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # NÂNG CẤP 1: Semantic Chunking thay vì Recursive [cite: 173-174]
            # Giúp mỗi đoạn là một ý hoàn chỉnh, không bị "đứt đoạn"
            chunks = self.semantic_splitter.split_documents(docs)
            
            for idx, chunk in enumerate(chunks):
                chunk.metadata.update({
                    "source": filename,
                    "file_hash": file_hash,
                    "upload_date": upload_date,
                    "user_id": user_id,
                    "chunk_id": f"{file_hash}_{idx}"
                })

            index_path = os.path.join(user_path, "index.faiss")
            if os.path.exists(index_path):
                vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
                # Xử lý Upsert dựa trên hash
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

    def get_answer(self, question_raw: str, user_id: int, conversation_id: str):
        user_path = self._get_user_path(user_id)
        if not os.path.exists(os.path.join(user_path, "index.faiss")):
            return {"answer": self.llm.invoke(question_raw).content, "sources": [], "confidence": 0.3}

        if conversation_id not in self.memories:
            self.memories[conversation_id] = ConversationBufferWindowMemory(k=5, return_messages=True)
        
        chat_hist = self.memories[conversation_id].buffer
        history_text = "\n".join([f"{m.type}: {m.content}" for m in chat_hist])
        optimized_query = self._rewrite_query(question_raw, history_text)

        vector_db = FAISS.load_local(user_path, self.embedder, allow_dangerous_deserialization=True)
        all_docs_list = list(vector_db.docstore._dict.values())
        
        # NÂNG CẤP 2: Dynamic K-Scaling & Multi-doc Awareness [cite: 624-628]
        available_files = list(set([d.metadata['source'] for d in all_docs_list]))
        mentioned_files = [f for f in available_files if f.lower() in question_raw.lower()]
        
        # Nếu hỏi "so sánh" hoặc nhắc nhiều file, tăng K để bao phủ đủ tài liệu
        base_k = 18 if (len(mentioned_files) > 1 or "so sánh" in question_raw.lower()) else 8

        # MMR Search để tăng tính đa dạng thông tin [cite: 550]
        faiss_retriever = vector_db.as_retriever(
            search_type="mmr",
            search_kwargs={"k": base_k, "fetch_k": 35, "lambda_mult": 0.5} # Lambda 0.5 giúp lấy thông tin đa dạng hơn
        )
        
        bm25_retriever = BM25Retriever.from_documents(all_docs_list)
        bm25_retriever.k = base_k

        ensemble = EnsembleRetriever(retrievers=[faiss_retriever, bm25_retriever], weights=[0.6, 0.4])
        
        if self.compressor:
            reranker = ContextualCompressionRetriever(base_compressor=self.compressor, base_retriever=ensemble)
            retrieved_docs = reranker.get_relevant_documents(optimized_query)
        else:
            retrieved_docs = ensemble.get_relevant_documents(optimized_query)

        # NÂNG CẤP 3: Cấu trúc Map-Reduce Context
        # Gom nhóm chunks theo từng file để AI không bị "loạn" [cite: 582, 628]
        grouped_docs = defaultdict(list)
        for d in retrieved_docs:
            grouped_docs[d.metadata['source']].append(d)

        context_parts = []
        for src, docs in grouped_docs.items():
            # LongContextReorder giúp thông tin quan trọng ở 2 đầu chunk list
            reorder = LongContextReorder()
            reordered = reorder.transform_documents(docs)
            
            file_text = "\n".join([f"- {d.page_content}" for d in reordered])
            context_parts.append(f"### DỮ LIỆU TỪ TÀI LIỆU: {src} ###\n{file_text}")
        
        context = "\n\n".join(context_parts)

        # NÂNG CẤP 4: Metadata Tagging để kiểm soát Citation [cite: 612, 636-641]
        QA_PROMPT = """Bạn là SmartDoc AI - Chuyên gia phân tích tài liệu đa nguồn.
        NHIỆM VỤ: Trả lời câu hỏi dựa trên NGỮ CẢNH được cung cấp.

        QUY TẮC CỐT LÕI:
        1. BẮT ĐẦU câu trả lời bằng Tag: [FOUND: TRUE] nếu có thông tin trong tài liệu, hoặc [FOUND: FALSE] nếu dùng kiến thức ngoài.
        2. Nếu thông tin đến từ nhiều file, phải đối chiếu rõ ràng: 'File A nói X, trong khi file B nêu Y'.
        3. Trích dẫn chính xác định dạng: [Nguồn: tên file - Trang X].
        4. Trả lời bằng tiếng Việt chuyên nghiệp.

        NGỮ CẢNH: 
        {context}

        CÂU HỎI: {question}
        TRẢ LỜI:"""

        full_output = self.llm.invoke(
            QA_PROMPT.format(context=context, question=question_raw)
        ).content

        # HẬU XỬ LÝ: Tách Tag và Nội dung
        is_internal = "[FOUND: TRUE]" in full_output
        clean_answer = full_output.replace("[FOUND: TRUE]", "").replace("[FOUND: FALSE]", "").strip()

        sources = []
        if is_internal and context_parts:
            seen = set()
            for d in retrieved_docs:
                src_key = f"{d.metadata['source']}_{d.metadata.get('page', 'NA')}"
                if src_key not in seen:
                    sources.append({
                        "source": d.metadata["source"], 
                        "page": d.metadata.get("page", "NA"), 
                        "content": d.page_content[:200]
                    })
                    seen.add(src_key)
            confidence = 0.98
        else:
            confidence = 0.45 # Kiến thức ngoài không trích dẫn nguồn

        self.memories[conversation_id].save_context({"input": question_raw}, {"output": clean_answer})

        return {"answer": clean_answer, "sources": sources, "confidence": confidence}

    def _get_user_path(self, user_id: int):
        user_path = os.path.join(self.vector_base_dir, f"user_{user_id}")
        os.makedirs(user_path, exist_ok=True)
        return user_path

    def _rewrite_query(self, question, chat_history):
        if not chat_history: return question
        prompt = f"Lịch sử: {chat_history}\nCâu hỏi: {question}\nViết lại thành câu truy vấn tìm kiếm độc lập."
        return self.llm.invoke(prompt).content

rag_logic = RAGService()