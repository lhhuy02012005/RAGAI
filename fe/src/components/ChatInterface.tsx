import React, { useState, useRef, useEffect } from "react";
// Thêm icon Menu để đóng mở sidebar
import { Send, Plus, Paperclip, User, Bot, UploadCloud, LogOut, X, Menu } from "lucide-react";
import { v4 as uuidv4 } from "uuid";
import TypingIndicator from "./TypingIndicator";
import { encryptMessage, decryptMessage } from "../lib/crypto";

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
  
  // --- STATE MỚI CHO SIDEBAR MOBILE ---
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchConversations = async () => {
      try {
        const res = await fetch(`${API_URL}/conversations`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          const loadedChats = data.map((c: any) => ({
            id: c.id,
            title: c.title || "Cuộc hội thoại cũ",
            messages: [],
            isLoading: false
          }));
          setConversations(loadedChats);
        }
      } catch (e) {
        console.error("Không thể tải danh sách hội thoại");
      }
    };
    fetchConversations();
  }, [token]);

  useEffect(() => {
    if (activeId) {
      const chat = conversations.find(c => c.id === activeId);
      if (chat && chat.messages.length === 0) {
        loadHistory(activeId);
      }
      // Tự động đóng sidebar trên mobile khi chọn chat
      setIsSidebarOpen(false);
    }
  }, [activeId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversations, activeId]);

  const loadHistory = async (convId: string) => {
    try {
      const res = await fetch(`${API_URL}/history/${convId}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const rawMessages = await res.json();

      const decryptedMessages = await Promise.all(rawMessages.map(async (msg: any) => {
        if (msg.role === "user") {
          try {
            const decryptedText = await decryptMessage(msg.content, masterKey);
            return { ...msg, content: decryptedText };
          } catch (e) {
            return { ...msg, content: "[Lỗi: Không thể giải mã tin nhắn này]" };
          }
        }
        return msg;
      }));

      setConversations(prev => prev.map(c => 
        c.id === convId ? { ...c, messages: decryptedMessages.length > 0 ? decryptedMessages : [{ role: "bot", content: "Chào bạn! Tôi có thể giúp gì cho bạn hôm nay?" }] } : c
      ));
    } catch (error) {
      console.error("Lỗi tải lịch sử:", error);
    }
  };

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
    setIsSidebarOpen(false); // Đóng sidebar khi tạo mới trên mobile
  };

  const currentChat = conversations.find((c) => c.id === activeId);

  const handleSend = async () => {
    if ((!input.trim() && !file) || !activeId) return;

    const currentInput = input;
    const currentFile = file;
    setInput("");
    setFile(null);

    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId
          ? {
              ...c,
              messages: [...c.messages, { role: "user", content: currentInput, file: currentFile?.name }],
              isLoading: true,
            }
          : c
      )
    );

    try {
      if (currentFile) {
        const formData = new FormData();
        formData.append("file", currentFile);
        await fetch(`${API_URL}/upload`, {
          method: "POST",
          headers: { "Authorization": `Bearer ${token}` },
          body: formData,
        });
      }

      const encrypted = await encryptMessage(currentInput, masterKey);
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: new URLSearchParams({
          question_enc: encrypted.cipher,
          question_raw: currentInput,
          conversation_id: activeId,
        }),
      });
      const data = await response.json();

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? {
                ...c,
                title: c.messages.length <= 2 ? currentInput.substring(0, 25) + "..." : c.title,
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
            ? { ...c, messages: [...c.messages, { role: "bot", content: "❌ Lỗi kết nối Server" }], isLoading: false }
            : c
        )
      );
    }
  };

  return (
    <div className="flex h-screen bg-[#0b0d11] text-white relative overflow-hidden">
      
      {/* 1. OVERLAY CHO MOBILE: Khi mở sidebar thì làm mờ màn hình chat */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-40 md:hidden transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* 2. SIDEBAR CẢI TIẾN: Thêm hiệu ứng trượt (transform) */}
      <aside className={`
        fixed md:relative z-50 w-72 h-full bg-[#17191e] p-4 flex flex-col border-r border-white/5 transition-transform duration-300 ease-in-out
        ${isSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
      `}>
        <div className="flex items-center justify-between mb-6 md:block">
          <button onClick={createNewChat} className="flex-1 flex items-center gap-3 px-3 py-3 border border-white/10 rounded-xl hover:bg-white/5 transition-all text-sm font-medium">
            <Plus size={18} /> New Chat
          </button>
          {/* Nút đóng sidebar chỉ hiện trên mobile */}
          <button onClick={() => setIsSidebarOpen(false)} className="ml-2 p-2 md:hidden text-gray-400">
            <X size={24} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2 scrollbar-hide">
          <p className="text-[10px] font-bold text-gray-500 uppercase px-2 mb-2">Gần đây</p>
          {conversations.map((chat) => (
            <div 
              key={chat.id} 
              onClick={() => setActiveId(chat.id)} 
              className={`px-3 py-3 text-sm rounded-xl cursor-pointer truncate transition-all ${activeId === chat.id ? "bg-white/10 text-white" : "text-gray-400 hover:bg-white/5"}`}
            >
              {chat.title}
            </div>
          ))}
        </div>
        
        <button onClick={onLogout} className="mt-4 flex items-center gap-2 text-gray-500 hover:text-red-400 text-sm p-2 transition-colors">
          <LogOut size={16} /> Đăng xuất
        </button>
      </aside>

      {/* 3. NỘI DUNG CHÍNH (MAIN CONTENT) */}
      <main className="flex-1 flex flex-col relative overflow-hidden w-full">
        
        {/* HEADER CHO MOBILE: Chứa nút Menu để mở Sidebar */}
        <header className="flex items-center justify-between p-4 border-b border-white/5 md:hidden bg-[#0b0d11]/80 backdrop-blur-md sticky top-0 z-30">
          <button onClick={() => setIsSidebarOpen(true)} className="p-2 text-gray-400 hover:text-white transition-colors">
            <Menu size={24} />
          </button>
          <h1 className="text-sm font-bold tracking-tight text-white/80">SmartDoc AI</h1>
          <div className="w-10" /> {/* Spacer để cân bằng layout */}
        </header>

        {currentChat ? (
          <>
            <div className="flex-1 overflow-y-auto p-4 md:p-10 scrollbar-hide">
              <div className="max-w-3xl mx-auto space-y-8">
                {currentChat.messages.map((msg, i) => (
                  <div key={i} className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`w-8 h-8 md:w-10 md:h-10 rounded-full flex items-center justify-center shrink-0 shadow-lg ${msg.role === "bot" ? "bg-bot-green" : "bg-blue-600"}`}>
                      {msg.role === "bot" ? <Bot size={18} /> : <User size={18} />}
                    </div>
                    <div className={`max-w-[85%] md:max-w-[80%] ${msg.role === "user" ? "text-right" : ""}`}>
                      {msg.file && (
                        <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/30 rounded-lg px-3 py-1 text-xs text-blue-400 mb-2">
                          <Paperclip size={12} /> {msg.file}
                        </div>
                      )}
                      <div className={`p-4 rounded-2xl text-sm md:text-base leading-relaxed whitespace-pre-wrap shadow-sm ${msg.role === "bot" ? "bg-white/5 border border-white/5" : "bg-blue-600/10 border border-blue-600/20"}`}>
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

            {/* Input Area: Tối ưu khoảng cách cho mobile */}
            <div className="p-3 md:p-4 bg-linear-to-t from-[#0b0d11] via-[#0b0d11] to-transparent">
              <div className="max-w-3xl mx-auto">
                {file && (
                  <div className="flex items-center gap-2 mb-2 animate-in fade-in slide-in-from-bottom-2">
                    <div className="bg-blue-600/20 border border-blue-500/50 rounded-lg px-3 py-2 flex items-center gap-2">
                      <Paperclip size={14} className="text-blue-400" />
                      <span className="text-xs text-blue-300 font-medium truncate max-w-37.5">{file.name}</span>
                      <button onClick={() => setFile(null)} className="ml-1 hover:text-white transition-colors"><X size={14} /></button>
                    </div>
                  </div>
                )}
                <div className="bg-[#17191e] rounded-2xl border border-white/10 shadow-xl focus-within:border-white/20 transition-all">
                  <textarea
                    rows={1}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                    placeholder={file ? "Phân tích file..." : "Hỏi AI bảo mật..."}
                    className="w-full bg-transparent border-none focus:ring-0 py-3 md:py-4 px-4 md:px-5 resize-none text-white text-sm md:text-base min-h-12.5 max-h-37.5"
                  />
                  <div className="flex justify-between items-center px-3 pb-3">
                    <button onClick={() => fileInputRef.current?.click()} className={`p-2 rounded-lg transition-colors ${file ? "text-blue-400 bg-blue-400/10" : "text-gray-400 hover:bg-white/5"}`}><UploadCloud size={20} /></button>
                    <input type="file" ref={fileInputRef} hidden accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
                    <button onClick={handleSend} disabled={!input.trim() && !file} className={`p-2 md:p-2.5 rounded-xl transition-all ${ (input.trim() || file) ? "bg-white text-black hover:bg-gray-200" : "bg-white/5 text-gray-600 cursor-not-allowed" }`}><Send size={18} /></button>
                  </div>
                </div>
                <p className="hidden md:block text-[10px] text-center text-gray-500 mt-3 italic">Dữ liệu mã hóa Zero-Knowledge tại trình duyệt.</p>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 space-y-4 px-6 text-center">
             <div className="p-6 bg-white/5 rounded-full border border-white/5 animate-pulse"><Bot size={48} className="opacity-20" /></div>
             <div className="max-w-xs">
                <h3 className="text-white font-medium text-lg">Chào mừng tới SmartDoc</h3>
                <p className="text-sm text-gray-400 mt-2">Phân tích tài liệu PDF nội bộ với tính bảo mật tuyệt đối.</p>
             </div>
             <button onClick={createNewChat} className="bg-white text-black px-8 py-2.5 rounded-full font-bold text-sm hover:bg-gray-200 transition-all shadow-lg active:scale-95">
               Bắt đầu Chat mới
             </button>
          </div>
        )}
      </main>
    </div>
  );
};

export default ChatInterface;