# 代码与第三方资料的权利边界

仓库公开不等于对全部内容重新授权。本项目未为项目自编代码新增统一开源许可证；依赖和保留的第三方源码遵循各自原有许可证。`components/ui` 来源于 shadcn 模板生态，相关包和依赖许可证请查看 lockfile 对应版本。

## 公开政府数据包

**3D Visualisation Map from Lands Department; LiDAR DTM from Civil Engineering and Development Department, Hong Kong SAR Government.** Source: [Common Spatial Data Infrastructure Portal](https://portal.csdi.gov.hk/).

政府保留其数据知识产权，依据 [CSDI Terms and Conditions](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC) 使用。该条款允许包括商业用途的复制、分发等使用，要求标识政府与来源。本项目对校园范围进行了坐标转换、预览采样及有证据的局部处理；不改变政府原始数据的所有权，不保证测绘精度或现状时效。数据版本/源日期随包记录。

## 仅本地保留

- HKUST Path Advisor 原始楼层、CAD、接口响应及官方下载 JS：未核实开放再分发许可；只发布本项目编写的处理代码和来源入口，不发布第三方 JS 或原始响应中的无关管理 ID。
- 校方照片、全景、平面图与校徽，以及内嵌这些像素的 GLB/纹理：未核实公开再分发许可。本地保留来源/哈希/近似说明；不出现在公开数据包中。校徽不暗示校方认可。
- 原用户截图、逐字要求和历史视觉证据：本地保留用于 QA；公开目标/验收状态不表示这些附件也被公开。
- 日晷社区模型等单独来源资产的许可只适用于其原始对象，不能扩展到校方品牌或其他数据；完整本地来源说明继续保留，公开 baseline 不包含它们。

发布新数据版本时必须逐项沿用或核对原始条款，不能把政府条款扩展到 HKUST 资料，也不能用项目代码许可证覆盖第三方资产。
