'use client';

import { useState, useEffect, useCallback } from 'react';

interface DashboardData {
  urgency: {
    level: string;
    score: number;
    reasons: string[];
    label: string;
  };
  pending_messages: Array<{
    id: string;
    role: string;
    content: string;
    timestamp: string;
    is_emoji?: boolean;
    is_image?: boolean;
    emoji_desc?: string;
  }>;
  stats: {
    pending_count: number;
    time_since_her: number;
    time_since_me: number;
    total_buffered: number;
  };
  emotion: string;
  topic: string;
  active_conversation: Record<string, unknown> | null;
  strategy_effectiveness: Record<string, unknown>;
  had_closed: boolean;
  closed_conv: Record<string, unknown> | null;
  evaluation: Record<string, unknown> | null;
}

export function useDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [lastAnalysis, setLastAnalysis] = useState<Record<string, unknown> | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard');
      if (res.ok) {
        const d = await res.json();
        setData(d);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    // Poll every 10 seconds for new messages
    const interval = setInterval(fetchDashboard, 10000);
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  const analyze = useCallback(async () => {
    if (!data?.pending_messages?.length) return;
    setAnalyzeLoading(true);
    try {
      const pending = data.pending_messages;
      const combined = pending.map((m) => m.content).join('\n');

      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: combined,
          chat_history: [],
        }),
      });

      if (!res.ok) throw new Error('Analysis failed');

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No body');

      const decoder = new TextDecoder();
      let buffer = '';
      let result: Record<string, unknown> = {};

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        let eventType = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ') && eventType === 'done') {
            try {
              result = JSON.parse(line.slice(6));
            } catch { /* skip */ }
          }
        }
      }

      setLastAnalysis(result);
      // Mark as processed
      await fetch('/api/dashboard/mark-processed', { method: 'POST' });
      await fetchDashboard();
    } catch {
      // silent
    } finally {
      setAnalyzeLoading(false);
    }
  }, [data, fetchDashboard]);

  return {
    data,
    loading,
    analyzeLoading,
    lastAnalysis,
    analyze,
    refresh: fetchDashboard,
  };
}
