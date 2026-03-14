import os
import io
import tempfile
from langchain_community.document_loaders import PDFPlumberLoader, PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import ChatOllama
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

class RAGService:
    def __init__(self, data_dir="./data", index_path="faiss_index"):
        self.index_path = index_path
        self.data_dir = data_dir
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        self.embedder = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        self.llm = ChatOllama(model="qwen2.5:7b", temperature=0.7)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        self.vector_db = None

        # Nạp Index cũ nếu có, nếu không thì quét data_dir
        if os.path.exists(self.index_path):
            print(f"💾 Loading index from {self.index_path}...")
            self.vector_db = FAISS.load_local(
                self.index_path, 
                self.embedder, 
                allow_dangerous_deserialization=True
            )
        elif os.listdir(self.data_dir):
            print(f"📂 Scanning directory {self.data_dir}...")
            self.load_directory(self.data_dir)

    def load_directory(self, path: str):
        loader = DirectoryLoader(path, glob="./*.pdf", loader_cls=PyPDFLoader)
        docs = loader.load()
        chunks = self.text_splitter.split_documents(docs)
        self.vector_db = FAISS.from_documents(chunks, self.embedder)
        self.save_index()

    def save_index(self):
        if self.vector_db:
            self.vector_db.save_local(self.index_path)

    def process_pdf(self, file_content: bytes):
        """Xử lý bytes từ FastAPI bằng cách tạo file tạm để loader đọc được"""
        # Tạo file tạm thời với suffix .pdf
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name

        try:
            # Loader sẽ đọc đường dẫn file (string) thay vì đối tượng BytesIO
            loader = PDFPlumberLoader(temp_path)
            docs = loader.load()
            chunks = self.text_splitter.split_documents(docs)
            
            if self.vector_db is None:
                self.vector_db = FAISS.from_documents(chunks, self.embedder)
            else:
                self.vector_db.add_documents(chunks)
            
            self.save_index()
            return len(chunks)
        finally:
            # Xóa file ngay sau khi xử lý xong để dọn dẹp hệ thống
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def get_answer(self, question: str):
        if not self.vector_db:
            return "Hệ thống chưa có dữ liệu. Vui lòng upload PDF hoặc kiểm tra thư mục data."

        vn_chars = 'áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ'
        is_vn = any(c in question.lower() for c in vn_chars)

        template = """Sử dụng ngữ cảnh sau để trả lời. Trả lời súc tích.
Ngữ cảnh: {context}
Câu hỏi: {question}
Trả lời:""" if is_vn else """Use the context to answer shortly.
Context: {context}
Question: {question}
Answer:"""

        prompt = PromptTemplate(template=template, input_variables=["context", "question"])
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_db.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": prompt}
        )
        return qa_chain.invoke({"query": question})["result"]

# Khởi tạo instance duy nhất
rag_logic = RAGService()