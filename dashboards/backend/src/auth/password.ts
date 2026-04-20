import { createCipheriv, createDecipheriv } from "node:crypto";

const RAW_KEY = Buffer.from("tJykDLYxZkr9Eqm9HPwCGVM", "utf-8").subarray(0, 8);

function withOddParity(key: Buffer): Buffer {
  const adjusted = Buffer.from(key);
  for (let i = 0; i < adjusted.length; i += 1) {
    let b = adjusted[i] & 0xfe;
    let ones = 0;
    for (let bit = 1; bit < 8; bit += 1) {
      if (b & (1 << bit)) ones += 1;
    }
    if (ones % 2 === 0) {
      b |= 0x01;
    }
    adjusted[i] = b;
  }
  return adjusted;
}

const DES_KEY = withOddParity(RAW_KEY);

export function encryptPassword(plainText: string): string {
  const cipher = createCipheriv("des-ecb", DES_KEY, null);
  cipher.setAutoPadding(true);
  const encrypted = Buffer.concat([cipher.update(plainText, "utf-8"), cipher.final()]);
  return encrypted.toString("base64");
}

export function decryptPassword(encryptedText: string): string {
  const decipher = createDecipheriv("des-ecb", DES_KEY, null);
  decipher.setAutoPadding(true);
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(encryptedText, "base64")),
    decipher.final(),
  ]);
  return decrypted.toString("utf-8");
}
