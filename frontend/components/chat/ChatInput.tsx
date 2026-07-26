'use client';

import { useState, useRef, useEffect } from 'react';

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="px-3 py-3 border-b border-gray-100 bg-white">
      <label className="text-xs font-medium text-gray-500 mb-1.5 block">
        📥 她说了什么？
      </label>
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="粘贴她发来的消息…"
        rows={3}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 outline-none
          resize-none focus:border-green-400 disabled:bg-gray-50 disabled:text-gray-400
          placeholder-gray-400"
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !text.trim()}
        className="mt-2 w-full py-2 rounded-lg text-sm font-medium text-white
          bg-green-500 hover:bg-green-600 disabled:bg-gray-300
          active:scale-[0.98] transition"
      >
        {disabled ? (
          <span className="inline-flex items-center gap-2">
            <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            分析中…
          </span>
        ) : (
          '🔍 分析并生成回复'
        )}
      </button>
    </div>
  );
}
