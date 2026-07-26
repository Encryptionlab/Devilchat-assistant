'use client';

import { useChat } from '@/hooks/useChat';
import MobileShell from '@/components/layout/MobileShell';
import TabBar from '@/components/layout/TabBar';
import ChatInput from '@/components/chat/ChatInput';
import AnalysisCard from '@/components/chat/AnalysisCard';
import ReplySuggestion from '@/components/chat/ReplySuggestion';
import ConversationContext from '@/components/chat/ConversationContext';

export default function ChatPage() {
  const {
    isLoading,
    analysis,
    reply,
    enhancedReply,
    history,
    error,
    sendMessage,
    needLabels,
    emotionLabels,
  } = useChat();

  const hasResult = !!reply || !!enhancedReply || isLoading;

  return (
    <>
      <MobileShell>
        <div className="flex flex-col h-full">
          <ChatInput onSubmit={sendMessage} disabled={isLoading} />

          <div className="flex-1 overflow-y-auto">
            {!hasResult && !error && (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                把她的消息粘贴上来，让 AI 帮你分析和回复
              </div>
            )}

            {error && (
              <div className="mx-3 mt-3 px-3 py-2 bg-red-50 text-red-600 text-xs rounded-lg">
                {error}
              </div>
            )}

            {analysis && (
              <AnalysisCard
                emotion={analysis.emotion}
                topic={analysis.topic}
                dominantNeed={analysis.dominantNeed}
                goal={analysis.goal}
                goalZh={analysis.goalZh}
                strategy={analysis.strategy}
                needLabels={needLabels}
                emotionLabels={emotionLabels}
              />
            )}

            <ReplySuggestion
              reply={reply}
              enhancedReply={enhancedReply}
              isStreaming={isLoading}
            />

            {hasResult && (
              <div className="px-3 py-2 text-xs text-gray-400 text-center">
                分析结果仅供参考，请根据实际情况判断
              </div>
            )}

            <ConversationContext history={history} />
          </div>
        </div>
      </MobileShell>
      <TabBar />
    </>
  );
}
