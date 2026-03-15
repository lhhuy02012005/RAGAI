import React, { useEffect, useState } from "react";
import { ShieldCheck, Lock, ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import { deriveKeyFromPin, saveKeyToStorage, unwrapKey } from "../lib/crypto";

interface PinModalProps {
  deviceSecret: string;
  onKeyReady: (key: CryptoKey) => void;
}

const PinModal: React.FC<PinModalProps> = ({ deviceSecret, onKeyReady }) => {
  const [pin, setPin] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    const autoUnlock = async () => {
      const wrappedKey = localStorage.getItem("wrapped_key");
      const iv = localStorage.getItem("key_iv");

      if (wrappedKey && iv && deviceSecret) {
        try {
          // Tự động giải mã chìa khóa mà không cần PIN
          const key = await unwrapKey(wrappedKey, iv, deviceSecret);
          onKeyReady(key);
        } catch (e) {
          console.log("Wrapped key hết hạn hoặc sai, yêu cầu nhập PIN");
        }
      }
    };
    autoUnlock();
  }, [deviceSecret]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pin.length < 4) {
      alert("Mã PIN phải có ít nhất 4 ký tự để đảm bảo an toàn.");
      return;
    }

    setIsProcessing(true);
    try {
      // 1. Tạo Master Key từ PIN của User
      const masterKey = await deriveKeyFromPin(pin, "smartdoc_secure_salt");

      // 2. Gói (Wrap) chìa khóa này lại và lưu vào LocalStorage
      // Sử dụng deviceSecret (lấy từ JWT) làm lớp vỏ bảo vệ
      await saveKeyToStorage(masterKey, deviceSecret);

      // 3. Thông báo cho App là chìa khóa đã sẵn sàng trong RAM
      onKeyReady(masterKey);
    } catch (error) {
      console.error("Lỗi thiết lập bảo mật:", error);
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

        <h2 className="text-2xl font-bold text-white mb-2">Thiết lập Mã PIN</h2>
        <p className="text-gray-400 text-sm mb-8">
          Mã PIN này dùng để mã hóa tin nhắn của bạn. <br />
          <span className="text-orange-400/80 text-xs font-medium">
            ⚠️ Admin không thể khôi phục nếu bạn quên mã này.
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
              className="w-full py-4 pl-12 pr-4 bg-white/5 border border-white/10 rounded-xl text-white text-lg tracking-[0.5em] focus:ring-2 focus:ring-blue-500 outline-none transition-all"
              disabled={isProcessing}
            />
          </div>

          <button
            type="submit"
            disabled={isProcessing || pin.length < 4}
            className="w-full py-4 bg-white text-black font-bold rounded-xl flex items-center justify-center gap-2 hover:bg-gray-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isProcessing ? "Đang thiết lập két sắt..." : "Kích hoạt bảo mật"}
            {!isProcessing && <ArrowRight size={18} />}
          </button>
        </form>
      </motion.div>
    </div>
  );
};

export default PinModal;
