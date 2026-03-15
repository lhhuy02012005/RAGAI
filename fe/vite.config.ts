import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 1. Cho phép tất cả các host để không bị lỗi "Blocked Host" khi link Tunnel thay đổi mỗi ngày
    allowedHosts: true, 
    
    // 2. Ép Vite lắng nghe trên tất cả các địa chỉ mạng (0.0.0.0) 
    // thay vì chỉ localhost, giúp Cloudflare "nhìn thấy" ứng dụng của bạn
    host: true, 
    
    // 3. Cố định cổng 5173
    port: 5173,

    // 4. Cấu hình HMR (Hot Module Replacement) qua Tunnel nếu cần
    hmr: {
      clientPort: 443, // Cloudflare luôn chạy cổng 443 (HTTPS)
    }
  }
})