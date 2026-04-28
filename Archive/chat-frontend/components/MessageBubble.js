"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { downloadDoc } from "../lib/api";

// Strip UUID prefix from stored filename: "b9c660ac-..._Network.pdf" → "Network.pdf"
function displayName(raw) {
  return raw.replace(/^[0-9a-f]{8}-[0-9a-f-]{27}_/i, "");
}

// Format score as relevance percentage (scores can exceed 1.0 in hybrid BM25+KNN)
function relevancePct(score) {
  return Math.round(score * 100);
}

// ── Source cards ──────────────────────────────────────────────────────────────

function SourceCard({ s, index }) {
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError] = useState("");

  async function handleDownload() {
    setDownloading(true);
    setDlError("");
    try {
      await downloadDoc(s.doc_id, displayName(s.file_name));
    } catch (e) {
      if (e.message === "NOT_LOGGED_IN" || e.message === "SESSION_EXPIRED") {
        setDlError("Session expired — please sign in again.");
        setTimeout(() => { window.location.href = "/login"; }, 1500);
      } else if (e.message === "ACCESS_DENIED") {
        setDlError("You don't have permission to download this file.");
      } else {
        setDlError(`Download failed: ${e.message}`);
      }
    } finally {
      setDownloading(false);
    }
  }

  const pct = relevancePct(s.score);

  return (
    <>
      <div className="flex items-start gap-3 rounded-xl border border-border bg-[#3a3b47] px-4 py-3 hover:border-[#565869] transition">
        {/* Index badge */}
        <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[#565869] text-[10px] font-semibold text-[#ececf1]">
          {index}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[#ececf1] truncate leading-5">
            {displayName(s.file_name)}
          </p>
          <p className="mt-0.5 text-xs text-[#8e8ea0]">
            p.{s.page_number}
            {s.section ? ` · ${s.section}` : ""}
            {s.doc_type ? ` · ${s.doc_type}` : ""}
            {s.branch ? ` · ${s.branch}` : ""}
            {s.year ? ` · ${s.year}` : ""}
          </p>
          {/* Relevance bar */}
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1.5 flex-1 rounded-full bg-[#4d4d4f] overflow-hidden">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-[#8e8ea0] tabular-nums w-8 text-right">
              {pct}%
            </span>
          </div>
        </div>

        {/* Download button */}
        <button
          onClick={handleDownload}
          disabled={downloading}
          title="Download PDF"
          className="mt-0.5 flex-shrink-0 rounded-lg p-1.5 text-[#565869] hover:bg-[#4d4d4f] hover:text-[#ececf1] transition disabled:opacity-40"
        >
          {downloading ? <SpinIcon /> : <DownloadIcon />}
        </button>
      </div>

      {dlError && (
        <p className="mt-1 px-1 text-[11px] text-red-400">{dlError}</p>
      )}
    </>
  );
}

// ── Sources panel ─────────────────────────────────────────────────────────────

function SourcesPanel({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-[#8e8ea0] hover:text-[#c5c5d2] transition"
      >
        <BookIcon />
        <span>{sources.length} source{sources.length > 1 ? "s" : ""}</span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="mt-3 space-y-2">
          {sources.map((s, i) => (
            <SourceCard key={`${s.doc_id}-${s.page_number}-${i}`} s={s} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

export default function MessageBubble({ msg }) {
  const isUser = msg.role === "user";
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className={`group flex gap-4 px-4 py-5 ${isUser ? "" : "bg-[#444654]"}`}>
      {/* Avatar */}
      <div
        className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-sm text-xs font-semibold ${
          isUser ? "bg-[#5436da] text-white" : "bg-accent text-white"
        }`}
      >
        {isUser ? "U" : "AI"}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Streaming: show raw text + blinking cursor */}
        {msg.streaming ? (
          <div className="text-sm leading-7 text-[#ececf1] whitespace-pre-wrap">
            {msg.content}
            <span className="ml-0.5 inline-block h-4 w-0.5 align-middle bg-[#ececf1] animate-[blink_1s_step-end_infinite]" />
          </div>
        ) : (
          /* Done: render markdown */
          <div className="prose-chat text-sm leading-7 text-[#ececf1]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content || ""}
            </ReactMarkdown>
          </div>
        )}

        {/* Sources (only after streaming done) */}
        {!msg.streaming && !isUser && (
          <SourcesPanel sources={msg.sources} />
        )}

        {/* Copy action */}
        {!isUser && !msg.streaming && (
          <div className="mt-2 flex gap-2 opacity-0 group-hover:opacity-100 transition">
            <button
              onClick={copy}
              className="flex items-center gap-1 text-xs text-[#565869] hover:text-[#ececf1] transition"
            >
              {copied ? <CheckIcon /> : <CopyIcon />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function BookIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function ChevronIcon({ open }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function SpinIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#10a37f" strokeWidth="2">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
