"use client";

import { useRef, useEffect } from "react";

export default function ChatInput({ value, onChange, onSubmit, loading }) {
  const ref = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.height = "auto";
    ref.current.style.height = Math.min(ref.current.scrollHeight, 200) + "px";
  }, [value]);

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!loading && value.trim()) onSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-chat px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="relative flex items-end gap-3 rounded-xl border border-border bg-input px-4 py-3 focus-within:border-[#565869]">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            disabled={loading}
            placeholder="Ask anything about your documents…"
            className="flex-1 resize-none bg-transparent text-sm text-[#ececf1] placeholder-[#565869] outline-none leading-6 max-h-48 overflow-y-auto disabled:opacity-60"
          />
          <button
            onClick={onSubmit}
            disabled={loading || !value.trim()}
            className="mb-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-accent text-white transition hover:bg-[#0d8a6c] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? <SpinIcon /> : <SendIcon />}
          </button>
        </div>
        <p className="mt-2 text-center text-xs text-[#565869]">
          Answers are based on indexed army documents. Press Shift+Enter for a new line.
        </p>
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function SpinIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
