'use client';

import { useState } from 'react';

interface ReplySuggestionProps {
  reply: string;
  enhancedReply: string;
  isStreaming: boolean;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="ml-2 shrink-0 px-2 py-1 text-[10px] rounded-full
        bg-gray-100 text-gray-500 hover:bg-green-100 hover:text-green-600
        active:scale-95 transition"
    >
      {copied ? '✓ 已复制' : '📋 复制'}
    </button>
  );
}

export default function ReplySuggestion({
  reply,
  enhancedReply,
  isStreaming,
}: ReplySuggestionProps) {
  if (!reply && !enhancedReply && !isStreaming) return null;

  return (
    <div className="px-3 py-3 border-b border-gray-100">
      {reply && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-medium text-gray-500">💬 建议回复</h3>
            <CopyButton text={reply} />
          </div>
          <div className="bg-gray-50 rounded-lg px-3 py-2.5 text-sm leading-relaxed text-gray-800">
            {reply}
            {isStreaming && !enhancedReply && (
              <span className="inline-block w-1 h-4 bg-green-500 ml-0.5 animate-pulse align-middle" />
            )}
          </div>
        </div>
      )}
      {enhancedReply && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-xs font-medium text-gray-500">✨ 润色版</h3>
            <CopyButton text={enhancedReply} />
          </div>
          <div className="bg-green-50 rounded-lg px-3 py-2.5 text-sm leading-relaxed text-gray-800">
            {enhancedReply}
            {isStreaming && (
              <span className="inline-block w-1 h-4 bg-green-500 ml-0.5 animate-pulse align-middle" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
