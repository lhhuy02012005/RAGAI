const ITERATIONS = 600000;

// 1. Tạo Master Key từ PIN của User
export async function deriveKeyFromPin(pin: string, salt: string) {
  const encoder = new TextEncoder();
  const baseKey = await window.crypto.subtle.importKey(
    "raw", encoder.encode(pin), "PBKDF2", false, ["deriveKey"]
  );

  return await window.crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: encoder.encode(salt), iterations: ITERATIONS, hash: "SHA-256" },
    baseKey,
    { name: "AES-GCM", length: 256 },
    true, ["encrypt", "decrypt", "wrapKey", "unwrapKey"]
  );
}

// 2. Gói chìa khóa (Wrap) để lưu vào localStorage
export async function saveKeyToStorage(masterKey: CryptoKey, deviceSecret: string) {
  const encoder = new TextEncoder();
  const wrappingKey = await window.crypto.subtle.importKey(
    "raw", 
    encoder.encode(deviceSecret.padEnd(32, '0')), 
    "AES-GCM", 
    false, 
    ["wrapKey"]
  );

  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const wrapped = await window.crypto.subtle.wrapKey(
    "raw",
    masterKey,
    wrappingKey,
    { name: "AES-GCM", iv }
  );

  localStorage.setItem("wrapped_key", btoa(String.fromCharCode(...new Uint8Array(wrapped))));
  localStorage.setItem("key_iv", btoa(String.fromCharCode(...iv)));
}

// 3. Mở gói chìa khóa (Unwrap) - ĐÂY LÀ HÀM BẠN ĐANG THIẾU
export async function unwrapKey(wrappedKeyBase64: string, ivBase64: string, deviceSecret: string) {
  const encoder = new TextEncoder();
  
  // Chuyển đổi từ Base64 ngược lại dạng Buffer
  const wrappedKeyBuffer = Uint8Array.from(atob(wrappedKeyBase64), c => c.charCodeAt(0));
  const iv = Uint8Array.from(atob(ivBase64), c => c.charCodeAt(0));

  const wrappingKey = await window.crypto.subtle.importKey(
    "raw", 
    encoder.encode(deviceSecret.padEnd(32, '0')), 
    "AES-GCM", 
    false, 
    ["unwrapKey"]
  );

  return await window.crypto.subtle.unwrapKey(
    "raw",
    wrappedKeyBuffer,
    wrappingKey,
    { name: "AES-GCM", iv },
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"]
  );
}

// 4. Mã hóa tin nhắn trước khi gửi
export async function encryptMessage(text: string, key: CryptoKey) {
  const encoder = new TextEncoder();
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await window.crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, key, encoder.encode(text)
  );
  return {
    cipher: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
    iv: btoa(String.fromCharCode(...iv))
  };
}