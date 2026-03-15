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

// Thêm tham số userId vào hàm
export async function saveKeyToStorage(masterKey: CryptoKey, deviceSecret: string, userId: string) {
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

  // LƯU RIÊNG THEO USER ID
  localStorage.setItem(`wrapped_key_${userId}`, btoa(String.fromCharCode(...new Uint8Array(wrapped))));
  localStorage.setItem(`key_iv_${userId}`, btoa(String.fromCharCode(...iv)));
}

// 3. Mở gói chìa khóa (Unwrap)
export async function unwrapKey(wrappedKeyBase64: string, ivBase64: string, deviceSecret: string) {
  const encoder = new TextEncoder();
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

// 4. Mã hóa tin nhắn: Gộp IV vào chung chuỗi để lưu vào DB dễ dàng hơn
export async function encryptMessage(text: string, key: CryptoKey) {
  const encoder = new TextEncoder();
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await window.crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, key, encoder.encode(text)
  );

  // Đóng gói IV và Cipher thành một JSON Base64 để lưu vào 1 cột duy nhất trong DB
  const packet = {
    iv: Array.from(iv),
    cipher: Array.from(new Uint8Array(encrypted))
  };
  return {
    cipher: btoa(JSON.stringify(packet))
  };
}

// 5. GIẢI MÃ TIN NHẮN (Hàm bạn đang thiếu)
export async function decryptMessage(ciphertextBase64: string, key: CryptoKey) {
  try {
    // Giải mã gói JSON
    const packet = JSON.parse(atob(ciphertextBase64));
    const iv = new Uint8Array(packet.iv);
    const encryptedData = new Uint8Array(packet.cipher);

    const decrypted = await window.crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      encryptedData
    );

    return new TextDecoder().decode(decrypted);
  } catch (e) {
    console.error("Lỗi giải mã:", e);
    return "[Lỗi: Không thể giải mã tin nhắn này]";
  }
}