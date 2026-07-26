'use client';

import { useState } from 'react';

interface BootstrapFormProps {
  onSubmit: (description: string) => Promise<void>;
  loading?: boolean;
}

export default function BootstrapForm({ onSubmit, loading }: BootstrapFormProps) {
  const [text, setText] = useState('');

  const handleSubmit = async () => {
    if (!text.trim() || loading) return;
    await onSubmit(text.trim());
  };

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-lg font-medium text-gray-800">欢迎使用魔鬼聊天</h2>
      <p className="text-sm text-gray-500 leading-relaxed">
        在开始之前，先简单说说你们现在的关系吧。比如认识多久了、怎么认识的、
        现在是什么关系阶段、最近有什么重要的事情发生。
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="我们认识三个月了，是大学同学，最近在一起复习考研..."
        rows={5}
        disabled={loading}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none
          focus:border-green-400 resize-none disabled:bg-gray-50"
      />
      <button
        onClick={handleSubmit}
        disabled={loading || !text.trim()}
        className="w-full py-2.5 bg-green-500 text-white rounded-lg font-medium
          hover:bg-green-600 disabled:bg-gray-300 active:scale-[0.98] transition"
      >
        {loading ? '分析中...' : '开始'}
      </button>
    </div>
  );
}
