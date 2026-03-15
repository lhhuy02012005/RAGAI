import React, { useState, useRef, useEffect } from "react";
import { Send, Plus, Paperclip, User, Bot, UploadCloud, LogOut, X } from "lucide-react";
import { v4 as uuidv4 } from "uuid";
import TypingIndicator from "./TypingIndicator";
import { encryptMessage } from "../lib/crypto";

// Tự động nhận diện API URL từ môi trường (.env)
const rawApiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_URL = rawApiUrl.endsWith("/") ? rawApiUrl.slice(0, -1) : rawApiUrl;

interface Message {
  role: "user" | "bot";
  content: string;
  file?: string;
}

interface Chat {
  id: string;
  title: string;
  messages: Message[];
  isLoading: boolean;
}

interface ChatInterfaceProps {
  token: string;
  masterKey: CryptoKey;
  onLogout: () => void;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ token, masterKey, onLogout }) => {
  const [conversations, setConversations] = useState<Chat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Tự động cuộn xuống cuối khi có tin nhắn mới
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversations, activeId]);

  const createNewChat = () => {
    const newId = uuidv4();
    const newChat: Chat = {
      id: newId,
      title: "Cuộc hội thoại mới",
      messages: [{ role: "bot", content: "Chào bạn! Tôi có thể giúp gì cho bạn hôm nay?" }],
      isLoading: false,
    };
    setConversations([newChat, ...conversations]);
    setActiveId(newId);
  };

  const currentChat = conversations.find((c) => c.id === activeId);

  const handleSend = async () => {
    if ((!input.trim() && !file) || !activeId) return;

    const currentInput = input;
    const currentFile = file;
    
    // Reset input ngay lập tức để tạo cảm giác mượt mà
    setInput("");
    setFile(null);

    // 1. Cập nhật UI tạm thời cho tin nhắn người dùng
    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId
          ? {
              ...c,
              messages: [
                ...c.messages,
                { role: "user", content: currentInput, file: currentFile?.name },
              ],
              isLoading: true,
            }
          : c
      )
    );

    try {
      // 2. Upload file nếu có (Gọi tới Docker/Local linh hoạt)
      if (currentFile) {
        const formData = new FormData();
        formData.append("file", currentFile);
        const uploadRes = await fetch(`${API_URL}/upload`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}` },
          body: formData,
        });
        if (!uploadRes.ok) throw new Error("Không thể upload tài liệu");
      }

      // 3. Mã hóa Zero-Knowledge câu hỏi
      const encrypted = await encryptMessage(currentInput, masterKey);

      // 4. Gửi câu hỏi đến Backend
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: new URLSearchParams({
          question_enc: encrypted.cipher,
          question_raw: currentInput,
          conversation_id: activeId,
        }),
      });

      if (!response.ok) throw new Error("Lỗi kết nối bộ não AI");
      const data = await response.json();

      // 5. Cập nhật câu trả lời từ bot
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? {
                ...c,
                // Cập nhật title dựa trên câu hỏi đầu tiên nếu cần
                title: c.messages.length === 1 ? currentInput.substring(0, 25) + "..." : c.title,
                messages: [...c.messages, { role: "bot", content: data.answer_raw }],
                isLoading: false,
              }
            : c
        )
      );
    } catch (error: any) {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? {
                ...c,
                messages: [
                  ...c.messages,
                  { role: "bot", content: `❌ Lỗi: ${error.message}. Hãy kiểm tra kết nối Server.` },
                ],
                isLoading: false,
              }
            : c
        )
      );
    }
  };

  return (
    <div className="flex h-screen bg-[#0b0d11] text-white">
      {/* Sidebar */}
      <aside className="w-64 bg-[#17191e] p-4 flex flex-col border-r border-white/5">
        <button
          onClick={createNewChat}
          className="flex items-center gap-3 px-3 py-3 border border-white/10 rounded-xl hover:bg-white/5 transition-all text-sm font-medium mb-6"
        >
          <Plus size={18} /> New Chat
        </button>
        
        <div className="flex-1 overflow-y-auto space-y-2">
          <p className="text-[10px] font-bold text-gray-500 uppercase px-2 mb-2">Gần đây</p>
          {conversations.map((chat) => (
            <div
              key={chat.id}
              onClick={() => setActiveId(chat.id)}
              className={`px-3 py-3 text-sm rounded-xl cursor-pointer truncate transition-all ${
                activeId === chat.id ? "bg-white/10 text-white" : "text-gray-400 hover:bg-white/5"
              }`}
            >
              {chat.title}
            </div>
          ))}
        </div>

        <button onClick={onLogout} className="mt-4 flex items-center gap-2 text-gray-500 hover:text-red-400 text-sm p-2 transition-colors">
          <LogOut size={16} /> Đăng xuất
        </button>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden">
        {currentChat ? (
          <>
            {/* Tin nhắn */}
            <div className="flex-1 overflow-y-auto p-4 md:p-10 scrollbar-hide">
              <div className="max-w-3xl mx-auto space-y-8">
                {currentChat.messages.map((msg, i) => (
                  <div key={i} className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-lg ${
                      msg.role === "bot" ? "bg-bot-green" : "bg-blue-600"
                    }`}>
                      {msg.role === "bot" ? <Bot size={18} /> : <User size={18} />}
                    </div>
                    <div className={`max-w-[80%] ${msg.role === "user" ? "text-right" : ""}`}>
                      {msg.file && (
                        <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/30 rounded-lg px-3 py-1 text-xs text-blue-400 mb-2">
                          <Paperclip size={12} /> {msg.file}
                        </div>
                      )}
                      <div className={`p-4 rounded-2xl leading-relaxed whitespace-pre-wrap shadow-sm ${
                        msg.role === "bot" ? "bg-white/5 border border-white/5" : "bg-blue-600/10 border border-blue-600/20"
                      }`}>
                        {msg.content}
                      </div>
                    </div>
                  </div>
                ))}
                {currentChat.isLoading && (
                  <div className="flex gap-4">
                    <div className="w-8 h-8 rounded-full bg-bot-green flex items-center justify-center"><Bot size={18} /></div>
                    <TypingIndicator />
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            </div>

            {/* Vùng nhập liệu */}
            <div className="p-4 bg-linear-to-t from-[#0b0d11] via-[#0b0d11] to-transparent">
              <div className="max-w-3xl mx-auto">
                
                {/* HIỂN THỊ FILE PREVIEW KHI CHỌN */}
                {file && (
                  <div className="flex items-center gap-2 mb-2 animate-in fade-in slide-in-from-bottom-2">
                    <div className="bg-blue-600/20 border border-blue-500/50 rounded-lg px-3 py-2 flex items-center gap-2">
                      <Paperclip size={14} className="text-blue-400" />
                      <span className="text-xs text-blue-300 font-medium truncate max-w-50">{file.name}</span>
                      <button onClick={() => setFile(null)} className="ml-1 hover:text-white transition-colors">
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                )}

                <div className="bg-[#17191e] rounded-2xl border border-white/10 shadow-xl focus-within:border-white/20 transition-all">
                  <textarea
                    rows={1}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    placeholder={file ? "Đặt câu hỏi về tài liệu này..." : "Hỏi AI bảo mật..."}
                    className="w-full bg-transparent border-none focus:ring-0 py-4 px-5 resize-none text-white text-sm"
                  />
                  
                  <div className="flex justify-between items-center px-3 pb-3">
                    <div className="flex items-center gap-1">
                      <button 
                        onClick={() => fileInputRef.current?.click()} 
                        className={`p-2 rounded-lg transition-colors ${file ? "text-blue-400 bg-blue-400/10" : "text-gray-400 hover:bg-white/5"}`}
                        title="Tải lên PDF"
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
                    </div>
                    
                    <button 
                      onClick={handleSend} 
                      disabled={!input.trim() && !file}
                      className={`p-2.5 rounded-xl transition-all ${
                        (input.trim() || file) 
                          ? "bg-white text-black hover:bg-gray-200" 
                          : "bg-white/5 text-gray-600 cursor-not-allowed"
                      }`}
                    >
                      <Send size={18} />
                    </button>
                  </div>
                </div>
                <p className="text-[10px] text-center text-gray-500 mt-3">
                  Dữ liệu được mã hóa Zero-Knowledge trước khi gửi đi.
                </p>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 space-y-4">
            <div className="p-6 bg-white/5 rounded-full border border-white/5">
              <Bot size={48} className="opacity-20" />
            </div>
            <div className="text-center">
              <h3 className="text-white font-medium">SmartDoc AI</h3>
              <p className="text-sm">Chọn một cuộc hội thoại để bắt đầu phân tích dữ liệu</p>
            </div>
            <button onClick={createNewChat} className="bg-white text-black px-6 py-2 rounded-full font-medium text-sm hover:bg-gray-200 transition-all">
              Bắt đầu ngay
            </button>
          </div>
        )}
      </main>
    </div>
  );
};

export default ChatInterface;