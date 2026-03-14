import React, { useState, useRef } from "react";
import { Send, Plus, Paperclip, User, Bot, UploadCloud, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import TypingIndicator from "./TypingIndicator";

// Định nghĩa kiểu dữ liệu (Interface) cho tin nhắn
interface Message {
  role: "user" | "bot";
  content: string;
  file?: string;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "bot",
      content:
        "Chào bạn! Tôi là SmartDoc AI. Hãy upload file PDF và đặt câu hỏi cho tôi.",
    },
  ]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Thêm state isLoading vào đầu component
  const [isLoading, setIsLoading] = useState(false);

const handleSend = async () => {
    if (!input.trim() && !file) return;

    // 1. Hiển thị tin nhắn người dùng
    const userMsg: Message = { role: "user", content: input, file: file?.name };
    setMessages((prev) => [...prev, userMsg]);
    
    const currentInput = input;
    const currentFile = file; // Giữ reference file để xử lý
    
    setInput("");
    setFile(null); // Clear file ngay để UI sạch sẽ
    setIsLoading(true);

    try {
      // 2. Upload file nếu có
      if (currentFile) {
        const formData = new FormData();
        formData.append("file", currentFile);
        
        const uploadRes = await fetch("http://localhost:8000/upload", {
          method: "POST",
          body: formData,
        });

        if (!uploadRes.ok) {
          const errorData = await uploadRes.json();
          throw new Error(errorData.detail || "Lỗi khi tải file lên");
        }
      }

      // 3. Gửi câu hỏi
      const response = await fetch("http://localhost:8000/ask", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ question: currentInput }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "AI gặp sự cố khi trả lời");
      }

      const data = await response.json();
      
      // 4. Cập nhật tin nhắn của Bot
      setMessages((prev) => [...prev, { role: "bot", content: data.answer }]);
      
    } catch (error: any) {
      // Hiển thị lỗi cụ thể từ Backend
      setMessages((prev) => [
        ...prev,
        { role: "bot", content: `❌ ${error.message}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-chat-bg">
      {/* Sidebar - [cite: 385, 389] */}
      <aside className="w-64 bg-sidebar-bg p-4 flex flex-col border-r border-white/10 md:flex">
        <button className="flex items-center gap-3 px-3 py-2 border border-white/20 rounded-md hover:bg-white/5 transition-all text-sm">
          <Plus size={16} /> New Chat
        </button>
        <div className="flex-1 mt-4 overflow-y-auto">
          <p className="text-[10px] font-bold text-gray-500 uppercase px-3 mb-2">
            History
          </p>
          <div className="px-3 py-2 text-sm hover:bg-input-bg rounded-lg cursor-pointer truncate">
            Dự án SmartDoc AI 2026
          </div>
        </div>
      </aside>

      {/* Main Area - [cite: 393, 396, 397] */}
      <main className="flex-1 flex flex-col relative overflow-hidden">
        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto p-4 md:p-10 space-y-6">
          <div className="max-w-3xl mx-auto">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-4 mb-8 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === "bot" ? "bg-bot-green" : "bg-blue-600"}`}
                >
                  {msg.role === "bot" ? <Bot size={18} /> : <User size={18} />}
                </div>
                <div
                  className={`max-w-[85%] p-1 rounded-lg ${msg.role === "user" ? "text-right" : ""}`}
                >
                  {msg.file && (
                    <div className="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-blue-400 mb-2">
                      <Paperclip size={12} /> {msg.file}
                    </div>
                  )}
                  <p className="text-base leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </p>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-4 mb-8">
                <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 bg-bot-green">
                  <Bot size={18} />
                </div>
                <div className="max-w-[85%] p-2 bg-white/5 rounded-lg">
                  <TypingIndicator />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Input Form - [cite: 396] */}
        <div className="p-4 bg-linear-to-t from-chat-bg via-chat-bg to-transparent">
          <div className="max-w-3xl mx-auto">
            <AnimatePresence>
              {file && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 text-xs text-blue-400 mb-2 px-2"
                >
                  <Paperclip size={14} /> {file.name}
                  <button onClick={() => setFile(null)}>
                    <X size={14} />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
            <div className="bg-input-bg rounded-2xl border border-white/10 shadow-2xl p-2">
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Hỏi bất cứ điều gì..."
                className="w-full bg-transparent border-none focus:ring-0 py-3 px-4 resize-none"
              />
              <div className="flex justify-between items-center px-2 pb-2">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 hover:bg-white/5 rounded-full text-gray-400"
                >
                  <UploadCloud size={20} />
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  hidden
                  accept=".pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
                <button
                  onClick={handleSend}
                  className={`p-2 rounded-xl transition-all ${input || file ? "bg-white text-black" : "bg-gray-600 text-gray-800"}`}
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default ChatInterface;
