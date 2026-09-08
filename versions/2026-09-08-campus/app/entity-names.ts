import type { Entity } from './entity-registry';
import { t, type Locale } from './i18n';
import { entityNameLocales } from './entity-name-locales';

// Name/search conversion only. Full interface prose uses authored translations.
// Official source names and aliases remain unchanged in the registry.
const scriptPairs =
  '华華 厅廳 联聯 际際 毕畢 业業 贵貴 实實 现現 属屬 细細 组組 览覽 辆輛 学學 湾灣 东東 体體 育育 诚誠 创創 楼樓 术術 郑鄭 裕裕 彤彤 商商 务務 卢盧 家家 骢驄 宿宿 叶葉 达達 三三 贤賢 义義 会會 议議 艺藝 演演 中中 心心 水水 动動 黄黃 焯焯 书書 科科 研研 电電 变變 实實 验驗 超超 级級 计計 算算 红紅 鸟鳥 晷晷 乔喬 罗羅 桂桂 祥祥 馆館 综綜 合合 习習 慈慈 爱愛 善善 正正 曾曾 肇肇 添添 廊廊 访訪 客客 资資 讯訊 骅驊 赛賽 马馬 骝騮 竞競 技技 潮潮 荟薈 萃萃 业業 贸貿 贸貿 湿濕 海海 滨濱 吴吳 韦瑋 玮瑋 圆圓 露露 剧劇 场場 低低 烧燒 烤烤 园園 广廣 方方 树樹 泉泉 连連 桥橋 西西 贡貢 宝寶 琳琳 北北 鱿魷 鱼魚 村村 道道 银銀 峦巒 台臺 径徑 宁寧 湖湖 竹竹 角角 亚亞 贤賢 里里 门門 冯馮 凤鳳 龙龍 狮獅 清清 兰蘭 关關 驿驛 长長 坪坪 岗崗 屿嶼 岭嶺 带帶 御御 结結 跑跑 环環 派派 内內 侧側 处處 号號 层層 车車 间間 饮飲 厕廁 扶扶 梯梯 护護 摄攝 灯燈 柜櫃 墙牆 浅淺 灰灰 绿綠 双雙 防防 火火 穿穿 孔孔 顶頂 线線 形形 转轉 窄窄 格格 区區 锈鏽 钢鋼 标標 储儲 开開 放放 温溫 刻刻 度度 支支 撑撐 弧弧 面面 周周 边邊 池池 高高 耸聳 弯彎 斜斜 杆桿 宽寬 公公 共共';
const toHant = new Map(
  scriptPairs.split(' ').map((pair) => [pair[0], pair[1]]),
);
const toHans = new Map(
  scriptPairs.split(' ').map((pair) => [pair[1], pair[0]]),
);
for (const pair of ['职職', '员員', '独獨', '俪儷', '医醫', '宾賓', '云雲', '轩軒', '陈陳', '满滿']) {
  toHant.set(pair[0], pair[1]);
  toHans.set(pair[1], pair[0]);
}
toHans.set('寳', '宝');
export function nameScript(text: string, locale: Locale): string {
  const mapping = locale === 'zh-Hant' ? toHant : toHans;
  return text.replace(
    /[\u3400-\u9fff]/g,
    (character) => mapping.get(character) ?? character,
  );
}
export function normalizeSearch(text: string): string {
  return nameScript(text, 'zh-Hans')
    .toLocaleLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}
const specificNames: Record<string, readonly [string, string]> = {
  'Courts1–2；Court4（北西住宅区）；Court7（GGT北側）；Court8（东南Staff Quarters旁）':
    [
      'Courts 1–2; Court 4 (northwest residences); Court 7 (north of GGT); Court 8 (southeast Staff Quarters)',
      'Courts 1–2；Court 4（西北住宅區）；Court 7（GGT 北側）；Court 8（東南 Staff Quarters 旁）',
    ],
  '華御結 Hana-musubi': ['Hana-musubi', '華御結 Hana-musubi'],
  '跑道及场内地面（官方跑道外环派生）': [
    'Track and infield ground (derived from the official track boundary)',
    '跑道及場內地面（官方跑道外環衍生）',
  ],
  霍英东体育中心足球场: [
    'Fok Ying Tung Sports Center football pitch',
    '霍英東體育中心足球場',
  ],
  海滨网球场西侧: ['Waterfront tennis courts · west', '海濱網球場西側'],
  海滨网球场东侧: ['Waterfront tennis courts · east', '海濱網球場東側'],
};
export function entityDisplayName(
  entity: Pick<Entity, 'name' | 'aliases'> & { type?: string; entityId?: string },
  locale: Locale,
): string {
  if (entity.type === 'floor') return entity.name;
  if (entity.entityId && Object.hasOwn(entityNameLocales, entity.entityId))
    return entityNameLocales[entity.entityId][locale];
  const special = Object.hasOwn(specificNames, entity.name) ? specificNames[entity.name] : undefined;
  if (special)
    return locale === 'en'
      ? special[0]
      : locale === 'zh-Hant'
        ? special[1]
        : nameScript(entity.name, locale);
  const unnamed = /^官方未命名道路 · STREETCODE (\d+)$/.exec(entity.name);
  if (unnamed)
    return (
      (locale === 'en'
        ? 'Unnamed official road'
        : locale === 'zh-Hant'
          ? '官方未命名道路'
          : '官方未命名道路') +
      ' · STREETCODE ' +
      unnamed[1]
    );
  if (locale === 'en') {
    const sourceEnglish = entity.aliases?.find(
      (alias) => /[A-Za-z]/.test(alias) && !/[\u3400-\u9fff]/.test(alias),
    );
    return sourceEnglish || t(locale, entity.name);
  }
  const sourceChinese = /[\u3400-\u9fff]/.test(entity.name)
    ? entity.name
    : entity.aliases?.find((alias) => /[\u3400-\u9fff]/.test(alias));
  return nameScript(sourceChinese || entity.name, locale);
}
export function entitySearchNames(entity: Entity): string[] {
  return [
    entity.name,
    ...(entity.aliases || []),
    ...(['en', 'zh-Hant', 'zh-Hans'] as const).map((locale) =>
      entityDisplayName(entity, locale),
    ),
  ];
}
