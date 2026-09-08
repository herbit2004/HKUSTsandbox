# HKUST Path Advisor 公开地图渲染语义核实

核实日期：2026-09-05。依据官方生产站当前脚本 https://navigate.ust.hk/path/app/static/js/main.c4c44c26.js ，本地完整副本 `main.js`。仅阅读已实际公开引用的脚本和已公开返回的数据；这次语义核实未做浏览器像素对照，也未访问登录资源。

## 已证实规则

1. 整个脚本 `hidden_from_map` 仅出现 1 次，用于 room polygon fill-color。严格布尔 true 的填色是 #F9FCFF；其他值（包括缺失字段）在有 type_color_hex 时使用对应颜色，否则 #CCCCCC。fill-opacity 为 1。没有按该字段过滤几何。
2. 房间多边形和轮廓来源均为完整 source_geojson，没有 visibility 标识正向白名单。楼层 geojson 作为 prop 直接赋值并 setData。不能因 hidden 或字段缺失而删除多边形。
3. cad_geojson 是官方独立 source_cad_geojson / layer_cad_geojson 线层；色 #D3D3D3、opacity 0.8，按 zoom 控制宽度，不检查 hidden 字段。
4. 当 CAD 存在时官方把 layer_geojson_outline 隐藏，用 CAD 作为结构细线；CAD 缺失时才显示多边形粗轮廓。应保留 CAD，不必凭缺失 hidden 字段拒绝。
5. 普通地图名称标签来自 source_nav_nodes，layer_nav_nodes_label 仅在 type_display_setting 为 show_location_name 或 show_location_name_and_icon 时显示 name；仍有 zoom/minZoom 规则。这与 room polygon 的 hidden 字段无关。应按公开 nav-node 显示规则做标注，不从 hidden polygon 属性额外合成标签。

## 对现有资产的应用

已下载的 9951 个 rooms.geojson 多边形可以全部作为公开地图平面几何；63 层原始 CAD 可以恢复细墙线、柱等线画。5653 个 hidden=true 元素应采用中性色，不代表 5653 个公众不可见的房间。此前导出的 floor-plan.svg 虽未给 hidden 元素加标题，但仍使用 type_color_hex，不完全等同官方配色；若用于最终产品，应按以上规则修正。

这些二维公开图层本身不是经测量验证的室内 BIM，不直接证明每条 CAD 线都是墙，也不能推定未公开的房门/层高/实体墙体厚度。后端搜索是否对特定类别另有可见性过滤，本次没有证据；不能从 fill 规则扩大推定。原始 JSON 里可出现人员/管理元数据，不必向产品展示。以上允许恢复公众地图已有几何，不建议额外揭示隐藏对象的名称/用途。

## 源码证据

### room_fill_and_outline

字符偏移 [1848680, 1849190)（0 起算，不是源码行号）

```js
Ie=()=>{M.current.addSource("source_geojson",{type:"geojson",data:NM}),M.current.addLayer({type:"fill",id:"layer_geojson",source:"source_geojson",paint:{"fill-color":["case",["==",["get","hidden_from_map"],!0],"#F9FCFF",["has","type_color_hex"],["concat","#",["get","type_color_hex"]],"#CCCCCC"],"fill-opacity":1}}),M.current.addLayer({type:"line",id:"layer_geojson_outline",source:"source_geojson",paint:{"line-color":"#CCCCCC","line-width":["interpolate",["linear"],["zoom"],16,0,17,.5,18,1,19,1.5,20,2]}})},
```

### cad_line_layer

字符偏移 [1848388, 1848680)（0 起算，不是源码行号）

```js
ke=()=>{M.current.addSource("source_cad_geojson",{type:"geojson",data:NM}),M.current.addLayer({type:"line",id:"layer_cad_geojson",source:"source_cad_geojson",paint:{"line-color":"#D3D3D3","line-width":["interpolate",["linear"],["zoom"],16,.5,17,.75,18,1,19,1.25,20,1.5],"line-opacity":.8}})},
```

### cad_toggles_outline

字符偏移 [1861549, 1861818)（0 起算，不是源码行号）

```js
(0,a.useEffect)(()=>{M.current&&M.current.getSource("source_cad_geojson")&&(M.current.getSource("source_cad_geojson").setData(j||NM),M.current.getLayer("layer_geojson_outline")&&M.current.setLayoutProperty("layer_geojson_outline","visibility",j?"none":"visible"))},[j])
```

### nav_node_label

字符偏移 [1850257, 1850883)（0 起算，不是源码行号）

```js
M.current.addLayer({type:"symbol",id:"layer_nav_nodes_label",source:"source_nav_nodes",layout:{"text-field":["case",["any",["==",["get","type_display_setting"],"show_location_name"],["==",["get","type_display_setting"],"show_location_name_and_icon"]],["get","name"],""],"text-variable-anchor":["center"],"text-font":["Open Sans Bold"],"text-size":14,"text-anchor":"bottom","text-offset":[0,0],"text-max-width":10,"icon-image":"type-image","icon-size":1,"icon-anchor":"top"},paint:{"text-color":"#003366","text-halo-color":"#FFFFFF","text-halo-width":1},filter:[">=",["zoom"],["case",["has","minZoom"],["get","minZoom"],18]]}),
```

### map_props

字符偏移 [1836411, 1836774)（0 起算，不是源码行号）

```js
FM=(0,a.forwardRef)(function(e,t){let{className:n,style:r,loading:i,locationId:s,baseMapOnClick:c,mapOnClick:u,locationCoordinates:d,navEdges:h,geojson:p,cadGeojson:f,baseGeojson:m,navNodes:g,pointOfInterests:v,zoom:y,initialCenter:_,popupComponent:b,filteredLocations:x,keyword:w,disableAutoZoom:E,hideEdgeArrows:S,userLocation:A,userHeading:C,activeFloorId:T}=e
```

### floor_prop_assignment

字符偏移 [1861101, 1861177)（0 起算，不是源码行号）

```js
(0,a.useEffect)(()=>{B(p||null)},[p]),(0,a.useEffect)(()=>{U(f||null)},[f]),
```

### full_room_data

字符偏移 [1861284, 1861548)（0 起算，不是源码行号）

```js
(0,a.useEffect)(()=>{M.current.getSource("source_geojson")&&(F?M.current.getSource("source_geojson").setData(F):(M.current.getSource("source_geojson").setData(NM),oe.current=null,P.current&&(P.current.remove(),P.current=new(SM().Marker)({color:"#FF0000"}))))},[F])
```
