import type { Locale } from './i18n';

type LocalizedEntityName = Readonly<Record<Locale, string>>;
const names = (en: string, hans: string, hant: string): LocalizedEntityName => ({
  en, 'zh-Hans': hans, 'zh-Hant': hant,
});

/** Display names only, keyed by canonical identity. Source names, aliases, physical
 * domains and IDs remain in the registry. Donor names come from its checked names
 * and aliases; generic residence/group names below are literal translations.
 * Coastal Marine Lab and Innovation Village have descriptive Chinese translations,
 * not independently certified Chinese naming records. */
export const entityNameLocales: Readonly<Record<string, LocalizedEntityName>> = {
  'building:b00000000000000000000001': names('Academic Building', '主学术大楼', '主學術大樓'),
  'building:b00000000000000000000002': names('Cheng Yu Tung Building', '郑裕彤楼', '鄭裕彤樓'),
  'building:b00000000000000000000003': names('Shaw Auditorium', '逸夫演艺中心', '逸夫演藝中心'),
  'building:b00000000000000000000004': names('Lee Shau Kee Business Building', '李兆基商学大楼', '李兆基商學大樓'),
  'building:b00000000000000000000005': names('HKUST Jockey Club Institute for Advanced Study / Lo Ka Chung Building', '香港科技大学赛马会高等研究院／卢家骢荟萃楼', '香港科技大學賽馬會高等研究院／盧家驄薈萃樓'),
  'building:b00000000000000000000006': names('Lo Ka Chung University Center', '卢家骢大学中心', '盧家驄大學中心'),
  'building:68ec6a9f32cc78a7ddf5ddb8': names('UG Hall I', '本科生宿舍1座', '本科生宿舍1座'),
  'building:68ec6b9632cc78a7ddf60beb': names('UG Hall II', '本科生宿舍2座', '本科生宿舍2座'),
  'building:68f9c3226e1e3a08098d2422': names('Tsang Shiu Tim Sports Centre', '曾肇添体育中心', '曾肇添體育中心'),
  'building:68f9de0b6e1e3a08099778dc': names('Coastal Marine Lab', '海岸海洋实验室', '海岸海洋實驗室'),
  'building:6902ca00b253da38aa2bab32': names('Li Dak Sum Yip Yio Chin Kenneth Li Conference Lodge', '李达三叶耀珍伉俪李本俊会议大楼', '李達三葉耀珍伉儷李本俊會議大樓'),
  'building:691adb789d35c25557ecab1f': names('UG Hall X', '本科生宿舍10座', '本科生宿舍10座'),
  'building:691c1bd903d92703c16b976f': names('UG Hall XII', '本科生宿舍12座', '本科生宿舍12座'),
  'building:691c1bf6923bee03b533d62b': names('UG Hall XI · DJI Hall', '本科生宿舍11座 · 大疆创新楼', '本科生宿舍11座 · 大疆創新樓'),
  'building:691c1c081c838d03d9a6dc21': names('UG Hall XIII', '本科生宿舍13座', '本科生宿舍13座'),
  'building:69201b741c838d03d9fbe71b': names('Martin Ka Shing Lee Innovation Building', '李家诚创科大楼', '李家誠創科大樓'),
  'building:695377863568ed07f4fc7e0f': names('Water Sports Center', '水上活动中心', '水上活動中心'),
  'building:6a85579974fe9a95803085ac': names('UG Hall VI', '本科生宿舍6座', '本科生宿舍6座'),
  'building:catalog:campus-20': names('HKUST Medical Education and Research Complex', '医学教育及研究大楼', '醫學教育及研究大樓'),
  'building:catalog:campus-27': names('Daniel & Mayce Yu Research Building', 'Daniel & Mayce Yu 科研楼', 'Daniel & Mayce Yu 科研樓'),
  'building:catalog:campus-32': names('Tsang Chiu Sang Tower', '曾超生楼', '曾超生樓'),
  // Official name uses 寳; the alternate 寶 spelling remains searchable.
  'building:catalog:campus-33': names('Lam Po Yu Tower', '林宝茹楼', '林寳茹樓'),
  'building:catalog:campus-35': names('Jockey Club Global Graduate Tower', '赛马会集贤楼', '賽馬會集賢樓'),
  'building:catalog:campus-43': names('President’s Lodge', '校长宿舍', '校長宿舍'),
  'building:catalog:campus-44': names('Distinguished Guest Lodge', '贵宾宿舍', '貴賓宿舍'),
  'building:catalog:campus-45': names('UniLodge', '水云轩', '水雲軒'),
  'building:catalog:ug-hall-3': names('UG Hall III', '本科生宿舍3座', '本科生宿舍3座'),
  'building:catalog:ug-hall-4': names('UG Hall IV', '本科生宿舍4座', '本科生宿舍4座'),
  'building:catalog:ug-hall-5': names('UG Hall V', '本科生宿舍5座', '本科生宿舍5座'),
  'building:catalog:ug-hall-7': names('UG Hall VII', '本科生宿舍7座', '本科生宿舍7座'),
  'building:catalog:ug-hall-8': names('UG Hall VIII', '本科生宿舍8座', '本科生宿舍8座'),
  'building:catalog:ug-hall-9': names('UG Hall IX', '本科生宿舍9座', '本科生宿舍9座'),
  ...Object.fromEntries(['C', 'D'].map((letter) => [
    `building:catalog:university-apartments-tower-${letter.toLowerCase()}`,
    names(`University Apartments Tower ${letter}`, `大学公寓${letter}座`, `大學公寓${letter}座`),
  ])),
  ...Object.fromEntries([1, 2, 3, 4].map((number) => [
    `building:catalog:staff-quarters-tower-${number}`,
    names(`Staff Quarters Tower ${number}`, `教职员宿舍第${number}座`, `教職員宿舍第${number}座`),
  ])),
  ...Object.fromEntries([1, 2, 3, 4, 5, 6, 7, 8].map((number) => [
    `building:catalog:staff-quarters-house-${number}`,
    names(`Staff Quarters House ${number}`, `教职员宿舍独立屋${number}号`, `教職員宿舍獨立屋${number}號`),
  ])),
  ...Object.fromEntries(['P', 'Q', 'R', 'S'].map((letter) => [
    `building:catalog:staff-quarters-block-${letter.toLowerCase()}`,
    names(`Staff Quarters Block ${letter}`, `教职员宿舍${letter}座`, `教職員宿舍${letter}座`),
  ])),
  ...Object.fromEntries(['1-12', '13-24', '25-36', '37-48'].map((range) => [
    `building:catalog:staff-quarters-apartments-${range}`,
    names(`Staff Quarters Apartments ${range}`, `教职员宿舍公寓${range}号`, `教職員宿舍公寓${range}號`),
  ])),
  'zone:catalog:campus-34': names('University Apartments Towers C and D', '大学公寓C、D座', '大學公寓C、D座'),
  ...Object.fromEntries([
    ['37', '1–2'], ['38', '3–4'], ['39', '5–7'],
    ['40', '8–11'], ['41', '12–14'], ['42', '15–19'],
  ].map(([id, range]) => [
    `zone:catalog:campus-${id}`,
    names(`Staff Quarters Towers ${range}`, `教职员宿舍第${range}座`, `教職員宿舍第${range}座`),
  ])),
  'zone:catalog:campus-46': names('Staff Quarters Houses 1–8 and Apartments 1–48', '教职员宿舍独立屋1–8号及公寓1–48号', '教職員宿舍獨立屋1–8號及公寓1–48號'),
  'zone:catalog:campus-47': names('Staff Quarters Blocks P–S', '教职员宿舍P–S座', '教職員宿舍P–S座'),
  'zone:catalog:campus-52': names('Fok Ying Tung Sports Center', '霍英东体育中心', '霍英東體育中心'),
  'zone:catalog:campus-55': names('Courts 1–2, 4, 7 and 8', '球场1–2、4、7及8', '球場1–2、4、7及8'),
  'zone:catalog:campus-62': names('North/South Entrances and Bus Stations; University Road, Ngan Ying Road and Clear Water Bay Road', '南北入口及巴士站、大学道、银影路、清水湾道', '南北入口及巴士站、大學道、銀影路、清水灣道'),
  'zone:innovation-village': names('Innovation Village · Halls X–XIII', '创新村 · 本科生宿舍10–13座', '創新村 · 本科生宿舍10–13座'),
  'zone:hkust-cwb:ug-halls-8-9': names('Undergraduate Halls VIII & IX', '本科生宿舍 VIII／IX', '本科生宿舍 VIII／IX'),
};

export const descriptiveNameTranslations = [
  'building:68f9de0b6e1e3a08099778dc',
  'zone:innovation-village',
] as const;
