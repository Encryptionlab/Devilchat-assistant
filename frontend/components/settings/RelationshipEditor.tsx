'use client';

import { useState } from 'react';
import type { RelationshipState } from '@/lib/types';

interface RelationshipEditorProps {
  state: RelationshipState;
  onUpdate: (data: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
}

const stages = [
  { value: 'stranger', label: '陌生人' },
  { value: 'acquaintance', label: '刚认识' },
  { value: 'friend', label: '普通朋友' },
  { value: 'ambiguous', label: '暧昧' },
  { value: 'dating', label: '恋爱中' },
  { value: 'stable', label: '长期稳定' },
];

const temperatures = [
  { value: 'hot', label: '火热' },
  { value: 'warm', label: '温暖' },
  { value: 'neutral', label: '中性' },
  { value: 'cold', label: '冷淡' },
];

export default function RelationshipEditor({ state, onUpdate, loading }: RelationshipEditorProps) {
  const [stage, setStage] = useState(state.stage);
  const [temp, setTemp] = useState(state.temperature);
  const [trust, setTrust] = useState(state.trust_level);
  const [intimacy, setIntimacy] = useState(state.intimacy_level);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdate({ stage, temperature: temp, trust_level: trust, intimacy_level: intimacy });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-4 space-y-5">
      <h2 className="text-lg font-medium text-gray-800">关系状态</h2>

      <div>
        <label className="text-sm text-gray-500 mb-1 block">关系阶段</label>
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value)}
          disabled={loading}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none focus:border-green-400"
        >
          {stages.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-sm text-gray-500 mb-1 block">关系热度</label>
        <select
          value={temp}
          onChange={(e) => setTemp(e.target.value)}
          disabled={loading}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg outline-none focus:border-green-400"
        >
          {temperatures.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-sm text-gray-500 mb-1 block">
          信任程度: <span className="font-medium text-gray-700">{trust}</span>
        </label>
        <input
          type="range"
          min={0}
          max={100}
          value={trust}
          onChange={(e) => setTrust(Number(e.target.value))}
          disabled={loading}
          className="w-full accent-green-500"
        />
      </div>

      <div>
        <label className="text-sm text-gray-500 mb-1 block">
          亲密程度: <span className="font-medium text-gray-700">{intimacy}</span>
        </label>
        <input
          type="range"
          min={0}
          max={100}
          value={intimacy}
          onChange={(e) => setIntimacy(Number(e.target.value))}
          disabled={loading}
          className="w-full accent-green-500"
        />
      </div>

      <button
        onClick={handleSave}
        disabled={saving || loading}
        className="w-full py-2.5 bg-green-500 text-white rounded-lg font-medium
          hover:bg-green-600 disabled:bg-gray-300 active:scale-[0.98] transition"
      >
        {saving ? '保存中...' : '保存'}
      </button>

      {state.conflict_level > 0 && (
        <div className="text-sm text-gray-500">
          <p>冲突等级: {state.conflict_level}/5</p>
          {state.unresolved_topics.length > 0 && (
            <p className="text-red-500 mt-1">
              未解决: {state.unresolved_topics.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
