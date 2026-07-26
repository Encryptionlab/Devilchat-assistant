'use client';

import { usePathname, useRouter } from 'next/navigation';

const tabs = [
  { path: '/dashboard', label: '仪表盘', icon: '📡' },
  { path: '/chat', label: '分析', icon: '💬' },
  { path: '/history', label: '记忆', icon: '📋' },
  { path: '/settings', label: '设置', icon: '⚙️' },
];

export default function TabBar({ dashboard: _d }: { dashboard?: boolean } = {}) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav className="h-14 flex items-center justify-around bg-white border-t border-gray-200 flex-shrink-0">
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.path);
        return (
          <button
            key={tab.path}
            onClick={() => router.push(tab.path)}
            className={`flex flex-col items-center justify-center w-full h-full text-xs gap-0.5
              ${active ? 'text-green-600' : 'text-gray-400'}`}
          >
            <span className="text-lg">{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
