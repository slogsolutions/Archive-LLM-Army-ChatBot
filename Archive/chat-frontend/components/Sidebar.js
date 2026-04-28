"use client";

import { clearToken, getUser } from "../lib/api";
import { useRouter } from "next/navigation";

export default function Sidebar({ sessions, activeId, onNewChat, onSelectSession, onDeleteSession }) {
  const router = useRouter();
  const user = getUser();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <aside className="flex h-full w-64 flex-shrink-0 flex-col bg-sidebar border-r border-border">
      {/* New Chat */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-[#ececf1] transition hover:bg-[#2a2b32]"
        >
          <PlusIcon />
          New chat
        </button>
      </div>

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {sessions.length === 0 && (
          <p className="px-2 py-2 text-xs text-[#565869]">No conversations yet</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group flex items-center rounded-lg px-3 py-2 text-sm cursor-pointer transition ${
              s.id === activeId
                ? "bg-[#2a2b32] text-[#ececf1]"
                : "text-[#c5c5d2] hover:bg-[#2a2b32]"
            }`}
            onClick={() => onSelectSession(s.id)}
          >
            <ChatIcon />
            <span className="ml-2 flex-1 truncate">{s.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
              className="hidden group-hover:flex items-center text-[#565869] hover:text-red-400 ml-1"
              title="Delete"
            >
              <TrashIcon />
            </button>
          </div>
        ))}
      </div>

      {/* Footer: user + logout */}
      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2 rounded-lg px-2 py-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-white text-sm font-semibold flex-shrink-0">
            {user?.name?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm text-[#ececf1]">{user?.name || "User"}</p>
            <p className="truncate text-xs text-[#565869] capitalize">{user?.role || ""}</p>
          </div>
          <button
            onClick={handleLogout}
            className="text-[#565869] hover:text-[#ececf1] transition"
            title="Sign out"
          >
            <LogoutIcon />
          </button>
        </div>
      </div>
    </aside>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
