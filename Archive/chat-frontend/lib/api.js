"use client";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(t) {
  localStorage.setItem("token", t);
}

export function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export function getUser() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    return null;
  }
}

export async function login(armyNumber, password) {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ army_number: armyNumber, password }),
  });
  if (!r.ok) throw new Error("Invalid credentials");
  const data = await r.json();
  setToken(data.access_token);
  // fetch /auth/me
  const me = await fetch(`${BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${data.access_token}` },
  });
  if (me.ok) {
    const user = await me.json();
    localStorage.setItem("user", JSON.stringify(user));
  }
  return data;
}

export async function chat(query, { sessionId, topK = 5, model = "llama3:latest", filters = {} } = {}) {
  const token = getToken();
  const r = await fetch(`${BASE}/chat/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      query,
      session_id: sessionId,
      top_k: topK,
      model,
      filters,
      stream: false,
      enable_agent: true,
    }),
  });
  if (r.status === 401) throw new Error("UNAUTHORIZED");
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

// SSE streaming chat — calls /chat/stream
export function chatStream(query, { sessionId, topK = 5, model = "llama3:latest", filters = {} } = {}) {
  const token = getToken();
  // SSE via fetch (ReadableStream)
  return fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      query,
      session_id: sessionId,
      top_k: topK,
      model,
      filters,
      stream: true,
      enable_agent: false,
    }),
  });
}

export async function clearSession(sessionId) {
  const token = getToken();
  await fetch(`${BASE}/chat/session/${sessionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function downloadDoc(docId, displayName) {
  const token = getToken();
  if (!token) throw new Error("NOT_LOGGED_IN");

  const r = await fetch(`${BASE}/documents/download/${docId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (r.status === 401) throw new Error("SESSION_EXPIRED");
  if (r.status === 403) throw new Error("ACCESS_DENIED");
  if (!r.ok) throw new Error(`Download failed (${r.status})`);

  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = displayName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
