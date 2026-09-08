import { t, type Locale } from './i18n';
import { nameScript } from './entity-names';

const titles: Record<string, readonly [string, string, string]> = {
  'Main Hall, flat-floor mode': [
    'Main Hall, flat-floor mode',
    '主禮堂・平地模式',
    '主礼堂・平地模式',
  ],
  'Main Hall, concert mode': [
    'Main Hall, concert mode',
    '主禮堂・音樂會模式',
    '主礼堂・音乐会模式',
  ],
  'Main Hall, theater mode': [
    'Main Hall, theater mode',
    '主禮堂・劇場模式',
    '主礼堂・剧场模式',
  ],
  'Main Hall, presentation mode': [
    'Main Hall, presentation mode',
    '主禮堂・演講模式',
    '主礼堂・演讲模式',
  ],
  Foyer: ['Foyer', '前廳', '前厅'],
  'Double-bedroom demonstration room': [
    'Double-bedroom demonstration room',
    '雙人示範房間',
    '双人示范房间',
  ],
  'Single-bedroom demonstration room': [
    'Single-bedroom demonstration room',
    '單人示範房間',
    '单人示范房间',
  ],
  'Living Lounge': ['Living Lounge', '生活休憩室', '生活休憩室'],
  'Laundry Room A': ['Laundry Room A', '洗衣房 A', '洗衣房 A'],
  'Shared kitchen': ['Shared kitchen', '共用廚房', '共用厨房'],
  'Cluster common area; Y-cluster indicated for photo05': [
    'Cluster common area; Y-cluster indicated for photo05',
    '組團公共空間；photo05 標示為 Y 組團',
    '组团公共空间；photo05标示为Y组团',
  ],
  'Co-working Space': ['Co-working Space', '共用工作空間', '共用工作空间'],
  'Curved-monitor computer area': [
    'Curved-monitor computer area',
    '曲面螢幕電腦區',
    '曲面屏幕电脑区',
  ],
  'Diners@LSKBB / official scene Canteen LSK': [
    'Diners@LSKBB / official scene Canteen LSK',
    'Diners@LSKBB / 官方現場 Canteen LSK',
    'Diners@LSKBB / 官方现场 Canteen LSK',
  ],
  'Double-height lobby/corridor': [
    'Double-height lobby/corridor',
    '挑高大堂／走廊',
    '挑高大堂／走廊',
  ],
  'E-learning Classroom A': [
    'E-learning Classroom A',
    '電子學習課室 A',
    '电子学习教室 A',
  ],
  'E-learning Classroom B': [
    'E-learning Classroom B',
    '電子學習課室 B',
    '电子学习教室 B',
  ],
  'Feature wall near shared workspace': [
    'Feature wall near shared workspace',
    '共用工作空間旁的特色牆',
    '共用工作空间旁的特色墙',
  ],
  'Group Study Room 1350': [
    'Group Study Room 1350',
    '小組研習室 1350',
    '小组研习室 1350',
  ],
  'Group study area': ['Group study area', '小組研習區', '小组研习区'],
  'Information Commons': [
    'Information Commons',
    '資訊共享空間',
    '信息共享空间',
  ],
  'Information Commons Learning Space': [
    'Information Commons Learning Space',
    '資訊共享學習空間',
    '信息共享学习空间',
  ],
  'InnoBay common work/cafe area': [
    'InnoBay common work/cafe area',
    'InnoBay 共用工作／咖啡區',
    'InnoBay共用工作／咖啡区',
  ],
  'LC-01 group room': ['LC-01 group room', 'LC-01 小組室', 'LC-01小组室'],
  'LC-03 group room': ['LC-03 group room', 'LC-03 小組室', 'LC-03小组室'],
  'LG5 teaching/group study space': [
    'LG5 teaching/group study space',
    'LG5 教學／小組研習空間',
    'LG5教学／小组研习空间',
  ],
  'Laboratory/public corridor': [
    'Laboratory/public corridor',
    '實驗室／公共走廊',
    '实验室／公共走廊',
  ],
  'Learning Commons group study tables': [
    'Learning Commons group study tables',
    '研習坊小組研習桌',
    '研习坊小组研习桌',
  ],
  'Media and Discussion Room': [
    'Media and Discussion Room',
    '媒體與討論室',
    '媒体与讨论室',
  ],
  'Multi-function Room': ['Multi-function Room', '多功能室', '多功能室'],
  'Official virtual tour Lecture Theater; exact LT letter is not exposed': [
    'Official virtual tour Lecture Theater; exact LT letter is not exposed',
    '官方虛擬導覽 Lecture Theater；未公開確切 LT 字母',
    '官方虚拟导览Lecture Theater；未公开确切LT字母',
  ],
  'Open research laboratory': [
    'Open research laboratory',
    '開放研究實驗室',
    '开放研究实验室',
  ],
  'Quiet room': ['Quiet room', '寧靜室', '安静室'],
  'Refreshment Zone': ['Refreshment Zone', '茶點區', '茶点区'],
  'Research write-up/office area': [
    'Research write-up/office area',
    '研究寫作／辦公區',
    '研究写作／办公区',
  ],
  'Room LG3-10 (filename LG310)': [
    'Room LG3-10 (filename LG310)',
    'Room LG3-10（檔名 LG310）',
    'Room LG3-10（文件名LG310）',
  ],
  'SCI/Home at Academic Concourse': [
    'SCI/Home at Academic Concourse',
    'Academic Concourse 的 SCI/Home',
    'Academic Concourse的SCI/Home',
  ],
  'Study carrels': ['Study carrels', '獨立研習桌', '独立研习桌'],
  'Study pods': ['Study pods', '研習間', '研习间'],
  'The BASE 外公共走廊': [
    'Public corridor outside The BASE',
    'The BASE 外公共走廊',
    'The BASE外公共走廊',
  ],
  'The Hong Kong Jockey Club Atrium': [
    'The Hong Kong Jockey Club Atrium',
    '香港賽馬會大堂',
    '香港赛马会大堂',
  ],
  'Tutorial spaces': ['Tutorial spaces', '導修空間', '辅导空间'],
  'Academic Concourse / Cheng Yu Tung–adjacent academic complex, official scene CWW 1F':
    [
      'Academic Concourse / Cheng Yu Tung–adjacent academic complex, official scene CWW 1F',
      'Academic Concourse／鄭裕彤樓附近學術建築群；官方現場 CWW 1F',
      'Academic Concourse／郑裕彤楼附近学术建筑群；官方现场CWW 1F',
    ],
  'Academic Concourse, official scene CWW 2F': [
    'Academic Concourse, official scene CWW 2F',
    'Academic Concourse；官方現場 CWW 2F',
    'Academic Concourse；官方现场CWW 2F',
  ],
  '李家诚创科大楼 · 宽面外观': [
    'Martin Ka Shing Lee Innovation Building · broad facade',
    '李家誠創科大樓 · 寬面外觀',
    '李家诚创科大楼 · 宽面外观',
  ],
  '李家诚创科大楼 · 转角外观': [
    'Martin Ka Shing Lee Innovation Building · corner facade',
    '李家誠創科大樓 · 轉角外觀',
    '李家诚创科大楼 · 转角外观',
  ],
  '红鸟日晷 · 交叉弧面': [
    'The Red Bird Sundial · intersecting curved surfaces',
    '紅鳥日晷 · 交叉弧面',
    '红鸟日晷 · 交叉弧面',
  ],
  '红鸟日晷 · 入口广场与红鸟周边': [
    'The Red Bird Sundial · Piazza and surroundings',
    '紅鳥日晷 · 入口廣場與紅鳥周邊',
    '红鸟日晷 · 入口广场与红鸟周边',
  ],
  '红鸟日晷 · 入口广场空间关系': [
    'The Red Bird Sundial · Piazza spatial context',
    '紅鳥日晷 · 入口廣場空間關係',
    '红鸟日晷 · 入口广场空间关系',
  ],
  '红鸟日晷 · 日晷刻度细部': [
    'The Red Bird Sundial · dial markings',
    '紅鳥日晷 · 日晷刻度細部',
    '红鸟日晷 · 日晷刻度细部',
  ],
  '红鸟日晷 · 窄支撑与周边水池': [
    'The Red Bird Sundial · narrow supports and surrounding pool',
    '紅鳥日晷 · 窄支撐與周邊水池',
    '红鸟日晷 · 窄支撑与周边水池',
  ],
  '红鸟日晷 · 高耸弯片与斜杆': [
    'The Red Bird Sundial · tall curved blade and inclined rod',
    '紅鳥日晷 · 高聳彎片與斜桿',
    '红鸟日晷 · 高耸弯片与斜杆',
  ],
  '用户报告：Hall II有盖连廊中段断开': [
    'User report: the Hall II covered corridor is broken in the middle',
    '使用者報告：Hall II 有蓋連廊中段斷開',
    '用户报告：Hall II有盖连廊中段断开',
  ],
  '长储物柜走廊入口，白墙、黑踢脚、浅灰地面，青绿色门与金属防火门；白色穿孔吊顶和线形灯。':
    [
      'Long locker corridor entrance, with white walls, black skirting, pale grey floor, turquoise doors and metal fire doors; white perforated ceiling and linear lights.',
      '長儲物櫃走廊入口，白牆、黑踢腳、淺灰地面，青綠色門與金屬防火門；白色穿孔吊頂和線形燈。',
      '长储物柜走廊入口，白墙、黑踢脚、浅灰地面，青绿色门与金属防火门；白色穿孔吊顶和线形灯。',
    ],
  '长走廊两侧浅灰三层储物柜、白圆柱、青绿色单门与金属门，连续线形灯。': [
    'Long corridor with pale grey three-tier lockers, white round columns, turquoise single doors, metal doors and continuous linear lights.',
    '長走廊兩側淺灰三層儲物櫃、白圓柱、青綠色單門與金屬門，連續線形燈。',
    '长走廊两侧浅灰三层储物柜、白圆柱、青绿色单门与金属门，连续线形灯。',
  ],
  '走廊交叉口：白圆柱、柜列、青绿色双门，右侧金属防火门；可见Lift 22指示牌。': [
    'Corridor junction with white round columns, lockers, turquoise double doors and a metal fire door on the right; a Lift 22 sign is visible.',
    '走廊交叉口：白圓柱、櫃列、青綠色雙門，右側金屬防火門；可見 Lift 22 指示牌。',
    '走廊交叉口：白圆柱、柜列、青绿色双门，右侧金属防火门；可见Lift 22指示牌。',
  ],
  '主走廊转支走廊处，柜列、青绿色门和金属双防火门；厕所导向牌可见。': [
    'Turn from the main corridor into a side corridor, with lockers, turquoise doors and metal double fire doors; a toilet direction sign is visible.',
    '主走廊轉支走廊處，櫃列、青綠色門和金屬雙防火門；廁所導向牌可見。',
    '主走廊转支走廊处，柜列、青绿色门和金属双防火门；厕所导向牌可见。',
  ],
  '较窄科研支走廊，白色高柜、白墙、青绿色双门、浅灰地面和小方格吊顶；仅走廊可见，未显示实验室室内。':
    [
      'Narrow research side corridor with tall white cabinets, white walls, turquoise double doors, pale grey floor and a square-grid ceiling. Only the corridor is visible, not laboratory interiors.',
      '較窄科研支走廊，白色高櫃、白牆、青綠色雙門、淺灰地面和小方格吊頂；僅走廊可見，未顯示實驗室室內。',
      '较窄科研支走廊，白色高柜、白墙、青绿色双门、浅灰地面和小方格吊顶；仅走廊可见，未显示实验室室内。',
    ],
  '科研走廊电梯凹区，可见Lift 21标识与不锈钢电梯门；相邻绿门、高储物柜。': [
    'Lift recess in a research corridor, showing a Lift 21 sign and stainless-steel lift doors, with adjacent green doors and tall lockers.',
    '科研走廊升降機凹區，可見 Lift 21 標識與不鏽鋼升降機門；相鄰綠門、高儲物櫃。',
    '科研走廊电梯凹区，可见Lift 21标识与不锈钢电梯门；相邻绿门、高储物柜。',
  ],
  '支走廊端部，浅灰高柜、青绿色门、白色格栅吊顶和线形灯；末端金属门。': [
    'End of a side corridor with tall pale grey cabinets, turquoise doors, white grille ceiling and linear lights; a metal door at the end.',
    '支走廊端部，淺灰高櫃、青綠色門、白色格柵吊頂和線形燈；末端金屬門。',
    '支走廊端部，浅灰高柜、青绿色门、白色格栅吊顶和线形灯；末端金属门。',
  ],
  'The BASE / HKUST Entrepreneurship Center外部公共走廊，玻璃界面内有绿/蓝座椅、白桌与橙灰地毯。':
    [
      'Public corridor outside The BASE / HKUST Entrepreneurship Center. Green/blue seating, white tables and orange-grey carpet are visible behind glass.',
      'The BASE / HKUST Entrepreneurship Center 外部公共走廊，玻璃界面內有綠／藍座椅、白桌與橙灰地毯。',
      'The BASE / HKUST Entrepreneurship Center外部公共走廊，玻璃界面内有绿／蓝座椅、白桌与橙灰地毯。',
    ],
};
/** Display-only source captions. URLs, identifiers, floor codes and official proper names stay intact. */
export function resourceText(locale: Locale, text: string): string {
  const value = Object.hasOwn(titles, text) ? titles[text] : undefined;
  if (value) return value[locale === 'en' ? 0 : locale === 'zh-Hant' ? 1 : 2];
  const corridor = /^(\S+) 公共走廊 · (\d+)$/.exec(text);
  if (corridor)
    return `${corridor[1]} ${locale === 'en' ? 'Public corridor' : '公共走廊'} · ${corridor[2]}`;
  const translated = t(locale, text);
  return locale === 'en' ? translated : nameScript(translated, locale);
}
