'use client';

import { useState } from 'react';

interface HistoryEntry {
  id: string;
  role: '她' | '我';
  content: string;
}

interface ConversationContextProps {
  history: HistoryEntry[];
}

export default function ConversationContext({ history }: ConversationContextProps) {
  const [open, setOpen] = useState(false);

  if (history.length === 0) return null;

  return (
    <div className="border-t border-gray-100">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3 py-2.5 flex items-center justify-between text-xs text-gray-500
          hover:bg-gray-50 transition"
      >
        <span>📜 本轮对话 ({history.length})</span>
        <span className="text-gray-400 transition-transform duration-200"
          style={{ transform: open ? 'rotate(180deg)' : 'none' }}
        >
          ▼
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3 max-h-48 overflow-y-auto">
          {history.map((entry) => (
            <div key={entry.id} className="flex gap-2 py-1.5 text-xs leading-relaxed">
              <span className="shrink-0">
                {entry.role === '她' ? '👩 她' : '🧑 建议'}
              </span>
              <span className="text-gray-600">{entry.content}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
