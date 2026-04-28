"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { flushSync } from "react-dom";
import { useRouter } from "next/navigation";
import { v4 as uuid } from "uuid";
import Sidebar from "../../components/Sidebar";
import MessageBubble from "../../components/MessageBubble";
import ChatInput from "../../components/ChatInput";
import { chatStream, clearSession, getToken } from "../../lib/api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function loadSessions() {
  try { return JSON.parse(localStorage.getItem("chat_sessions") || "[]"); }
  catch { return []; }
}
function saveSessions(s) { localStorage.setItem("chat_sessions", JSON.stringify(s)); }

// Strip LLM citation markers and appended References section from displayed text.
// The source cards below the message replace inline refs.
function cleanAnswer(text) {
  return text
    .replace(/\[Source \d+\]/g, "")           // [Source 1]
    .replace(/\n\n---\n\*\*References:\*\*[\s\S]*$/, "")  // References block
    .replace(/\n\n---\n⚠️[\s\S]*$/, "")        // Grounding warning (non-streaming)
    .replace(/\s{3,}/g, "  ")                  // Collapse excess whitespace
    .trim();
}

// ── Welcome screen ────────────────────────────────────────────────────────────

const PROMPTS = [
  "What is Bluetooth?",
  "Explain Star Topology",
  "What are types of computer networks?",
  "List all file commands",
  "What is CASEVAC procedure?",
];

function WelcomeScreen({ onPrompt }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-4">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent text-white text-2xl font-bold shadow-lg">
          A
        </div>
        <h1 className="text-2xl font-semibold text-[#ececf1]">Army AI Assistant</h1>
        <p className="mt-2 text-sm text-[#8e8ea0] max-w-md">
          Ask questions about your indexed army documents. Answers come directly
          from the indexed PDF library.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 w-full max-w-2xl">
        {PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => onPrompt(p)}
            className="rounded-xl border border-border bg-input px-4 py-3 text-left text-sm text-[#ececf1] hover:bg-[#4a4b5a] transition"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── SSE stream parser ─────────────────────────────────────────────────────────

async function* parseSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop(); // keep incomplete trailing line

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const raw = trimmed.slice(5).trim();
      if (!raw || raw === "[DONE]") continue;
      try { yield JSON.parse(raw); } catch { /* skip malformed */ }
    }
  }
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const router = useRouter();
  const bottomRef = useRef(null);
  const abortRef = useRef(null); // to cancel in-flight streams
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Auth guard
  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  // Load sessions from localStorage
  useEffect(() => {
    const saved = loadSessions();
    setSessions(saved);
    if (saved.length > 0) {
      setActiveId(saved[0].id);
      setMessages(saved[0].messages || []);
    }
  }, []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Session helpers ───────────────────────────────────────────────────────

  function newChat() {
    const id = uuid();
    const s = { id, title: "New conversation", messages: [] };
    const updated = [s, ...sessions];
    setSessions(updated); saveSessions(updated);
    setActiveId(id); setMessages([]); setInput("");
  }

  function selectSession(id) {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveId(id); setMessages(s.messages || []); setInput("");
  }

  async function deleteSession(id) {
    try { await clearSession(id); } catch {}
    const updated = sessions.filter((s) => s.id !== id);
    setSessions(updated); saveSessions(updated);
    if (activeId === id) {
      if (updated.length > 0) { setActiveId(updated[0].id); setMessages(updated[0].messages || []); }
      else { setActiveId(null); setMessages([]); }
    }
  }

  const persistMessages = useCallback((id, msgs) => {
    setSessions((prev) => {
      const updated = prev.map((s) => s.id === id ? { ...s, messages: msgs } : s);
      saveSessions(updated); return updated;
    });
  }, []);

  function touchTitle(id, query) {
    const title = query.length > 45 ? query.slice(0, 45) + "…" : query;
    setSessions((prev) => {
      const updated = prev.map((s) =>
        s.id === id && s.title === "New conversation" ? { ...s, title } : s
      );
      saveSessions(updated); return updated;
    });
  }

  // ── Send with SSE streaming ───────────────────────────────────────────────

  async function sendMessage(queryText) {
    const query = (queryText || input).trim();
    if (!query || loading) return;

    // Cancel any previous stream
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Ensure active session
    let sid = activeId;
    if (!sid) {
      sid = uuid();
      const ns = { id: sid, title: "New conversation", messages: [] };
      setSessions((prev) => { const u = [ns, ...prev]; saveSessions(u); return u; });
      setActiveId(sid);
    }

    const userMsg = { id: uuid(), role: "user", content: query };
    const userMessages = [...messages, userMsg];
    setMessages(userMessages);
    setInput(""); setLoading(true);

    if (messages.length === 0) touchTitle(sid, query);

    const asstId = uuid();
    // Placeholder shown while streaming
    setMessages((prev) => [
      ...prev,
      { id: asstId, role: "assistant", content: "", streaming: true, sources: [] },
    ]);

    try {
      const response = await chatStream(query, { sessionId: sid });

      if (response.status === 401) {
        router.replace("/login"); return;
      }
      if (!response.ok) throw new Error(`Server error ${response.status}`);

      let accumulated = "";
      let sources = [];

      for await (const event of parseSSE(response)) {
        if (controller.signal.aborted) break;

        if (event.type === "token") {
          accumulated += event.content;
          // flushSync forces one React render per token instead of batching,
          // giving a true character-by-character typewriter effect.
          flushSync(() => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, content: accumulated } : m
              )
            );
          });
        } else if (event.type === "sources") {
          sources = event.sources || [];
        } else if (event.type === "done" || event.type === "error") {
          break;
        }
      }

      const finalContent = cleanAnswer(accumulated);
      const asstMsg = {
        id: asstId,
        role: "assistant",
        content: finalContent,
        sources,
        streaming: false,
      };
      const finalMessages = [...userMessages, asstMsg];
      setMessages(finalMessages);
      persistMessages(sid, finalMessages);
    } catch (err) {
      if (err.name === "AbortError") return;
      const errMsg = {
        id: asstId,
        role: "assistant",
        content: `Error: ${err.message}`,
        sources: [],
        streaming: false,
      };
      const finalMessages = [...userMessages, errMsg];
      setMessages(finalMessages);
      persistMessages(sid, finalMessages);
    } finally {
      setLoading(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onNewChat={newChat}
        onSelectSession={selectSession}
        onDeleteSession={deleteSession}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <WelcomeScreen onPrompt={(p) => sendMessage(p)} />
          ) : (
            <div className="pb-6">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={() => sendMessage()}
          loading={loading}
        />
      </div>
    </div>
  );
}
