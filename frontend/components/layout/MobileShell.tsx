'use client';

import { usePathname } from 'next/navigation';

const titles: Record<string, string> = {
  '/dashboard': '魔鬼聊天',
  '/chat': '消息分析',
  '/history': '对话记忆',
  '/settings': '关系设置',
};

export default function MobileShell({ children, dashboardMode }: { children: React.ReactNode; dashboardMode?: boolean }) {
  const pathname = usePathname();
  const base = '/' + (pathname.split('/')[1] || (dashboardMode ? 'dashboard' : 'chat'));
  const title = titles[base] || '魔鬼聊天';

  return (
    <>
      <header className="h-12 flex items-center justify-center bg-wechat-dark text-white flex-shrink-0">
        <h1 className="text-base font-medium">{title}</h1>
      </header>
      <main className="flex-1 overflow-hidden">{children}</main>
    </>
  );
}
