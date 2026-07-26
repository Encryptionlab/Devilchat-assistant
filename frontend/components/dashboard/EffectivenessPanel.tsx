'use client';

interface StrategyEffectiveness {
  total_uses: number;
  successes: number;
  partials: number;
  failures: number;
  success_rate: number;
  last_used: string;
}

interface EffectivenessPanelProps {
  effectiveness: Record<string, StrategyEffectiveness>;
}

export default function EffectivenessPanel({ effectiveness }: EffectivenessPanelProps) {
  const entries = Object.entries(effectiveness || {});
  if (entries.length === 0) return null;

  const sorted = entries.sort(
    (a, b) => (b[1].success_rate || 0) - (a[1].success_rate || 0)
  );

  return (
    <div className="px-3 py-3 border-t border-gray-100">
      <h3 className="text-xs font-medium text-gray-500 mb-2">📈 策略效果</h3>
      <div className="space-y-1.5">
        {sorted.map(([name, entry]) => {
          const rate = Math.round((entry.success_rate || 0) * 100);
          return (
            <div key={name} className="flex items-center gap-2 text-xs">
              <span className="w-16 text-gray-600 truncate">{name}</span>
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all"
                  style={{ width: `${rate}%` }}
                />
              </div>
              <span className="w-10 text-right text-gray-400">
                {rate}% ({entry.total_uses})
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
