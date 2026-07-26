'use client';

interface PendingMessage {
  id: string;
  role: string;
  content: string;
  timestamp: string;
  is_emoji?: boolean;
  is_image?: boolean;
  emoji_desc?: string;
}

interface PendingMessageListProps {
  messages: PendingMessage[];
  emotion: string;
  topic: string;
  onAnalyze: () => void;
  loading: boolean;
}

function timeAgo(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return '刚刚';
    if (min < 60) return `${min}分钟前`;
    const hrs = Math.floor(min / 60);
    if (hrs < 24) return `${hrs}小时前`;
    return `${Math.floor(hrs / 24)}天前`;
  } catch {
    return '';
  }
}

export default function PendingMessageList({
  messages,
  emotion,
  topic,
  onAnalyze,
  loading,
}: PendingMessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-400 text-sm">
        暂无待处理消息
      </div>
    );
  }

  return (
    <div className="px-3 py-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-gray-500">
          📥 待处理消息 ({messages.length})
        </h3>
        {emotion && (
          <span className="text-[10px] px-2 py-0.5 bg-purple-50 text-purple-600 rounded-full">
            {emotion}
          </span>
        )}
      </div>

      <div className="space-y-1.5 mb-3">
        {messages.map((msg) => (
          <div key={msg.id} className="flex gap-2 text-xs leading-relaxed">
            <span className="text-gray-400 shrink-0 w-12 text-right">
              {timeAgo(msg.timestamp)}
            </span>
            <span className="text-gray-700">
              {msg.is_emoji ? `[表情: ${msg.emoji_desc || '未知'}]` : msg.content}
            </span>
          </div>
        ))}
      </div>

      <button
        onClick={onAnalyze}
        disabled={loading}
        className="w-full py-2 rounded-lg text-sm font-medium text-white
          bg-green-500 hover:bg-green-600 disabled:bg-gray-300
          active:scale-[0.98] transition"
      >
        {loading ? (
          <span className="inline-flex items-center gap-2">
            <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            分析中…
          </span>
        ) : (
          '🔍 分析并生成回复建议'
        )}
      </button>
    </div>
  );
}
