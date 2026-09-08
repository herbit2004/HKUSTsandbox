export type Locale = 'en' | 'zh-Hant' | 'zh-Hans';
export const localeOptions: Array<{ id: Locale; label: string }> = [
  { id: 'en', label: 'English' },
  { id: 'zh-Hant', label: '繁體中文' },
  { id: 'zh-Hans', label: '简体中文' },
];
export function resolveLocale(value: unknown): Locale {
  return localeOptions.some((option) => option.id === value)
    ? (value as Locale)
    : 'zh-Hans';
}
// Keys retain the original source message. Values: English, Traditional Chinese,
// and optional Simplified Chinese when the key itself is an original English title.
export const messages: Record<string, readonly [string, string, string?]> = {
  浏览模式: ['Navigation mode', '瀏覽模式'],
  地图环绕: ['Orbit map', '地圖環繞'],
  自由飞行: ['Free flight', '自由飛行'],
  '围绕地图位置旋转、平移和缩放': ['Rotate, pan and zoom around a map location', '圍繞地圖位置旋轉、平移和縮放'],
  第一人称自由飞行: ['First-person free flight', '第一人稱自由飛行'],
  飞行操作: ['Flight controls', '飛行操作'],
  '鼠标观察 · WASD移动 · Space上升 · Shift下降 · Esc释放鼠标': ['Mouse to look · WASD to move · Space up · Shift down · Esc releases mouse', '滑鼠觀察 · WASD移動 · Space上升 · Shift下降 · Esc釋放滑鼠'],
  '左键拖动观察 · WASD移动 · Space上升 · Shift下降 · Esc停止操作': ['Drag to look · WASD to move · Space up · Shift down · Esc stops controls', '左鍵拖動觀察 · WASD移動 · Space上升 · Shift下降 · Esc停止操作'],
  '点击地图后，左键拖动观察 · WASD移动 · Space上升 · Shift下降': ['Click the map, then drag to look · WASD to move · Space up · Shift down', '點擊地圖後，左鍵拖動觀察 · WASD移動 · Space上升 · Shift下降'],
  '移动鼠标观察 · WASD移动 · Space上升 · Shift下降 · Esc停止操作': ['Move the mouse to look · WASD to move · Space up · Shift down · Esc stops controls', '移動滑鼠觀察 · WASD移動 · Space上升 · Shift下降 · Esc停止操作'],
  '聚焦地图后，移动鼠标观察 · WASD移动 · Space上升 · Shift下降': ['Focus the map, then move the mouse to look · WASD to move · Space up · Shift down', '聚焦地圖後，移動滑鼠觀察 · WASD移動 · Space上升 · Shift下降'],
  '点击地图捕获鼠标，开始飞行；Esc释放鼠标操作界面': ['Click the map to capture the mouse and fly; Esc releases it to use the interface', '點擊地圖擷取滑鼠，開始飛行；Esc釋放滑鼠操作介面'],
  聚焦地图开始飞行: ['Focus map to fly', '聚焦地圖開始飛行'],
  捕获鼠标开始飞行: ['Capture mouse to fly', '擷取滑鼠開始飛行'],
  飞行速度: ['Flight speed', '飛行速度'],
  '近景 · 8 m/s': ['Close view · 8 m/s', '近景 · 8 m/s'],
  '标准 · 30 m/s': ['Standard · 30 m/s', '標準 · 30 m/s'],
  '快速 · 80 m/s': ['Fast · 80 m/s', '快速 · 80 m/s'],
  '选择实体、打开楼层或预设视角会返回环绕。': ['Selecting an entity, opening floors or choosing a preset returns to orbit.', '選擇實體、開啟樓層或預設視角會返回環繞。'],
  '返回环绕时，以前方可见表面为中心；不适合环绕时恢复进入飞行前视角。': ['Orbit uses the visible surface ahead; if unsuitable, it restores the view saved before flight.', '返回環繞時，以前方可見表面為中心；不適合環繞時恢復進入飛行前視角。'],
  已恢复进入飞行前的环绕视角: ['Restored the orbit view saved before flight', '已恢復進入飛行前的環繞視角'],
  '飞行 · 恢复界面': ['Flying · Restore interface', '飛行 · 恢復介面'],
  '飞行地图，点击捕获鼠标，WASD移动，Space上升，Shift下降，Esc释放鼠标': ['Flight map: click to capture mouse, WASD to move, Space up, Shift down, Esc releases mouse', '飛行地圖，點擊擷取滑鼠，WASD移動，Space上升，Shift下降，Esc釋放滑鼠'],
  '建设中 · 尚未确认竣工': ['Under construction · Completion not yet confirmed', '建設中 · 尚未確認竣工'],
  查看相关现场影像: ['View related panoramas', '查看相關現場影像'],
  附近环境图像: ['Nearby context image', '附近環境圖像'],
  其他名称: ['Other names', '其他名稱'],
  来源中的所属关系: ['Source-recorded location', '來源中的所屬關係'],
  '原始公开资料 · 拍摄日期 {date}': ['Original public source · Capture date {date}', '原始公開資料 · 拍攝日期 {date}'],
  沉浸地图: ['Immersive map', '沉浸地圖'],
  恢复界面: ['Restore interface', '恢復介面'],
  来源记录: ['Source record', '來源記錄'],
  room_parts: ['Room geometry parts', '房間幾何部件', '房间几何部件'],
  poi_point: ['Facility point', '設施點位', '设施点位'],
  floor_drawing: ['Floor drawing', '樓層圖面', '楼层图面'],
  cad_lines: ['CAD linework', 'CAD 線稿', 'CAD线稿'],
  reference_point: ['Reference point', '參考點位', '参考点位'],
  footprint: ['Building footprint', '建築輪廓', '建筑轮廓'],
  plan_image: ['Plan image', '平面圖像', '平面图像'],
  mesh_group: ['Mesh group', '網格組', '网格组'],
  mesh_surface: ['Mesh surface', '網格表面', '网格表面'],
  diagram_stack: ['Stacked diagrams', '疊層示意', '叠层示意'],
  textured_mesh_tiles: [
    'Textured mesh tiles',
    '含紋理網格區塊',
    '含纹理网格区块',
  ],
  terrain: ['Terrain', '地形', '地形'],

  '香港科技大学清水湾 · 三维校园地图': [
    'HKUST Clear Water Bay · 3D Campus Map',
    '香港科技大學清水灣 · 三維校園地圖',
  ],
  香港科技大学校徽: ['HKUST university emblem', '香港科技大學校徽'],
  '部分外观暂未载入，可刷新重试': [
    'Some exteriors could not be loaded. Refresh to retry.',
    '部分外觀暫未載入，可重新整理後重試',
  ],
  摄影覆盖边界暂未载入: [
    'Photogrammetry coverage boundaries are not yet loaded.',
    '攝影覆蓋邊界暫未載入',
  ],
  运动场正射地表暂未载入: [
    'The sports-ground orthophoto surface is not yet loaded.',
    '運動場正射地表暫未載入',
  ],
  '入口地面细节暂未载入，请刷新重试': [
    'Entrance ground detail could not be loaded. Refresh to retry.',
    '入口地面細節暫未載入，請重新整理後重試',
  ],
  '地面衔接细节暂未载入，请刷新重试': [
    'Ground transition detail could not be loaded. Refresh to retry.',
    '地面銜接細節暫未載入，請重新整理後重試',
  ],
  '地标外观暂未载入，请刷新重试': [
    'Landmark appearance could not be loaded. Refresh to retry.',
    '地標外觀暫未載入，請重新整理後重試',
  ],
  '现状建筑外观暂未载入，请刷新重试': [
    'Current building appearance could not be loaded. Refresh to retry.',
    '現狀建築外觀暫未載入，請重新整理後重試',
  ],
  '建筑原始细节暂未载入，保留完整外观并稍后重试': [
    'Original building detail is not ready. Keeping the complete exterior and retrying shortly.',
    '建築原始細節暫未載入，保留完整外觀並稍後重試',
  ],
  完整原纹理组超出缓存预算: [
    'The complete original-texture group exceeds the cache budget.',
    '完整原紋理組超出快取預算',
  ],
  原纹理不可用: ['Original textures are unavailable.', '原紋理不可用'],
  '原纹理请求超时，将自动重试': [
    'The original-texture request timed out; retrying automatically.',
    '原紋理請求逾時，將自動重試',
  ],
  '原纹理暂未就绪，将自动重试': [
    'Original textures are not ready; retrying automatically.',
    '原紋理暫未就緒，將自動重試',
  ],
  整组原纹理尚未就绪: [
    'The complete original-texture group is not yet ready.',
    '整組原紋理尚未就緒',
  ],
  原始别名: ['Original alias', '原始別名'],
  '来源记录（原文）': ['Source record (original)', '來源記錄（原文）'],
  语言: ['Language', '語言'],
  切换实体列表: ['Toggle entity list', '切換實體列表'],
  清水湾校园: ['Clear Water Bay Campus', '清水灣校園'],
  香港科技大学: [
    'The Hong Kong University of Science and Technology',
    '香港科技大學',
  ],
  香港科技大学清水湾校园: [
    'HKUST Clear Water Bay Campus',
    '香港科技大學清水灣校園',
  ],
  校园原图: ['Official campus map', '校園原圖'],
  '2026年8月官方校园图': [
    'Official campus map · August 2026',
    '2026年8月官方校園圖',
  ],
  场景设置与来源: ['Scene settings and sources', '場景設定與來源'],
  搜索校园实体: ['Search campus entities', '搜尋校園實體'],
  '搜建筑、房号、电梯或场地': [
    'Search buildings, rooms, lifts or places',
    '搜尋建築、房號、升降機或場地',
  ],
  清除搜索: ['Clear search', '清除搜尋'],
  收起楼层: ['Close floor view', '收起樓層'],
  楼层: ['Floor', '樓層'],
  当前建筑楼层: ['Current building floor', '目前建築樓層'],
  校园总览: ['Campus overview', '校園總覽'],
  类型: ['Type', '類型'],
  筛选实体类型: ['Filter entity types', '篩選實體類型'],
  当前区域: ['Current area', '目前區域'],
  本层全部: ['Everything on this floor', '本層全部'],
  全部类型: ['All types', '全部類型'],
  全校园搜索: ['Campus-wide search', '全校園搜尋'],
  当前楼层: ['Current floor', '目前樓層'],
  全校园: ['Entire campus', '全校園'],
  校园实体树: ['Campus entity tree', '校園實體樹'],
  '显示前 160 项。输入名称、房号或类型以缩小范围。': [
    'Showing the first 160 results. Enter a name, room number or type to narrow the list.',
    '顯示前 160 項。輸入名稱、房號或類型以縮小範圍。',
  ],
  '没有匹配的公开实体。可选择全部类型或修改搜索。': [
    'No matching public entities. Select all types or change the search.',
    '沒有相符的公開實體。可選擇全部類型或修改搜尋。',
  ],
  沙盘视角: ['Campus view controls', '校園視角控制'],
  左键平移模式: ['Left-button pan mode', '左鍵平移模式'],
  左键平移已开启: ['Left-button pan is on', '左鍵平移已開啟'],
  左键平移: ['Pan with left button', '左鍵平移'],
  放大沙盘: ['Zoom in', '放大校園'],
  缩小沙盘: ['Zoom out', '縮小校園'],
  上一视角: ['Previous view', '上一視角'],
  校园全景: ['Campus overview', '校園全景'],
  北向俯视: ['North-up overhead view', '北向俯視'],
  看整层: ['View entire floor', '查看整層'],
  叠看楼层: ['Stack floors', '疊看樓層'],
  边界示意: ['Boundary illustration', '邊界示意'],
  '升起 {height}m': ['Raise by {height} m', '升起 {height}m'],
  边界示意高度: ['Illustrated boundary height', '邊界示意高度'],
  '公开平面未提供实测墙高。座席与门线保留源CAD。': [
    'Public plans do not provide measured wall heights. Seating and door lines retain the source CAD.',
    '公開平面未提供實測牆高。座席與門線保留來源 CAD。',
  ],
  当前实体: ['Selected entity', '目前實體'],
  关闭实体信息: ['Close entity information', '關閉實體資訊'],
  '已建成 · 外观为近似表示': [
    'Completed · approximate exterior representation',
    '已建成 · 外觀為近似表示',
  ],
  '社区模型与公开照片校准 · 外观为近似表示': [
    'Community model aligned to public photos · approximate appearance',
    '社群模型與公開照片校準 · 外觀為近似表示',
  ],
  '位置尚未确定，可查看所属区域资料。': [
    'Location is not yet verified. Information about its recorded area is available.',
    '位置尚未確定，可查看所屬區域資料。',
  ],
  公开停靠层: ['Recorded stops', '公開停靠層'],
  原位打开楼层: ['Open floors in place', '原位開啟樓層'],
  相关资料: ['Related resources', '相關資料'],
  '载入校园 {loaded}/{total}': [
    'Loading campus {loaded}/{total}',
    '載入校園 {loaded}/{total}',
  ],
  '正在载入附近建筑细节…': [
    'Loading nearby building detail…',
    '正在載入附近建築細節…',
  ],
  '左键平移 · 滚轮缩放': [
    'Left drag to pan · Scroll to zoom',
    '左鍵平移 · 滾輪縮放',
  ],
  '左键旋转 · 右键平移 · 滚轮缩放': [
    'Left drag to orbit · Right drag to pan · Scroll to zoom',
    '左鍵旋轉 · 右鍵平移 · 滾輪縮放',
  ],
  '正在原位置打开楼层…': ['Opening the floor in place…', '正在原位置開啟樓層…'],
  关闭设置: ['Close settings', '關閉設定'],
  场景与资料: ['Scene and resources', '場景與資料'],
  画质: ['Quality', '畫質'],
  场景画质: ['Scene quality', '場景畫質'],
  自动: ['Automatic', '自動'],
  流畅: ['Smooth', '流暢'],
  均衡: ['Balanced', '均衡'],
  高清: ['High', '高清'],
  最高: ['Ultra', '最高'],
  '根据设备能力和持续渲染开销调整细节。': [
    'Adjust detail for device capabilities and sustained rendering cost.',
    '根據裝置能力和持續渲染開銷調整細節。',
  ],
  '降低画面分辨率和细节范围，适合性能有限的设备。': [
    'Reduce rendering resolution and detail range for less powerful devices.',
    '降低畫面解析度和細節範圍，適合效能有限的裝置。',
  ],
  '兼顾近处细节和操作流畅度。': [
    'Balance nearby detail and responsive interaction.',
    '兼顧近處細節和操作流暢度。',
  ],
  '扩大清晰建筑和地面细节范围。': [
    'Expand the range of detailed buildings and ground.',
    '擴大清晰建築和地面細節範圍。',
  ],
  '使用可用的最高细节，资源和加载开销较大。': [
    'Use the highest available detail, with greater resource and loading costs.',
    '使用可用的最高細節，資源和載入開銷較大。',
  ],
  建筑名称: ['Building names', '建築名稱'],
  从海岸看校园: ['View campus from the coast', '從海岸看校園'],
  '来源、日期与运行详情': [
    'Sources, dates and runtime details',
    '來源、日期與執行詳情',
  ],
  海面边缘过渡: ['Sea-edge blending', '海面邊緣過渡'],
  '地形采集2019–2020；摄影网格包修订2025，逐栋模型包修订2026。修订不是拍摄日期。校园名称与状态保留2026公开资料。':
    [
      'Terrain survey: 2019–2020. Photogrammetry package revision: 2025; individual building package revision: 2026. Revision dates are not capture dates. Campus names and status follow public 2026 records.',
      '地形採集2019–2020；攝影網格包修訂2025，逐棟模型包修訂2026。修訂不是拍攝日期。校園名稱與狀態保留2026公開資料。',
    ],
  '楼内采用公开平面、原Z和CAD，边界升起为示意，不能替代实测BIM。': [
    'Interiors use public floor plans, original Z values and CAD. Raised boundaries are illustrations and do not replace measured BIM.',
    '樓內採用公開平面、原 Z 和 CAD，邊界升起為示意，不能替代實測 BIM。',
  ],
  '当前纹理 {textures} · 几何 {geometries} · 楼层缓存 {cache} MiB': [
    'Textures {textures} · Geometries {geometries} · Floor cache {cache} MiB',
    '目前紋理 {textures} · 幾何 {geometries} · 樓層快取 {cache} MiB',
  ],
  '同时显示 {count} 个完整外观组；外观纹理（含 mipmap）{visible} MiB，缓存 {cache} MiB，加载预留 {pending} MiB，分配预算 {budget} MiB。': [
    '{count} complete exterior groups visible; exterior textures including mipmaps {visible} MiB, cache {cache} MiB, loading reservation {pending} MiB, allocated budget {budget} MiB.',
    '同時顯示 {count} 個完整外觀組；外觀紋理（含 mipmap）{visible} MiB，快取 {cache} MiB，載入預留 {pending} MiB，分配預算 {budget} MiB。',
  ],
  '动态纹理共享预算（建筑、摄影网格、区域原图，含 mipmap 与替换遮罩）：驻留及加载预留 {used} MiB，当前上限 {cap} MiB。': [
    'Shared dynamic texture budget (buildings, photogrammetry and original region images, including mipmaps and replacement masks): resident and reserved {used} MiB; current limit {cap} MiB.',
    '動態紋理共享預算（建築、攝影網格、區域原圖，含 mipmap 與替換遮罩）：駐留及載入預留 {used} MiB，目前上限 {cap} MiB。',
  ],
  '正在释放旧资源，目标上限 {cap} MiB。': [
    'Releasing previous resources toward the target limit of {cap} MiB.',
    '正在釋放舊資源，目標上限 {cap} MiB。',
  ],
  '固定纹理另计约 {fixed} MiB；上述统计不含 CPU 位图、解码临时内存、几何和驱动开销。': [
    'Fixed textures are estimated separately at {fixed} MiB. These figures exclude CPU bitmaps, temporary decoding memory, geometry and driver overhead.',
    '固定紋理另計約 {fixed} MiB；上述統計不含 CPU 點陣圖、解碼暫存記憶體、幾何和驅動開銷。',
  ],
  '区域原纹理（含 mipmap）{used} MiB；预算 {budget} MiB。': [
    'Original region textures, including mipmaps: {used} MiB; budget {budget} MiB.',
    '區域原紋理（含 mipmap）{used} MiB；預算 {budget} MiB。',
  ],
  实体与出处记录: ['Entity and provenance records', '實體與出處記錄'],
  完整建筑模型来源: ['Complete building model sources', '完整建築模型來源'],
  实体相关资料: ['Resources for this entity', '實體相關資料'],
  返回实体沙盘: ['Return to the campus model', '返回實體校園模型'],
  '资料与所示对象、拍摄位置分别绑定；附近现场不代表房间内景。': [
    'Resources record their depicted entity and capture location separately. A nearby view does not imply a room interior.',
    '資料與所示物件、拍攝位置分別綁定；附近現場不代表房間內景。',
  ],
  查看本层附近现场影像: [
    'View nearby imagery on this floor',
    '查看本層附近現場影像',
  ],
  该实体相关图像: ['Images related to this entity', '該實體相關圖像'],
  所属建筑资料: ['Resources for its building', '所屬建築資料'],
  '暂无已绑定的图像资料。': [
    'No images are currently linked to this entity.',
    '暫無已綁定的圖像資料。',
  ],
  实体来源与空间关系: [
    'Entity provenance and spatial relations',
    '實體來源與空間關係',
  ],
  '按公开空间标识与几何归属登记。': [
    'Registered using public spatial identifiers and geometric ownership.',
    '按公開空間識別與幾何歸屬登記。',
  ],
  '源几何 / 资产': ['Source geometry / asset', '來源幾何 / 資產'],
  '源Z：{values}m': ['Source Z: {values} m', '來源 Z：{values}m'],
  实体图像资料: ['Entity imagery', '實體圖像資料'],
  关闭图像资料: ['Close imagery', '關閉圖像資料'],
  '原始公开资料 · 拍摄日期未核实': [
    'Original public resource · Capture date unverified',
    '原始公開資料 · 拍攝日期未核實',
  ],
  原始来源: ['Original source', '原始來源'],
  '建筑选择暂未更新，请重试': [
    'The building selection could not be updated. Please retry.',
    '建築選擇暫未更新，請重試',
  ],
  '校园资料读取失败，请刷新重试': [
    'Campus data could not be loaded. Please refresh and retry.',
    '校園資料讀取失敗，請重新整理後重試',
  ],
  '当前楼层暂未载入，请重试': [
    'The current floor could not be loaded. Please retry.',
    '目前樓層暫未載入，請重試',
  ],
  '相关资料读取失败，请重试': [
    'Related resources could not be loaded. Please retry.',
    '相關資料讀取失敗，請重試',
  ],
  '楼层读取失败，请重试': [
    'The floor could not be loaded. Please retry.',
    '樓層讀取失敗，請重試',
  ],
  '统一校园沙盘，拖动旋转、滚轮缩放、点击实体': [
    'Campus model: drag to orbit, scroll to zoom, click an entity',
    '統一校園模型，拖動旋轉、滾輪縮放、點擊實體',
  ],
  该建筑缺少可核实外壳边界: [
    'A verified exterior boundary is not available for this building.',
    '該建築缺少可核實外殼邊界',
  ],
  '附近地面细节暂未就绪，将自动重试': [
    'Nearby ground detail is not ready; retrying automatically.',
    '附近地面細節暫未就緒，將自動重試',
  ],
  '附近原纹理暂未就绪，将自动重试': [
    'Nearby original textures are not ready; retrying automatically.',
    '附近原紋理暫未就緒，將自動重試',
  ],
  '附近建筑原纹理暂未就绪，将自动重试': [
    'Original building textures are not ready; retrying automatically.',
    '附近建築原紋理暫未就緒，將自動重試',
  ],
  '建筑原纹理暂未就绪，将自动重试': [
    'Original building textures are not ready; retrying automatically.',
    '建築原紋理暫未就緒，將自動重試',
  ],
  校园与户外: ['Campus and outdoors', '校園與戶外'],
  建筑内: ['Inside buildings', '建築內'],
  通行与设施: ['Connections and facilities', '通行與設施'],
  其他: ['Other', '其他'],
  建筑: ['Building', '建築'],
  场地: ['Outdoor area', '場地'],
  道路: ['Road / path', '道路'],
  车行通道: ['Vehicle access', '車行通道'],
  区域: ['Area', '區域'],
  空间: ['Space', '空間'],
  电梯: ['Lift', '升降機'],
  楼梯: ['Stairs', '樓梯'],
  扶梯: ['Escalator', '扶手電梯'],
  出入口: ['Entrance / exit', '出入口'],
  门: ['Door', '門'],
  其他连接设施: ['Other connections', '其他連接設施'],
  一般设施: ['General facilities', '一般設施'],
  其他实体: ['Other entities', '其他實體'],
  连接设施: ['Connection', '連接設施'],
  设施: ['Facility', '設施'],
  校园: ['Campus', '校園'],
  实体: ['Entity', '實體'],
  房间: ['Room', '房間'],
  洗手间: ['Toilet', '洗手間'],
  图书馆空间: ['Library space', '圖書館空間'],
  走廊: ['Corridor', '走廊'],
  大堂: ['Lobby', '大堂'],
  球场: ['Sports court', '球場'],
  网球场: ['Tennis court', '網球場'],
  足球场: ['Football pitch', '足球場'],
  田径场: ['Athletics track', '田徑場'],
  广场: ['Piazza', '廣場'],
  饮水机: ['Drinking fountain', '飲水機'],
  饮水设施: ['Drinking water', '飲水設施'],
  AED: ['AED', 'AED'],
  ATM: ['ATM', 'ATM'],
  巴士站: ['Bus station', '巴士站'],
  餐饮摊位: ['Food outlet', '餐飲攤位'],
  九巴服务站: ['KMB kiosk', '九巴服務站'],
  地标: ['Landmark', '地標'],
  日晷: ['Sundial', '日晷'],
  真实室内全景: ['Original indoor panoramas', '真實室內全景'],
  真实现场影像: ['Original scene imagery', '真實現場影像'],
  选择现场: ['Choose a scene', '選擇現場'],
  '拖动 / ← → 环顾 · + − 缩放 · 数字键进入相邻点 · 拍摄日期未核实': [
    'Drag / ← → to look around · + − to zoom · Number keys for neighbors · Capture date unverified',
    '拖動 / ← → 環顧 · + − 縮放 · 數字鍵進入相鄰點 · 拍攝日期未核實',
  ],
  关闭全景: ['Close panorama', '關閉全景'],
  返回原楼层与房间: [
    'Return to the original floor and room',
    '返回原樓層與房間',
  ],
  '更多官方全景（联网加载）': [
    'More official panoramas (online)',
    '更多官方全景（連線載入）',
  ],
  全景建筑筛选: ['Filter panorama buildings', '全景建築篩選'],
  全部建筑: ['All buildings', '全部建築'],
  全景楼层筛选: ['Filter panorama floors', '全景樓層篩選'],
  全部楼层: ['All floors', '全部樓層'],
  全景场景: ['Panorama scene', '全景場景'],
  暂无匹配场景: ['No matching scenes', '暫無相符場景'],
  '联网 · ': ['Online · ', '連線 · '],
  '公共影像按需载入。线段只表示官方节点连接，不保证现实通行。': [
    'Public imagery loads on demand. Lines show official node connections, not guaranteed physical access.',
    '公共影像按需載入。線段只表示官方節點連接，不保證現實通行。',
  ],
  官方来源: ['Official source', '官方來源'],
  返回上一全景: ['Previous panorama', '返回上一全景'],
  放大全景: ['Zoom in on panorama', '放大全景'],
  缩小全景: ['Zoom out of panorama', '縮小全景'],
  收起位置图: ['Hide location map', '收起位置圖'],
  显示位置图: ['Show location map', '顯示位置圖'],
  该筛选下暂无现场: ['No scenes match this filter', '該篩選下暫無現場'],
  '正在载入当前现场…': ['Loading this scene…', '正在載入目前現場…'],
  '官方相邻点 {count} 处': [
    '{count} official neighboring points',
    '官方相鄰點 {count} 處',
  ],
  当前场景没有公开连接: [
    'No public connections for this scene',
    '目前場景沒有公開連接',
  ],
  '仅当前影像驻留 · 返回保留原楼层位置 · 图中方向与影像朝向不作测量北向': [
    'Only the current image stays loaded · Return preserves the floor view · Map and image headings are not surveyed north',
    '僅目前影像駐留 · 返回保留原樓層位置 · 圖中方向與影像朝向不作測量北向',
  ],
  '此历史场景缺少可核实的同层位置。': [
    'This historical scene has no verified same-floor location.',
    '此歷史場景缺少可核實的同層位置。',
  ],
  未标层: ['Floor unspecified', '未標樓層'],
  '红点为当前现场 · 选择圆点可跳转': [
    'Red is the current scene · Select a point to move',
    '紅點為目前現場 · 選擇圓點可跳轉',
  ],
  当前楼层全景点与官方连接: [
    'Current-floor panorama points and official connections',
    '目前樓層全景點與官方連接',
  ],
  '位置图跳转 {name}': [
    'Open {name} from the location map',
    '位置圖跳轉 {name}',
  ],
  '{count} 个同层点位；不含推测路线。': [
    '{count} points on the same floor; no inferred routes.',
    '{count} 個同層點位；不含推測路線。',
  ],
  '该楼层暂无匹配全景，可改变建筑或楼层筛选。': [
    'No panoramas match this floor. Change the building or floor filter.',
    '該樓層暫無相符全景，可變更建築或樓層篩選。',
  ],
  官方影像暂时无法读取: [
    'Official imagery is temporarily unavailable.',
    '官方影像暫時無法讀取',
  ],
  '全景目录读取失败，请重试': [
    'The panorama catalog could not be loaded. Please retry.',
    '全景目錄讀取失敗，請重試',
  ],
  '全景影像读取失败，请重试': [
    'The panorama could not be loaded. Please retry.',
    '全景影像讀取失敗，請重試',
  ],
  'building-evidence': [
    'Cross-checked building source evidence.',
    '已交叉核對的建築來源證據。',
    '已交叉核对的建筑来源证据。',
  ],
  'catalog.indoorBuilding/focusParent or building-evidence named wing notes; source geometry is not inferred':
    [
      'Ownership follows the catalog indoorBuilding/focusParent or named-wing source notes; geometry is not inferred.',
      '歸屬依據目錄 indoorBuilding/focusParent 或具名翼樓來源註記；不推測幾何。',
      '归属依据目录 indoorBuilding/focusParent 或具名翼楼来源注记；不推测几何。',
    ],
  '官方CDO当前状态Completed；正式中文名李家誠創科大樓。公开楼层与2026官方实景支持在原位置显示已建成近似外观，屋顶与立面参数不视为测量。':
    [
      'The official CDO status is Completed. Public floors and official 2026 photographs support an approximate completed exterior in place. Roof and facade parameters are not measurements.',
      '官方 CDO 目前狀態為 Completed；正式中文名李家誠創科大樓。公開樓層與2026官方實景支持在原位置顯示已建成近似外觀，屋頂與立面參數不視為測量。',
    ],
  'CMO states Red Bird, Sundial and Circle of Time refer to one sculpture; Brand Guideline formal name The Red Bird Sundial':
    [
      'CMO identifies Red Bird, Sundial and Circle of Time as one sculpture. The Brand Guideline names it The Red Bird Sundial.',
      'CMO 指出 Red Bird、Sundial 與 Circle of Time 為同一雕塑；品牌指引正式名稱為 The Red Bird Sundial。',
      'CMO指出Red Bird、Sundial与Circle of Time为同一雕塑；品牌指引正式名称为The Red Bird Sundial。',
    ],
  line_group: ['Line group', '線組', '线组'],
  point: ['Point', '點位', '点位'],
  polygon: ['Polygon', '多邊形', '多边形'],
  mesh: ['Mesh', '網格', '网格'],
  floor_plan: ['Floor plan', '樓層平面', '楼层平面'],
  floorplan: ['Floor plan', '樓層平面', '楼层平面'],
  boundary: ['Boundary', '邊界', '边界'],
};
export function hasTranslation(key: string): boolean {
  return Object.hasOwn(messages, key);
}

export function t(
  locale: Locale,
  key: string,
  params: Record<string, string | number> = {},
): string {
  const entry = Object.hasOwn(messages, key) ? messages[key] : undefined;
  const text = entry
    ? locale === 'en'
      ? entry[0]
      : locale === 'zh-Hant'
        ? entry[1]
        : (entry[2] ?? key)
    : key;
  return text.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.hasOwn(params, name) ? String(params[name]) : match,
  );
}
