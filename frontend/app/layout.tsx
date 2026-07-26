import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '魔鬼聊天',
  description: 'AI 恋爱沟通助手',
  viewport: 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no',
  themeColor: '#191919',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: '魔鬼聊天',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="h-full flex justify-center">
        <div className="w-full max-w-mobile h-full flex flex-col bg-white shadow-lg relative">
          {children}
        </div>
      </body>
    </html>
  );
}
