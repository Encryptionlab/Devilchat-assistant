'use client';

import { useState, useEffect, useCallback } from 'react';
import { getRelationship, updateRelationship } from '@/lib/api';
import type { RelationshipState } from '@/lib/types';

export function useRelationship() {
  const [state, setState] = useState<RelationshipState | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getRelationship();
      setState(result as unknown as RelationshipState);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const update = useCallback(async (data: Record<string, unknown>) => {
    const result = await updateRelationship(data);
    setState(result as unknown as RelationshipState);
  }, []);

  return { state, loading, refresh: fetch, update };
}
