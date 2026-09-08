import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'香港科技大学清水湾 · 三维校园地图',description:'基于政府地形、三维几何和 HKUST 官方资料的本地校园浏览与认路工具。'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}
