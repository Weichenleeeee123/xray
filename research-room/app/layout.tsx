import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://xiaoqi-kline-run.fanmeilin164.chatgpt.site'),
  title: '小企研究室 · 企er',
  description: '看小企穿梭于企业档案、新闻与数据终端，收集证据并生成企业研究报告。',
  openGraph: {
    title: '小企研究室 · 企er',
    description: '30 秒，看见一份企业研究报告如何生成。',
    images: [{ url: '/og.png', width: 1672, height: 941, alt: '小企在像素研究室收集企业资料' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: '小企研究室 · 企er',
    description: '30 秒，看见一份企业研究报告如何生成。',
    images: ['/og.png'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
