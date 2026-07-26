'use client';

import { useState, useEffect, useCallback } from 'react';
import { getConversations } from '@/lib/api';

export function useConversations() {
  const [data, setData] = useState<{
    active: Record<string, unknown> | null;
    closed: Record<string, unknown>[];
  }>({ active: null, closed: [] });
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getConversations();
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { ...data, loading, refresh: fetch };
}
