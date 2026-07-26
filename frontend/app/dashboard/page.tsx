'use client';

import { useDashboard } from '@/hooks/useDashboard';
import MobileShell from '@/components/layout/MobileShell';
import TabBar from '@/components/layout/TabBar';
import UrgencyBadge from '@/components/dashboard/UrgencyBadge';
import PendingMessageList from '@/components/dashboard/PendingMessageList';
import EffectivenessPanel from '@/components/dashboard/EffectivenessPanel';
import AnalysisCard from '@/components/chat/AnalysisCard';
import ReplySuggestion from '@/components/chat/ReplySuggestion';
import ConversationContext from '@/components/chat/ConversationContext';

export default function DashboardPage() {
  const { data, loading, analyzeLoading, lastAnalysis, analyze } = useDashboard();

  const needLabels: Record<string, string> = {
    UNDERSTANDING: '被理解',
    ATTENTION: '被关注',
    VALIDATION: '被认可',
    COMPANIONSHIP: '陪伴',
    PARTICIPATION: '参与感',
    SECURITY: '安全感',
    COMFORT: '安慰',
  };

  const emotionLabels: Record<string, string> = {
    happy: '开心', sad: '难过', angry: '生气', anxious: '焦虑',
    tired: '疲惫', disappointed: '失望', neutral: '中性', excited: '兴奋',
    worried: '担心', confused: '困惑',
  };

  const hasAnalysis = lastAnalysis && (lastAnalysis.reply || lastAnalysis.enhanced_reply);

  return (
    <>
      <MobileShell dashboardMode>
        <div className="flex flex-col h-full">
          {/* Status bar */}
          <div className="px-3 py-2 bg-wechat-dark text-white text-[10px] flex items-center justify-between">
            <span className="inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
              监听中
            </span>
            {data?.stats && (
              <span>
                缓冲 {data.stats.total_buffered} · 未读 {data.stats.pending_count}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-sm text-gray-400 text-center">加载中…</div>
            ) : (
              <>
                {/* Urgency */}
                {data?.urgency && (
                  <UrgencyBadge
                    level={data.urgency.level}
                    label={data.urgency.label}
                    reasons={data.urgency.reasons}
                    score={data.urgency.score}
                  />
                )}

                {/* Pending messages + analyze button */}
                <PendingMessageList
                  messages={data?.pending_messages || []}
                  emotion={data?.emotion || ''}
                  topic={data?.topic || ''}
                  onAnalyze={analyze}
                  loading={analyzeLoading}
                />

                {/* Analysis results */}
                {hasAnalysis && (
                  <>
                    {lastAnalysis && (
                      <AnalysisCard
                        emotion={(lastAnalysis.debug as Record<string, unknown>)?.emotion as string || ''}
                        topic=""
                        dominantNeed={(lastAnalysis.debug as Record<string, unknown>)?.dominant_need as string || ''}
                        goal={lastAnalysis.goal as string || ''}
                        goalZh={lastAnalysis.goal_zh as string || ''}
                        strategy={lastAnalysis.strategy_name as string || ''}
                        needLabels={needLabels}
                        emotionLabels={emotionLabels}
                      />
                    )}
                    <ReplySuggestion
                      reply={(lastAnalysis?.reply as string) || ''}
                      enhancedReply={(lastAnalysis?.enhanced_reply as string) || ''}
                      isStreaming={false}
                    />
                  </>
                )}

                {/* Strategy effectiveness */}
                {data?.strategy_effectiveness && (
                  <EffectivenessPanel
                    effectiveness={data.strategy_effectiveness as Record<string, {
                      total_uses: number; successes: number; partials: number;
                      failures: number; success_rate: number; last_used: string;
                    }>}
                  />
                )}

                {/* Active conversation info */}
                {data?.active_conversation && (
                  <div className="px-3 py-2 border-t border-gray-100 text-[10px] text-gray-400">
                    当前话题: {data.active_conversation.topic as string}
                    {data?.emotion && ` · 情绪: ${data.emotion}`}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </MobileShell>
      <TabBar dashboard />
    </>
  );
}
