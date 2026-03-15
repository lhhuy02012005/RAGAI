import React, { useEffect, useState } from "react";
import { ShieldCheck, Lock, ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import { deriveKeyFromPin, saveKeyToStorage, unwrapKey } from "../lib/crypto";

// Helper: Lấy userId từ JWT Token (trường 'sub')
const getUserIdFromToken = (token: string): string | null => {
  console.log("🔍 Token nhận được để trích xuất userId:", token); // Debug: Kiểm tra token có đúng không trước khi giải mã
  if (!token || typeof token !== 'string') return null;
  

  try {
    // 1. Loại bỏ chữ "Bearer " nếu có
    const cleanToken = token.startsWith("Bearer ") ? token.split(" ")[1] : token;
    const parts = cleanToken.split(".");
    if (parts.length !== 3) return null;

    // 2. Lấy phần Payload (phần giữa)
    let base64Url = parts[1];
    
    // 3. Thay thế ký tự đặc biệt JWT sang Base64 chuẩn
    let base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");

    // 4. Thêm Padding (dấu =) nếu thiếu để atob không bị lỗi
    while (base64.length % 4 !== 0) {
      base64 += "=";
    }

    // 5. Giải mã an toàn cho cả ký tự Unicode
    const jsonPayload = decodeURIComponent(
      window.atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );

    const decoded = JSON.parse(jsonPayload);
    console.log("🔍 Payload thực tế nhận được:", decoded);
    
    // Ép kiểu về string để làm Key cho localStorage
    return decoded.sub ? String(decoded.sub) : null;
  } catch (e) {
    console.error("❌ Lỗi giải mã JWT:", e);
    return null;
  }
};

interface PinModalProps {
  token: string; // Cần token để xác định user đang đăng nhập
  deviceSecret: string;
  onKeyReady: (key: CryptoKey) => void;
}

const PinModal: React.FC<PinModalProps> = ({
  token,
  deviceSecret,
  onKeyReady,
}) => {
  const [pin, setPin] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const userId = React.useMemo(() => getUserIdFromToken(token), [token]);
  console.log("User ID từ token:", userId); // Debug: Kiểm tra userId có được trích xuất đúng không

  // 1. Tự động mở khóa (Auto-unlock) nếu đã có key của User này trong máy
  useEffect(() => {
    const autoUnlock = async () => {
      if (!userId || !deviceSecret) return;

      // Tìm đúng cặp key/iv dành riêng cho User ID này
      const wrappedKey = localStorage.getItem(`wrapped_key_${userId}`);
      const iv = localStorage.getItem(`key_iv_${userId}`);

      if (wrappedKey && iv) {
        try {
          const key = await unwrapKey(wrappedKey, iv, deviceSecret);
          onKeyReady(key);
        } catch (e) {
          console.log(
            "Key cũ không khớp với thiết bị hoặc mã PIN đã thay đổi.",
          );
          // Nếu không khớp, ta xóa key cũ để người dùng nhập lại PIN mới
          localStorage.removeItem(`wrapped_key_${userId}`);
          localStorage.removeItem(`key_iv_${userId}`);
        }
      }
    };
    autoUnlock();
  }, [deviceSecret, userId, onKeyReady]);

  // 2. Xử lý khi người dùng nhập PIN và nhấn nút
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId) {
      alert("Lỗi xác thực người dùng. Vui lòng đăng nhập lại.");
      return;
    }

    setIsProcessing(true);
    try {
      // Tái tạo Master Key từ PIN (kèm salt cố định của hệ thống)
      const masterKey = await deriveKeyFromPin(pin, "smartdoc_secure_salt");

      // Lưu key vào LocalStorage với tên biến có gắn User ID để không bị ghi đè
      await saveKeyToStorage(masterKey, deviceSecret, userId);

      // Trả key về cho App để bắt đầu giải mã history
      onKeyReady(masterKey);
    } catch (error) {
      console.error("Lỗi bảo mật:", error);
      alert("Không thể thiết lập lớp bảo mật. Hãy thử lại.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="w-full max-w-md bg-[#17191e] rounded-3xl border border-white/10 p-8 shadow-2xl text-center"
      >
        <div className="flex justify-center mb-6">
          <div className="p-4 bg-blue-500/10 rounded-full text-blue-400">
            <ShieldCheck size={48} />
          </div>
        </div>

        <h2 className="text-2xl font-bold text-white mb-2">Xác thực Mã PIN</h2>
        <p className="text-gray-400 text-sm mb-8">
          Mã PIN dùng để bảo vệ quyền riêng tư và giải mã tin nhắn. <br />
          <span className="text-orange-400/80 text-xs font-medium italic">
            Mã PIN được xử lý Zero-Knowledge tại trình duyệt.
          </span>
        </p>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="relative">
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500">
              <Lock size={18} />
            </div>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="Nhập mã PIN cá nhân..."
              className="w-full py-4 pl-12 pr-4 bg-white/5 border border-white/10 rounded-xl text-white text-lg tracking-[0.5em] focus:ring-2 focus:ring-blue-500 outline-none transition-all placeholder:tracking-normal placeholder:text-sm"
              disabled={isProcessing}
              autoFocus
            />
          </div>

          <button
            type="submit"
            disabled={isProcessing || pin.length < 4}
            className="w-full py-4 bg-white text-black font-bold rounded-xl flex items-center justify-center gap-2 hover:bg-gray-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isProcessing ? "Đang giải mã..." : "Kích hoạt bảo mật"}
            {!isProcessing && <ArrowRight size={18} />}
          </button>
        </form>
      </motion.div>
    </div>
  );
};

export default PinModal;
