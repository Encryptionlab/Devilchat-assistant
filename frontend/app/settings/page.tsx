'use client';

import { useState } from 'react';
import { useRelationship } from '@/hooks/useRelationship';
import { bootstrap } from '@/lib/api';
import MobileShell from '@/components/layout/MobileShell';
import TabBar from '@/components/layout/TabBar';
import BootstrapForm from '@/components/settings/BootstrapForm';
import RelationshipEditor from '@/components/settings/RelationshipEditor';

export default function SettingsPage() {
  const { state, loading, refresh, update } = useRelationship();
  const [bootstrapLoading, setBootstrapLoading] = useState(false);

  const handleBootstrap = async (description: string) => {
    setBootstrapLoading(true);
    try {
      await bootstrap(description);
      await refresh();
    } finally {
      setBootstrapLoading(false);
    }
  };

  const needsBootstrap = !loading && (!state || !state.stage);

  return (
    <>
      <MobileShell>
        <div className="h-full overflow-y-auto">
          {loading ? (
            <div className="p-4 text-sm text-gray-400">加载中...</div>
          ) : needsBootstrap ? (
            <BootstrapForm onSubmit={handleBootstrap} loading={bootstrapLoading} />
          ) : (
            <>
              <RelationshipEditor
                state={state!}
                onUpdate={update}
                loading={loading}
              />
              <div className="px-4 pb-8">
                <button
                  onClick={() => { /* reset to bootstrap */ }}
                  className="w-full py-2 text-sm text-gray-400 underline"
                >
                  重新初始化关系档案
                </button>
              </div>
            </>
          )}
        </div>
      </MobileShell>
      <TabBar />
    </>
  );
}
