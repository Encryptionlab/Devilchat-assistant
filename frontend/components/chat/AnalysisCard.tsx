'use client';

interface AnalysisCardProps {
  emotion: string;
  topic: string;
  dominantNeed: string;
  goal: string;
  goalZh: string;
  strategy: string;
  needLabels: Record<string, string>;
  emotionLabels: Record<string, string>;
}

const goalLabels: Record<string, string> = {
  EXPRESS_MORE: '引导表达',
  REDUCE_NEGATIVE: '缓解负面',
  BUILD_SECURITY: '建立安全感',
  INCREASE_PARTICIPATION: '带动参与',
  AMPLIFY_POSITIVE: '放大积极',
  INCREASE_INTIMACY: '推进亲密',
  REPAIR_CONNECTION: '修复连接',
  DEESCALATE_CONFLICT: '化解冲突',
};

const topicLabels: Record<string, string> = {
  daily: '日常闲聊',
  exam: '备考',
  relationship: '感情关系',
  work: '工作',
  family: '家庭',
  dating: '约会',
  conflict: '冲突',
  entertainment: '娱乐',
};

export default function AnalysisCard({
  emotion,
  topic,
  dominantNeed,
  goal,
  goalZh,
  strategy,
  needLabels,
  emotionLabels,
}: AnalysisCardProps) {
  if (!emotion && !dominantNeed && !strategy) return null;

  return (
    <div className="px-3 py-3 border-b border-gray-100">
      <h3 className="text-xs font-medium text-gray-500 mb-2">📊 分析结果</h3>
      <div className="grid grid-cols-2 gap-2">
        {emotion && (
          <div className="bg-purple-50 rounded-lg px-3 py-2">
            <div className="text-[10px] text-purple-500">情绪</div>
            <div className="text-sm font-medium text-purple-700">
              {emotionLabels[emotion] || emotion}
            </div>
          </div>
        )}
        {topic && (
          <div className="bg-blue-50 rounded-lg px-3 py-2">
            <div className="text-[10px] text-blue-500">话题</div>
            <div className="text-sm font-medium text-blue-700">
              {topicLabels[topic] || topic}
            </div>
          </div>
        )}
        {dominantNeed && (
          <div className="bg-amber-50 rounded-lg px-3 py-2">
            <div className="text-[10px] text-amber-500">核心需求</div>
            <div className="text-sm font-medium text-amber-700">
              {needLabels[dominantNeed] || dominantNeed}
            </div>
          </div>
        )}
        {(goalZh || goal) && (
          <div className="bg-green-50 rounded-lg px-3 py-2">
            <div className="text-[10px] text-green-500">目标</div>
            <div className="text-sm font-medium text-green-700">
              {goalZh || goalLabels[goal] || goal}
            </div>
          </div>
        )}
      </div>
      {strategy && (
        <div className="mt-2 bg-gray-50 rounded-lg px-3 py-2">
          <div className="text-[10px] text-gray-500">策略</div>
          <div className="text-xs text-gray-600">{strategy}</div>
        </div>
      )}
    </div>
  );
}
