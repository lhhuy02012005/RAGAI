import React, { useState } from 'react';

interface AuthProps {
  onAuthSuccess: (token: string, deviceSecret: string) => void;
}

const Auth: React.FC<AuthProps> = ({ onAuthSuccess }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // Lấy URL từ biến môi trường, nếu không có thì mặc định về localhost
  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const endpoint = isLogin ? "/login" : "/register";
    
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    try {
      // SỬA TẠI ĐÂY: Dùng template string với API_URL linh động
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        body: formData,
      });
      
      const data = await res.json();
      
      if (res.ok) {
        if (isLogin) {
          localStorage.setItem("token", data.access_token);
          onAuthSuccess(data.access_token, data.device_secret);
        } else {
          alert("Đăng ký thành công! Hãy đăng nhập.");
          setIsLogin(true);
        }
      } else {
        alert(data.detail || "Có lỗi xảy ra");
      }
    } catch (err) {
      console.error("Auth Error:", err);
      alert("Không thể kết nối tới máy chủ. Vui lòng kiểm tra Tunnel!");
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-[#0b0d11]">
      <div className="w-full max-w-md p-8 bg-[#17191e] rounded-2xl border border-white/10 shadow-2xl">
        <h2 className="text-2xl font-bold mb-6 text-center text-white">
          {isLogin ? "Đăng nhập SmartDoc" : "Đăng ký thành viên"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input 
            className="w-full p-3 bg-[#1e2227] rounded-lg border border-white/10 text-white outline-none focus:border-blue-500 transition-all"
            placeholder="Tên đăng nhập" 
            value={username} 
            onChange={e => setUsername(e.target.value)} 
          />
          <input 
            type="password"
            className="w-full p-3 bg-[#1e2227] rounded-lg border border-white/10 text-white outline-none focus:border-blue-500 transition-all"
            placeholder="Mật khẩu" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
          />
          <button className="w-full py-3 bg-white text-black font-bold rounded-lg hover:bg-gray-200 transition-colors">
            {isLogin ? "Vào hệ thống" : "Tạo tài khoản"}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-gray-400 cursor-pointer hover:text-white transition-colors" onClick={() => setIsLogin(!isLogin)}>
          {isLogin ? "Chưa có tài khoản? Đăng ký ngay" : "Đã có tài khoản? Đăng nhập"}
        </p>
      </div>
    </div>
  );
};

export default Auth;