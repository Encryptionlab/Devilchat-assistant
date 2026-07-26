'use client';

interface UrgencyBadgeProps {
  level: string;
  label: string;
  reasons: string[];
  score: number;
}

export default function UrgencyBadge({ level, label, reasons }: UrgencyBadgeProps) {
  const colors: Record<string, string> = {
    urgent: 'bg-red-50 border-red-200 text-red-700',
    attention: 'bg-amber-50 border-amber-200 text-amber-700',
    normal: 'bg-green-50 border-green-200 text-green-700',
  };

  return (
    <div className={`mx-3 mt-3 px-3 py-2.5 rounded-lg border ${colors[level] || colors.normal}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        {reasons.length > 0 && (
          <span className="text-[10px] opacity-60">{reasons[0]}</span>
        )}
      </div>
    </div>
  );
}
