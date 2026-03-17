import os
import tempfile
import hashlib
import re
from datetime import datetime
from collections import defaultdict
from thefuzz import process, fuzz

# LangChain & AI Libraries
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import FlashrankRerank
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.document_transformers import LongContextReorder
from langchain.text_splitter import RecursiveCharacterTextSplitter



class RAGService:
    def __init__(self, vector_base_dir="./vector_stores"):
        self.vector_base_dir = vector_base_dir
        os.makedirs(self.vector_base_dir, exist_ok=True)

        print(f"🚀 [INIT] Đang khởi tạo hệ thống RAG tối ưu...")
        self.embedder = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )

        self.size_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, chunk_overlap=120
        )

        self.semantic_splitter = SemanticChunker(
            self.embedder, breakpoint_threshold_type="percentile"
        )

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.llm = ChatOllama(model="qwen2.5:7b", base_url=ollama_url, temperature=0.1)

        try:
            self.compressor = FlashrankRerank(model="ms-marco-MultiBERT-L-12")
            print("✅ [INIT] Đã nạp Flashrank Reranker.")
        except Exception as e:
            self.compressor = None
            print(f"⚠️ [INIT] Flashrank lỗi: {e}")

        self.memories = {}

    def _smart_router(self, question: str, available_files: list):
        question_low = question.lower()
        print(f"\n🧠 [ROUTER] Đang phân tích câu hỏi: '{question}'")

        # 1. Kiểm tra chào hỏi
        if (
            re.search(r"^(chào|hi|hello|tạm biệt|bye|cám ơn|thanks)", question_low)
            and len(question_low) < 15
        ):
            print("➡️ [ROUTER] Loại: SOCIAL (Chào hỏi xã giao)")
            return "general", []

        # 2. Kiểm tra yêu cầu tóm tắt/toàn bộ
        if re.search(r"(tóm tắt|nội dung|tổng hợp|tất cả|các file)", question_low):
            print(
                f"➡️ [ROUTER] Loại: MULTI-DOC (Truy vấn tổng hợp trên {len(available_files)} file)"
            )
            return "multi", available_files

        # 3. Kiểm tra nhắc tên file đích danh
        file_ref = re.search(
            r"(?:file|tài liệu|tệp|bản|trong|về)\s+([\w\s\.\-_]+)", question_low
        )
        if file_ref:
            potential_name = file_ref.group(1).strip()
            print(f"🔎 [ROUTER] Phát hiện tham chiếu file: '{potential_name}'")
            best_match, score = process.extractOne(
                potential_name, available_files, scorer=fuzz.partial_ratio
            )

            if score > 75:
                print(f"🎯 [ROUTER] Khớp đích danh: '{best_match}' (Score: {score})")
                return "specific", [best_match]
            print(
                f"⚠️ [ROUTER] Tên file tham chiếu không đủ độ tin cậy ({score}), dùng chế độ Multi."
            )

        print("➡️ [ROUTER] Loại: DEFAULT (Tìm kiếm ngữ nghĩa trên toàn bộ kho tài liệu)")
        return "multi", available_files

    def process_file(self, file_content: bytes, filename: str, user_id: int):
        print(f"\n📥 [UPLOAD] Bắt đầu xử lý file: {filename}")

        file_hash = hashlib.md5(file_content).hexdigest()
        print(f"🔑 [UPLOAD] Mã MD5: {file_hash}")

        ext = filename.split(".")[-1].lower()
        is_image = ext in ["png", "jpg", "jpeg"]
        user_path = self._get_user_path(user_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            print(f"📖 [UPLOAD] Đang nạp nội dung định dạng {ext.upper()}...")
            loader = (
                PDFPlumberLoader(tmp_path) if ext == "pdf" else Docx2txtLoader(tmp_path)
            )
            docs = loader.load()
            docs = self.size_splitter.split_documents(docs)

            print(f"✂️ [UPLOAD] Đang chia mảnh (Semantic Chunking) - Vui lòng chờ...")
            chunks = self.semantic_splitter.split_documents(docs)
            print(f"📦 [UPLOAD] Đã tạo thành công {len(chunks)} mảnh tài liệu.")

            upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for idx, chunk in enumerate(chunks):
                chunk.metadata.update(
                    {
                        "source": filename,
                        "page": chunk.metadata.get("page", "NA"),
                        "file_hash": file_hash,
                        "upload_date": upload_date,
                        "chunk_id": f"{file_hash}_{idx}",
                    }
                )

            index_path = os.path.join(user_path, "index.faiss")
            if os.path.exists(index_path):
                print(f"♻️ [UPLOAD] Đang cập nhật Vector Store hiện có tại: {user_path}")
                vector_db = FAISS.load_local(
                    user_path, self.embedder, allow_dangerous_deserialization=True
                )

                # Tìm và xóa các chunk cũ của cùng một file để tránh trùng lặp
                ids_to_del = [
                    id
                    for id, d in vector_db.docstore._dict.items()
                    if d.metadata.get("file_hash") == file_hash
                ]
                if ids_to_del:
                    print(
                        f"🧹 [UPLOAD] Phát hiện file cũ, đang dọn dẹp {len(ids_to_del)} mảnh cũ..."
                    )
                    vector_db.delete(ids_to_del)

                print(f"➕ [UPLOAD] Đang thêm {len(chunks)} mảnh mới vào index...")
                vector_db.add_documents(chunks)
            else:
                print(f"🔢 [UPLOAD] Đang khởi tạo FAISS Index mới...")
                vector_db = FAISS.from_documents(chunks, self.embedder)

            print(f"💾 [UPLOAD] Đang lưu Vector Store cục bộ...")
            vector_db.save_local(user_path)
            print(f"✅ [UPLOAD] Hoàn tất! File '{filename}' đã sẵn sàng truy vấn.")
            return len(chunks)

        except Exception as e:
            print(f"❌ [UPLOAD ERROR] Lỗi khi xử lý file {filename}: {str(e)}")
            raise e
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def get_answer(self, question_raw: str, user_id: int, conversation_id: str):
        print(f"\n{'='*20} BẮT ĐẦU MULTI-QUERY RAG {'='*20}")
        user_path = self._get_user_path(user_id)

        if not os.path.exists(os.path.join(user_path, "index.faiss")):
            return {
                "answer": self.llm.invoke(question_raw).content,
                "sources": [],
                "confidence": 0.3,
            }

        # BƯỚC 1: GENERATE MULTI-QUERIES
        print(f"🔄 [STEP 1] Đang tạo các biến thể truy vấn...")
        if conversation_id not in self.memories:
            self.memories[conversation_id] = ConversationBufferWindowMemory(
                k=5, return_messages=True
            )
        history_text = "\n".join(
            [
                f"User: {m.content}" if m.type == "human" else f"Assistant: {m.content}"
                for m in self.memories[conversation_id].buffer
            ]
        )

        query_variants = self._rewrite_query(question_raw, history_text)
        all_queries = list(set([question_raw] + query_variants))[:4]

        for i, q in enumerate(all_queries):
            print(f"   📍 Query {i+1}: {q}")

        # BƯỚC 2: KHỞI TẠO RETRIEVER
        vector_db = FAISS.load_local(
            user_path, self.embedder, allow_dangerous_deserialization=True
        )
        all_docs_list = list(vector_db.docstore._dict.values())

        # BƯỚC 3: TRUY XUẤT ĐA LUỒNG (Multi-Query Loop)
        print(
            f"⚡ [STEP 3] Đang truy xuất dữ liệu từ {len(all_queries)} hướng khác nhau..."
        )

        # Sử dụng Ensemble (Vector + BM25) cho từng câu hỏi
        faiss_ret = vector_db.as_retriever(
            search_type="mmr", search_kwargs={"k": 6, "fetch_k": 50}
        )
        bm25_ret = BM25Retriever.from_documents(all_docs_list)
        bm25_ret.k = 15
        ensemble = EnsembleRetriever(
            retrievers=[faiss_ret, bm25_ret], weights=[0.6, 0.4]
        )

        all_retrieved_docs = []
        for q in all_queries:
            docs = ensemble.get_relevant_documents(q)
            all_retrieved_docs.extend(docs)

        # Loại bỏ trùng lặp dựa trên chunk_id
        unique_docs = {d.metadata["chunk_id"]: d for d in all_retrieved_docs}
        retrieved_docs = list(unique_docs.values())
        print(
            f"🧩 [INFO] Tìm thấy tổng cộng {len(retrieved_docs)} mảnh tài liệu duy nhất."
        )

        # BƯỚC 4: RERANKING (Cực kỳ quan trọng khi dùng Multi-query để lọc nhiễu)
        if self.compressor and retrieved_docs:
            print(
                f"🚀 [STEP 4] Reranking: Đang lọc lại những mảnh thực sự liên quan đến '{question_raw}'..."
            )
            # Dùng câu hỏi gốc (question_raw) để rerank đống tài liệu vừa gom được
            retrieved_docs = retrieved_docs[:20]
            retrieved_docs = self.compressor.compress_documents(
                retrieved_docs, question_raw
            )

        # BƯỚC 5: LONG CONTEXT REORDER & BUILD CONTEXT
        reorder = LongContextReorder()
        final_docs = reorder.transform_documents(retrieved_docs)
        final_docs = final_docs[:15]

        if not final_docs:
            return {
                "answer": "Không tìm thấy thông tin liên quan trong tài liệu.",
                "sources": [],
                "confidence": 0.3,
            }

        context_parts = []
        for d in final_docs:
            context_parts.append(f"[SOURCE: {d.metadata['source']}]\n{d.page_content}")
        context = "\n\n".join(context_parts)

        # BƯỚC 6: TRẢ LỜI
        QA_PROMPT = """
    Bạn là SmartDoc AI.

    Dựa vào:
    1. LỊCH SỬ HỘI THOẠI
    2. NGỮ CẢNH TÀI LIỆU

    để trả lời CÂU HỎI BẰNG TIẾNG VIỆT (BẮT BUỘC).
    ---------------------

    LỊCH SỬ HỘI THOẠI:
    {history}

    ---------------------

    NGỮ CẢNH:
    {context}

    ---------------------

    CÂU HỎI:
    {question}

    TRẢ LỜI:
    """

        full_output = self.llm.invoke(
            QA_PROMPT.format(
                context=context, question=question_raw, history=history_text
            )
        ).content
        is_internal = "[FOUND: TRUE]" in full_output
        clean_answer = (
            full_output.replace("[FOUND: TRUE]", "")
            .replace("[FOUND: FALSE]", "")
            .strip()
        )

        self.memories[conversation_id].save_context(
            {"input": question_raw}, {"output": clean_answer}
        )
        print(f"{'='*20} HOÀN TẤT {'='*20}")

        return {
            "answer": clean_answer,
            "sources": (
                [
                    {
                        "source": d.metadata["source"],
                        "page": d.metadata.get("page", "NA"),
                    }
                    for d in final_docs
                ][:5]
                if is_internal
                else []
            ),
            "confidence": 0.98 if is_internal else 0.45,
        }

    def _get_user_path(self, user_id: int):
        user_path = os.path.join(self.vector_base_dir, f"user_{user_id}")
        os.makedirs(user_path, exist_ok=True)
        return user_path

    def _rewrite_query(self, question, chat_history):
        if not chat_history:
            return [question]
        prompt = f"""Dựa trên lịch sử chat, hãy viết lại câu hỏi mới nhất thành một câu truy vấn tìm kiếm DUY NHẤT.
        RÀO CẢN NGHIÊM NGẶT:
        - KHÔNG được trả lời câu hỏi.
        - KHÔNG được thêm các câu dẫn như "Dựa trên thông tin...", "Tôi hiểu rằng...".
        - KHÔNG giải thích tại sao thông tin không có trong file.
        - Giữ nguyên các từ khóa kỹ thuật
        
        Lịch sử: {chat_history}
        Câu hỏi: {question}
        Truy vấn:
        """
        response = self.llm.invoke(prompt).content
        # Tách các dòng thành danh sách và loại bỏ dòng trống
        queries = [q.strip() for q in response.split("\n") if q.strip()]
        return queries[:3] if queries else [question]

    def _process_image(self, image_path):
        print("🖼️ [OCR] Đang đọc chữ từ ảnh...")
        result = self.ocr.ocr(image_path)
        texts = []
        for line in result:
            for word in line:
                texts.append(word[1][0])
        return "\n".join(texts)


rag_logic = RAGService()
