const encoder = new TextEncoder();
const decoder = new TextDecoder();

function bytesToBase64Url(bytes) {
  let binary = '';
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (let index = 0; index < view.length; index += 1) binary += String.fromCharCode(view[index]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlToBytes(value) {
  const normalized = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4 || 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function hmacKey(secret, usages) {
  if (!secret || String(secret).length < 32) throw new Error('TOKEN_SIGNING_SECRET must contain at least 32 characters');
  return crypto.subtle.importKey(
    'raw', encoder.encode(String(secret)), { name: 'HMAC', hash: 'SHA-256' }, false, usages,
  );
}

export function validInstallationId(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ''));
}

export async function issueInstallationToken(secret, installationId, nowMs, ttlSeconds) {
  if (!validInstallationId(installationId)) throw new Error('invalid installation id');
  const issuedAt = Math.floor(Number(nowMs) / 1000);
  const payload = {
    v: 1,
    sid: installationId,
    iat: issuedAt,
    exp: issuedAt + Math.max(3600, Number(ttlSeconds) || 0),
  };
  const encoded = bytesToBase64Url(encoder.encode(JSON.stringify(payload)));
  const signature = await crypto.subtle.sign('HMAC', await hmacKey(secret, ['sign']), encoder.encode(encoded));
  return `${encoded}.${bytesToBase64Url(signature)}`;
}

export async function verifyInstallationToken(secret, token, nowMs) {
  const parts = String(token || '').split('.');
  if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error('invalid token');
  let payload;
  try {
    payload = JSON.parse(decoder.decode(base64UrlToBytes(parts[0])));
  } catch (_) {
    throw new Error('invalid token');
  }
  const valid = await crypto.subtle.verify(
    'HMAC', await hmacKey(secret, ['verify']), base64UrlToBytes(parts[1]), encoder.encode(parts[0]),
  );
  if (!valid || payload.v !== 1 || !validInstallationId(payload.sid)) throw new Error('invalid token');
  const nowSeconds = Math.floor(Number(nowMs) / 1000);
  if (!Number.isFinite(payload.exp) || payload.exp <= nowSeconds) throw new Error('expired token');
  if (!Number.isFinite(payload.iat) || payload.iat > nowSeconds + 300) throw new Error('invalid token');
  return payload;
}

export async function hashIdentifier(secret, value) {
  const key = await hmacKey(secret, ['sign']);
  const digest = new Uint8Array(await crypto.subtle.sign('HMAC', key, encoder.encode(String(value || 'unknown'))));
  return Array.from(digest.slice(0, 16), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
