"""Refresh installed-model inventory without changing visual acceptance decisions."""
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
D = P / 'docs/source-evidence-v4/building-quality'
read = lambda path: json.loads(path.read_text())
path = D / 'visual-quality-status.json'
report = read(path)
registry_entities = read(P / 'public/data/entity-registry.json')['entities']
by_id = {e['entityId']: e for e in registry_entities}
entities = [e for e in registry_entities if e['type'] == 'building']
prior = {row['entityId']: row for row in report['rows']}
rows = []
for entity in entities:
    row = prior.get(entity['entityId'], {
        'entityId': entity['entityId'],
        'status': 'pending-multiangle-runtime-acceptance',
        'note': '尚未完成与Academic同等正常认路距离的逐栋多角度、近区加载与切区返回验收。',
        'evidence': [], 'finalVisualAcceptance': False,
    })
    row['name'] = entity['name']
    row['installedModels'] = [
        {k: model[k] for k in ['type', 'asset', 'subtype', 'featureId'] if k in model}
        for model in entity['representations']
        if model.get('subtype') == 'exterior_bundle' or model.get('subtype', '').endswith('_current_form_approximation')
    ]
    for relation in entity.get('relations', []):
        if relation['type'] != 'sharesExteriorWith':
            continue
        owner = by_id.get(relation['targetId'])
        if not owner or owner['type'] != 'zone':
            continue
        row['installedModels'].extend({
            'type': 'reference', 'subtype': 'shared_exterior_bundle_reference',
            'asset': model['asset'], 'featureId': model['featureId'],
            'ownerEntityId': owner['entityId'],
        } for model in owner['representations'] if model.get('subtype') == 'exterior_bundle')
    rows.append(row)
assert set(prior).issubset({row['entityId'] for row in rows}), 'Do not discard existing acceptance rows.'
bundles = read(P / 'public/models/exteriors/manifest.json')['bundles']
prior_groups = {row['physicalDomainId']: row for row in report.get('physicalGroupRows', [])}
physical_groups = []
for bundle in bundles:
    entity = by_id.get(bundle.get('entityId'))
    domain_id = bundle.get('physicalDomainId')
    if not entity or entity['type'] != 'zone' or not domain_id:
        continue
    row = prior_groups.get(domain_id, {
        'physicalDomainId': domain_id,
        'status': 'pending-multiangle-runtime-acceptance',
        'note': '官方聚合楼域；区间中的编号尚无逐座边界证据。完整原生源已安装，未完成真实多角度验收。',
        'evidence': [], 'finalVisualAcceptance': False,
    })
    row.update(entityId=entity['entityId'], name=entity['name'],
               installedBundleId=bundle['id'])
    physical_groups.append(row)
assert set(prior_groups).issubset({row['physicalDomainId'] for row in physical_groups}), 'Do not discard physical-group acceptance rows.'
report.update(rows=rows, registryBuildingRecords=len(rows),
              physicalGroupRows=physical_groups,
              unresolvedAggregatePhysicalDomains=len(physical_groups),
              finalAcceptedBuildings=sum(row.get('finalVisualAcceptance') is True for row in rows),
              workingTreeNativeExteriorGroups=len(bundles),
              workingTreeNativeSourceObjects=sum(len(bundle['objects']) for bundle in bundles),
              lastPublishedSnapshot=(P / '.preview/current').resolve().name)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
lines = ['# 全校逐栋实际视觉验收状态', '',
         f"仍在执行；最终通过{report['finalAcceptedBuildings']}栋。{len(rows)}个registry建筑记录不等于最终独立物理楼数；{report['remainingUnsplitStaffTowerNames']}个Staff Tower名称仍待独立边界确认。", '',
         f"已发布快照：`{report['lastPublishedSnapshot']}`。工作区{len(bundles)}原生组/{report['workingTreeNativeSourceObjects']}源对象，发布与真实运行验收分别记录于QA-v4。", '',
         '| 实体 | 状态 | 已安装可验模型 |', '|---|---|---|']
runtime_note = report.get('publishedRuntimeAcceptance')
if runtime_note:
    lines[2:2] = ['**运行说明（来自验收 JSON）**：' + str(runtime_note), '']
for row in rows:
    installed = ', '.join(model.get('subtype', model['type']) for model in row['installedModels']) or '待查最高源/完整实体表示'
    lines.append(f"| {row['name']} | {row['status']} | {installed} |")
ggt_row = next((row for row in rows if row['entityId'] == 'building:catalog:campus-35'), None)
if ggt_row and ggt_row.get('occlusionAudit'):
    lines.extend(['', '## 集贤楼基座候选：遮挡假设更正', '', ggt_row['note'], '',
                  '完整审计：[面级证据与未启用候选](ggt-front-base-candidate/occlusion-audit/README.zh.md)。历史措辞保存在审计 history 目录；结构检查不等于视觉验收。'])

if physical_groups:
    lines.extend(['', '## 成员分界尚未确认的共同物理楼域', '',
                  '下列每行是已确认的官方共同楼域，不能将编号数量或源对象数量当作独立建筑数。与上表分别追踪，均须真实多角度验收；VIII／IX共同域不算第三栋建筑。', '',
                  '| 范围实体 | 官方物理域 | 状态 | 已安装外观组 |', '|---|---|---|---|'])
    for row in physical_groups:
        lines.append(f"| {row['name']} | {row['physicalDomainId']} | {row['status']} | {row['installedBundleId']} |")
(D / 'visual-quality-status.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({key: report[key] for key in ['registryBuildingRecords', 'finalAcceptedBuildings', 'workingTreeNativeExteriorGroups', 'workingTreeNativeSourceObjects', 'lastPublishedSnapshot']}))
