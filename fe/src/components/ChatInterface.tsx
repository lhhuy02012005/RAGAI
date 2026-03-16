import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Plus,
  Paperclip,
  User,
  Bot,
  UploadCloud,
  LogOut,
  X,
  Menu,
  Trash2,
  Database,
  Info,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Loader2
} from "lucide-react";
import { v4 as uuidv4 } from "uuid";
import TypingIndicator from "./TypingIndicator";
import { encryptMessage, decryptMessage } from "../lib/crypto";

const rawApiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_URL = rawApiUrl.endsWith("/") ? rawApiUrl.slice(0, -1) : rawApiUrl;

interface Source {
  page: string;
  source: string;
  content: string;
}

interface Message {
  id: string;
  role: "user" | "bot";
  content: string;
  files?: string[];
  sources?: Source[];
  confidence?: number;
  isError?: boolean;
  retryQuestion?: string;
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

const LIMIT_CONV = 15;
const LIMIT_MSG = 20;

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  token,
  masterKey,
  onLogout,
}) => {
  const [conversations, setConversations] = useState<Chat[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // States cho Phân trang
  const [convPage, setConvPage] = useState(0);
  const [hasMoreConv, setHasMoreConv] = useState(true);
  const [msgPage, setMsgPage] = useState(0);
  const [hasMoreMsg, setHasMoreMsg] = useState(true);
  const [isFetchingMoreMsg, setIsFetchingMoreMsg] = useState(false);
  
  // State xử lý Retry
  const [retryingMessageId, setRetryingMessageId] = useState<string | null>(null);

  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(100);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Tự động giãn nở textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  // Tải danh sách hội thoại
  const fetchConversations = useCallback(async (page: number) => {
    try {
      const skip = page * LIMIT_CONV;
      const res = await fetch(`${API_URL}/conversations?skip=${skip}&limit=${LIMIT_CONV}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.length < LIMIT_CONV) setHasMoreConv(false);
        const newChats = data.map((c: any) => ({
          id: c.id,
          title: c.title || "Cuộc hội thoại cũ",
          messages: [],
          isLoading: false,
        }));
        setConversations((prev) => (page === 0 ? newChats : [...prev, ...newChats]));
      }
    } catch (e) {
      console.error("Lỗi fetch conversations", e);
    }
  }, [token]);

  useEffect(() => {
    fetchConversations(0);
  }, [fetchConversations]);

  // Logic hỏi AI
  const askServer = useCallback(
    async (question: string, conversationId: string) => {
      const encrypted = await encryptMessage(question, masterKey);
      const response = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: new URLSearchParams({
          question_enc: encrypted.cipher,
          question_raw: question,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || "Ask API failed");
      }

      return response.json();
    },
    [masterKey, token]
  );

  // Tải lịch sử tin nhắn
  const loadHistory = async (convId: string, page: number = 0) => {
    if (isFetchingMoreMsg) return;
    setIsFetchingMoreMsg(true);
    try {
      const skip = page * LIMIT_MSG;
      const res = await fetch(`${API_URL}/history/${convId}?skip=${skip}&limit=${LIMIT_MSG}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Không tải được lịch sử");

      const rawMessages = await res.json();
      if (rawMessages.length < LIMIT_MSG) setHasMoreMsg(false);

      const decryptedMessages: Message[] = await Promise.all(
        rawMessages.map(async (msg: any, idx: number) => {
          const base: Message = {
            id: msg.id ? `srv_${msg.id}` : `srv_${page}_${idx}_${Date.now()}`,
            role: msg.role,
            content: msg.content,
          };
          if (msg.role === "user") {
            try {
              return { ...base, content: await decryptMessage(msg.content, masterKey) };
            } catch {
              return { ...base, content: "[Lỗi giải mã]" };
            }
          }
          return base;
        })
      );

      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== convId) return c;
          const merged = page === 0 ? decryptedMessages : [...decryptedMessages, ...c.messages];
          const dedup = new Map<string, Message>();
          merged.forEach((m) => dedup.set(m.id, m));
          return { ...c, messages: Array.from(dedup.values()) };
        })
      );
    } finally {
      setIsFetchingMoreMsg(false);
    }
  };

  // Khôi phục ID từ localstorage (Chống chớp màn hình bằng cách kiểm tra activeId)
  useEffect(() => {
    const savedId = localStorage.getItem("lastActiveChatId");
    if (savedId && !activeId && conversations.length > 0) {
        const exists = conversations.some(c => c.id === savedId);
        if (exists) setActiveId(savedId);
    }
  }, [conversations, activeId]);

  // Tải tin nhắn khi đổi hội thoại
  useEffect(() => {
    if (activeId) {
      localStorage.setItem("lastActiveChatId", activeId);
      const chat = conversations.find((c) => c.id === activeId);
      if (chat && chat.messages.length === 0 && chat.title !== "Hội thoại mới") {
        setMsgPage(0);
        setHasMoreMsg(true);
        loadHistory(activeId, 0);
      }
      setIsSidebarOpen(false);
    }
  }, [activeId]);

  // Cuộn xuống đáy khi có tin nhắn mới
  useEffect(() => {
    if (msgPage === 0 && !isFetchingMoreMsg) {
      chatEndRef.current?.scrollIntoView({ behavior: "auto" });
    }
  }, [conversations, activeId, msgPage, isFetchingMoreMsg]);

  // Xử lý cuộn tin nhắn cũ
  const handleChatScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight } = e.currentTarget;
    if (scrollTop <= 10 && hasMoreMsg && !isFetchingMoreMsg && activeId) {
      const prevHeight = scrollHeight;
      const prevTop = scrollTop;
      const nextPage = msgPage + 1;
      setMsgPage(nextPage);

      loadHistory(activeId, nextPage).then(() => {
        requestAnimationFrame(() => {
          if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop =
              chatContainerRef.current.scrollHeight - prevHeight + prevTop;
          }
        });
      });
    }
  };

  // Xử lý cuộn Sidebar
  const handleSidebarScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop <= clientHeight + 50 && hasMoreConv) {
      const nextPage = convPage + 1;
      setConvPage(nextPage);
      fetchConversations(nextPage);
    }
  };

  const createNewChat = () => {
    const newId = uuidv4();
    const newChat: Chat = {
      id: newId,
      title: "Hội thoại mới",
      messages: [
        {
          id: uuidv4(),
          role: "bot",
          content: "Chào bạn! Tôi là SmartDoc AI, bạn cần tôi phân tích tài liệu gì hôm nay?"
        }
      ],
      isLoading: false,
    };
    setConversations([newChat, ...conversations]);
    setActiveId(newId);
    setMsgPage(0);
    setHasMoreMsg(false);
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Xóa toàn bộ lịch sử chat?")) return;
    const res = await fetch(`${API_URL}/clear-history`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setConversations([]);
      setActiveId(null);
      localStorage.removeItem("lastActiveChatId");
    }
  };

  const handleClearVector = async () => {
    if (!window.confirm("Xóa toàn bộ kho tài liệu?")) return;
    const res = await fetch(`${API_URL}/clear-vector-store`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) alert("Kho tri thức đã sạch sẽ!");
  };

  const retryFailedQuestion = async (chatId: string, failedMessageId: string, question: string) => {
    setRetryingMessageId(failedMessageId);
    try {
      const data = await askServer(question, chatId);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === chatId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === failedMessageId
                    ? {
                        id: uuidv4(),
                        role: "bot",
                        content: data.answer_raw,
                        sources: data.sources,
                        confidence: data.confidence,
                      }
                    : m
                ),
              }
            : c
        )
      );
    } catch (e) {
      console.error("Retry failed", e);
    } finally {
      setRetryingMessageId(null);
    }
  };

  const handleSend = async () => {
    const currentChat = conversations.find((c) => c.id === activeId);
    if ((!input.trim() && files.length === 0) || !activeId || currentChat?.isLoading) return;

    const currentInput = input.trim();
    const currentFiles = [...files];
    setInput("");
    setFiles([]);

    if (fileInputRef.current) fileInputRef.current.value = "";

    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId
          ? {
              ...c,
              messages: [
                ...c.messages,
                {
                  id: uuidv4(),
                  role: "user",
                  content: currentInput || "Nạp tài liệu mới",
                  files: currentFiles.map((f) => f.name),
                },
              ],
              isLoading: true,
            }
          : c
      )
    );

    try {
      if (currentFiles.length > 0) {
        const formData = new FormData();
        currentFiles.forEach((f) => formData.append("files", f));
        formData.append("chunk_size", chunkSize.toString());
        formData.append("chunk_overlap", chunkOverlap.toString());

        await fetch(`${API_URL}/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
      }

      const data = await askServer(currentInput || "Tóm tắt các tài liệu tôi vừa nạp", activeId);

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? {
                ...c,
                title: c.title === "Hội thoại mới" && currentInput 
                    ? currentInput.substring(0, 20) 
                    : c.title,
                messages: [
                  ...c.messages,
                  {
                    id: uuidv4(),
                    role: "bot",
                    content: data.answer_raw,
                    sources: data.sources,
                    confidence: data.confidence,
                  },
                ],
                isLoading: false,
              }
            : c
        )
      );
    } catch {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? {
                ...c,
                messages: [
                  ...c.messages,
                  {
                    id: uuidv4(),
                    role: "bot",
                    content: "❌ Lỗi: Server RAG không phản hồi.",
                    isError: true,
                    retryQuestion: currentInput || "Tóm tắt các tài liệu tôi vừa nạp",
                  },
                ],
                isLoading: false,
              }
            : c
        )
      );
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    if (files.length === 1 && fileInputRef.current) fileInputRef.current.value = "";
  };

  const currentChat = conversations.find((c) => c.id === activeId);

  return (
    <div className="flex h-screen bg-[#0b0d11] text-white relative overflow-hidden font-sans">
      {isSidebarOpen && <div className="fixed inset-0 bg-black/60 z-40 md:hidden" onClick={() => setIsSidebarOpen(false)} />}

      <aside className={`fixed md:relative z-50 w-72 h-full bg-[#17191e] p-4 flex flex-col border-r border-white/5 transition-transform duration-300 ${isSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}>
        <button onClick={createNewChat} className="flex items-center gap-3 px-3 py-3 border border-white/10 rounded-xl hover:bg-white/10 transition-all text-sm font-semibold mb-6">
          <Plus size={18} /> New Chat
        </button>

        <div onScroll={handleSidebarScroll} className="flex-1 overflow-y-auto space-y-2 scrollbar-hide">
          <p className="text-[10px] font-black text-gray-500 uppercase px-2 mb-2 tracking-widest">Hội thoại</p>
          {conversations.map((chat) => (
            <div
              key={chat.id}
              onClick={() => setActiveId(chat.id)}
              className={`px-4 py-3 text-sm rounded-xl cursor-pointer truncate transition-all ${activeId === chat.id ? "bg-white/10 text-white shadow-sm" : "text-gray-400 hover:bg-white/5"}`}
            >
              {chat.title}
            </div>
          ))}
          {isSidebarOpen && !hasMoreConv && conversations.length > 5 && (
            <p className="text-[10px] text-center text-gray-600 py-2 italic">Đã hết lịch sử</p>
          )}
        </div>

        <div className="mt-4 p-4 bg-white/5 rounded-2xl border border-white/10 space-y-4">
          <p className="text-[10px] font-black text-blue-400 uppercase flex items-center gap-2"><Database size={12} /> RAG Config</p>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-[10px] text-gray-400 mb-1"><span>Chunk Size</span><span>{chunkSize}</span></div>
              <input type="range" min="500" max="2000" step="500" value={chunkSize} onChange={(e) => setChunkSize(parseInt(e.target.value))} className="w-full h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
            </div>
            <div>
              <div className="flex justify-between text-[10px] text-gray-400 mb-1"><span>Overlap</span><span>{chunkOverlap}</span></div>
              <input type="range" min="50" max="200" step="50" value={chunkOverlap} onChange={(e) => setChunkOverlap(parseInt(e.target.value))} className="w-full h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500" />
            </div>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-white/5 space-y-1">
          <button onClick={handleClearHistory} className="w-full flex items-center gap-2 text-gray-500 hover:text-red-400 text-xs p-3 transition-colors rounded-lg hover:bg-red-400/5"><Trash2 size={14} /> Clear History</button>
          <button onClick={handleClearVector} className="w-full flex items-center gap-2 text-gray-500 hover:text-orange-400 text-xs p-3 transition-colors rounded-lg hover:bg-orange-400/5"><Database size={14} /> Clear Vector Store</button>
          <button onClick={() => { localStorage.removeItem("lastActiveChatId"); onLogout(); }} className="w-full flex items-center gap-2 text-gray-500 hover:text-white text-xs p-3 transition-colors rounded-lg hover:bg-white/5"><LogOut size={14} /> Logout</button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col relative w-full bg-[#0b0d11]">
        <header className="flex items-center justify-between p-4 border-b border-white/5 md:hidden">
          <button onClick={() => setIsSidebarOpen(true)} className="p-2 text-gray-400"><Menu size={24} /></button>
          <h1 className="text-sm font-black tracking-tighter uppercase">SmartDoc</h1>
          <div className="w-10" />
        </header>

        {currentChat ? (
          <>
            <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 md:p-10 scrollbar-hide" style={{ scrollBehavior: 'auto' }}>
              <div className="max-w-3xl mx-auto space-y-10">
                {isFetchingMoreMsg && <div className="flex justify-center py-4"><Loader2 size={24} className="text-emerald-500 animate-spin" /></div>}

                {currentChat.messages.map((msg) => (
                  <div key={msg.id} className={`flex gap-4 md:gap-6 animate-in fade-in slide-in-from-bottom-2 duration-300 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`w-9 h-9 md:w-10 md:h-10 rounded-full flex items-center justify-center shrink-0 shadow-inner ${msg.role === "bot" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-blue-600/10 text-blue-400 border border-blue-600/20"}`}>
                      {msg.role === "bot" ? <Bot size={20} /> : <User size={20} />}
                    </div>
                    <div className={`max-w-[88%] ${msg.role === "user" ? "text-right" : ""}`}>
                      {msg.files?.map((fname, idx) => (
                        <div key={idx} className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-1.5 text-[10px] text-blue-400 mb-2 ml-1">
                          <Paperclip size={10} /> {fname}
                        </div>
                      ))}
                      <div className={`p-4 md:p-5 rounded-2xl text-sm md:text-[15px] leading-relaxed whitespace-pre-wrap shadow-sm ${msg.isError ? "border border-red-500/50 bg-red-500/5 text-red-400" : msg.role === "bot" ? "bg-white/3 border border-white/5" : "bg-blue-600/8 border border-blue-600/20"}`}>
                        {msg.content}
                        {msg.isError && msg.retryQuestion && (
                          <button onClick={() => retryFailedQuestion(currentChat.id, msg.id, msg.retryQuestion!)} disabled={retryingMessageId === msg.id} className="mt-3 flex items-center gap-2 text-[11px] font-bold bg-red-500/20 hover:bg-red-500/40 px-3 py-1.5 rounded-lg transition-all">
                            {retryingMessageId === msg.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Retry
                          </button>
                        )}
                      </div>
                      {msg.role === "bot" && !msg.isError && typeof msg.confidence === "number" && (
                        <div className={`mt-2 flex items-center gap-1 text-[10px] font-medium ${msg.confidence >= 0.75 ? "text-emerald-400" : "text-amber-400"}`}>
                          {msg.confidence >= 0.75 ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />} Độ tin cậy: {Math.round(msg.confidence * 100)}%
                        </div>
                      )}
                      {msg.role === "bot" && !msg.isError && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {msg.sources.map((src, idx) => (
                            <div key={idx} className="group relative">
                              <span className="flex items-center gap-1.5 text-[10px] bg-white/4 border border-white/10 px-2.5 py-1.5 rounded-lg text-gray-400 cursor-help hover:bg-white/8 transition-all">
                                <Info size={11} className="text-emerald-500" /> Trang {src.page} - {src.source}
                              </span>
                              <div className="absolute bottom-full left-0 mb-3 hidden group-hover:block w-80 p-4 bg-[#1e2227] border border-white/10 rounded-2xl shadow-2xl z-50">
                                <p className="text-[10px] text-emerald-400 mb-2 font-bold tracking-tight">Trích xuất nội dung:</p>
                                <p className="text-[11px] text-gray-300 leading-relaxed italic">"{src.content}..."</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {currentChat.isLoading && <div className="flex gap-4"><div className="w-9 h-9 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center border border-emerald-500/20"><Bot size={20} /></div><TypingIndicator /></div>}
                <div ref={chatEndRef} />
              </div>
            </div>

            <div className="p-4 bg-linear-to-t from-[#0b0d11] via-[#0b0d11] to-transparent">
              <div className="max-w-3xl mx-auto">
                <div className="flex flex-wrap gap-2 mb-3">
                  {files.map((f, i) => (
                    <div key={i} className="bg-blue-600/10 border border-blue-500/20 rounded-xl px-3 py-1.5 flex items-center gap-2 text-[11px] text-blue-300">
                      <Paperclip size={12} /> <span className="max-w-35 truncate">{f.name}</span>
                      <button onClick={() => removeFile(i)} className="hover:text-white transition-colors"><X size={14} /></button>
                    </div>
                  ))}
                </div>
                <div className="bg-[#17191e] rounded-2xl border border-white/10 shadow-2xl focus-within:border-white/20 transition-all">
                  <textarea ref={textareaRef} rows={1} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if(!currentChat.isLoading) handleSend(); } }} placeholder="Đặt câu hỏi về tài liệu..." className="w-full bg-transparent border-none focus:ring-0 py-4 px-6 text-sm md:text-base min-h-14 overflow-y-auto" />
                  <div className="flex justify-between items-center px-4 pb-3">
                    <button onClick={() => fileInputRef.current?.click()} className="p-2.5 text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all"><UploadCloud size={20} /></button>
                    <input type="file" ref={fileInputRef} hidden multiple accept=".pdf,.docx" onChange={(e) => setFiles((prev) => [...prev, ...Array.from(e.target.files || [])])} />
                    <button onClick={handleSend} disabled={(!input.trim() && files.length === 0) || currentChat.isLoading} className={`p-2.5 rounded-xl transition-all ${((input.trim() || files.length > 0) && !currentChat.isLoading) ? "bg-white text-black hover:bg-gray-200" : "bg-white/5 text-gray-600"}`}><Send size={18} /></button>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center space-y-6 px-6 text-center">
            <div className="p-8 bg-white/2 rounded-full border border-white/5 relative">
              <Bot size={64} className="text-emerald-500/20" />
              <div className="absolute inset-0 bg-emerald-500/10 blur-3xl rounded-full -z-10" />
            </div>
            <div className="max-w-md">
                <h3 className="text-white font-bold text-2xl tracking-tight">Hệ thống SmartDoc RAG</h3>
                <p className="text-sm text-gray-400 mt-3 leading-relaxed">Chọn một hội thoại hoặc tạo mới để bắt đầu phân tích tài liệu.</p>
            </div>
            <button onClick={createNewChat} className="bg-white text-black px-10 py-3.5 rounded-full font-bold text-sm hover:scale-105 transition-all shadow-xl">Khởi tạo hội thoại mới</button>
          </div>
        )}
      </main>
    </div>
  );
};

export default ChatInterface;