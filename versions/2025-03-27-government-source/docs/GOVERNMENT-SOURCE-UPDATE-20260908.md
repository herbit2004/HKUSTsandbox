# 政府三维来源更新核查 · 2026-09-08

未发现比项目已使用来源更新、且已确认包含李家誠創科大樓与 iVillage / Hall X–XIII 竣工外观的政府摄影模型。Shaw Auditorium 的政府原生模型已经在本地使用。此次核查没有替换任何现有几何或纹理。

| 产品 | 12-NW-6C | 12-NW-11A | 判断 |
|---|---|---|---|
| Tile-based 摄影网格 | 2025-03-27 | 2025-03-27 | 与现用来源相同 |
| Individualised 有纹理单体 | 2026-04-24 | 2025-03-27 | 本地已经使用该版本 |
| Non-textured 无纹理单体 | 2026-04-24 | 2025-09-29 | 与对应有纹理包的建筑身份集合一致，未找到额外新楼对象 |
| 3D-BIT00 几何/属性 | 2026-04-01 | 2026-04-01 | 与已保存资料图幅版本相同 |

官方逐幅 CSV 与 FeatureServer 日期交叉确认。CSV HTTP Last-Modified 为 2026-08-30 16:00:18 GMT（香港8月31日），校园图幅仍为上述日期。全局元数据修订日期、CSV 更新时间与 ZIP 重打包日期不能当作校园摄影采集或新楼模型更新日期。

原始逐幅表：[摄影网格](https://www.landsd.gov.hk/landsd_psi_data/SMO/data/3dvm_tilebased_update.csv)、[有纹理单体](https://www.landsd.gov.hk/landsd_psi_data/SMO/data/3dvm_individualised_update.csv)、[无纹理单体](https://www.landsd.gov.hk/landsd_psi_data/SMO/data/3dvm_nontextured_update.csv)、[BIT00](https://www.landsd.gov.hk/doc/en/mapping/digital-map/common/update/3d_update.csv)。

## 对象与真实下载包检查

- Shaw：政府对象 `B451872165201063A0`，LOD3/3A、6,427 三角形、主纹理4096×4096。远端7个文件与已保存原生资源大小/CRC一致；本地 standalone 和 exteriors manifest 已引用。它不是本次发现的更晚版本。
- 创新楼近邻 `B452662165301062A0`、`B452672172701062A0` 的小型 glTF 已读取，高度约7.52 m和4.40 m，尺寸/位置不覆盖已保存的创新楼主体轮廓，不能用来替换现状模型。
- iVillage 近邻 `B455802160301062A0`、`B455542150401062A0` 高约5.85 m和3.80 m，不能当作宿舍楼群。未发现已确认覆盖建成楼群的独立原生模型。
- 6C与11A的无纹理包分别有53、134个对象；去除LOD/版本编码后的地理身份集合与相应有纹理包一致。此结果不能证明所有几何字节相同。
- 对远端ZIP中央目录和本地原生资源做比较，6C已保存140文件、11A已保存13文件均大小/CRC一致。没有下载全幅或全港大包。

| 下载包 | 实际字节 | HTTP Last-Modified UTC |
|---|---:|---|
| CESIUM/12-NW-6C.zip | 664,752,327 | 2025-03-20 03:36:08 |
| CESIUM/12-NW-11A.zip | 535,317,659 | 2025-03-20 03:36:15 |
| GLTF/12-NW-6C.zip | 1,946,470,142 | 2026-04-02 10:11:41 |
| GLTF/12-NW-11A.zip | 1,385,939,398 | 2026-01-16 20:16:16 |
| GLTF0/12-NW-6C.zip | 40,436,867 | 2026-04-01 09:49:18 |
| GLTF0/12-NW-11A.zip | 44,220,165 | 2025-09-02 09:56:24 |

摄影网格的局部子树确有L20/L21；公开预览只使用较粗前沿与最大边512的纹理。提取更细LOD可以提高同次采集模型的清晰度，但不能补出未采集的新竣工建筑。3A表示暴露立面有照片纹理，不表示当前实况或测量级BIM。[官方单体模型说明](https://static.csdi.gov.hk/csdi-webpage/download/common/462b62ddbb400a794759523ce1fdb13a3533c9078cd09dd6365546c30db77ad0)

## 后续更新与边界

政府招标 LD SMO/HQ/2026/07 涉及香港岛、离岛、九龙及新界南的航空测量与三维更新，2026-08-07截标、合同21个月。公告未给HKUST采集日期、交付批次或公开上线日期，不能承诺校园新版时间。[招标公告](https://www.landsd.gov.hk/sc/whats-new/on-going-tenders/tender-goods-services-consultancies/tn-ss/tn-ss_LD-SMO-HQ-2026-07.html)

未证明所有未保存近邻对象的完整视觉内容、政府是否拥有未公开的新楼生产数据或未来校园覆盖时间。现阶段保留有来源记录的现状补建，不把附近低矮对象或旧施工摄影网格冒充新竣工楼体。
