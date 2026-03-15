import React, { useState } from "react";
import Auth from "./components/Auth";
import ChatInterface from "./components/ChatInterface";
import PinModal from "./components/PinModal";
import { jwtDecode } from "jwt-decode";

const App: React.FC = () => {
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [masterKey, setMasterKey] = useState<CryptoKey | null>(null);

  // Lấy device_secret từ token JWT
  const getDeviceSecret = () => {
    if (!token) return null;
    try {
      const decoded: any = jwtDecode(token);
      return decoded.ds; // 'ds' là device_secret từ Backend
    } catch (e) {
      return null;
    }
  };

  // --- HÀM QUAN TRỌNG: Logout ---
  const handleLogout = () => {
    localStorage.clear();
    setToken(null);
    setMasterKey(null);
  };

  if (!token) return <Auth onAuthSuccess={(t) => setToken(t)} />;

  const deviceSecret = getDeviceSecret();

  // Nếu chưa có masterKey trong RAM, hiện PinModal
  if (!masterKey) {
    return (
      <PinModal
        token={token} 
        deviceSecret={deviceSecret || ""} 
        onKeyReady={(key) => setMasterKey(key)} 
      />
    );
  }

  return (
    <ChatInterface 
      token={token} 
      masterKey={masterKey} 
      onLogout={handleLogout} 
    />
  );
};

export default App;