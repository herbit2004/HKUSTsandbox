#!/usr/bin/env python3
"""Build the close-view Hall XI lower floating-fragment correction."""
from __future__ import annotations

import json
from pathlib import Path

from glb_source_correction import rewrite, sha

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall11-lower-floaters-topology-u69.json"
SOURCES = json.loads(Path("/tmp/hkust-ivillage-rebuild-source/sources.json").read_text())["sources"]
OUT = ROOT / "public/models/hires/source-corrections/hall11-lower-floaters-v3"
ID = "hall11-lower-floaters-v3"
SELECTED = {
    33: {"tile33-mesh0-primitive0-fullComponent0", "tile33-mesh0-primitive0-fullComponent1"},
    37: {"tile37-mesh0-primitive0-fullComponent0"},
    47: {"tile47-mesh0-primitive0-fullComponent11"},
}
EXPECTED = {33: 1344, 37: 42, 47: 1078}


def components_by_tile(report):
    result = {}
    for roi in report["rois"]:
        for tile in roi["tiles"]:
            index = int(tile["sourceTileIndex"])
            result[index] = {
                component["componentId"]: component
                for component in tile["completeVertexConnectedComponents"]
            }
    return result


def main():
    topology = json.loads(REPORT.read_text())
    components = components_by_tile(topology)
    outputs = []
    for tile_index, component_ids in SELECTED.items():
        faces = set()
        selected = []
        for component_id in sorted(component_ids):
            component = components[tile_index][component_id]
            assert component["sharesVertexWithExternalFaces"] is False
            current = set(map(int, component["faces"]))
            assert not (faces & current)
            faces.update(current)
            selected.append({
                "componentId": component_id,
                "faces": component["faceCount"],
                "seedHits": component["seedHitCount"],
                "seedHitPixelBounds": component["seedHitPixelBounds"],
                "seedDistanceRange": [component["nearestSeedDistance"], component["farthestSeedDistance"]],
                "worldBounds": component["worldBounds"],
            })
        assert len(faces) == EXPECTED[tile_index], (tile_index, len(faces))
        meta = SOURCES[tile_index]
        source = Path(meta["localPath"])
        assert source.exists() and sha(source) == meta["sha256"]
        relative = source.relative_to(ROOT)
        output = OUT / relative.parent.name / relative.name.replace(".glb", f".{ID}.glb")
        result = rewrite(source, faces, output)
        result.update({
            "sourceTileIndex": tile_index,
            "sourceId": meta["id"],
            "sourceUrl": str(relative).replace("\\", "/"),
            "correctedUrl": str(output.relative_to(ROOT)).replace("\\", "/"),
            "correctedSha256": result["derivedSha256"],
            "removedSourceTriangleIndices": sorted(faces),
            "selectedComponents": selected,
            "upstreamSourceCorrection": meta.get("sourceCorrection"),
        })
        outputs.append(result)
    evidence = {
        "status": "runtime-close-view-topology-candidate-not-registered",
        "id": ID,
        "runtimeScreenshot": "docs/screenshots/v4/u69-hall11-remnant-candidate/close.png",
        "topologyEvidence": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        "sourceTiles": outputs,
        "removedTriangles": sum(EXPECTED.values()),
        "selection": "Complete isolated source closures hit by the visible cyan sliver (tiles 33/37) and the dominant deep-blue column (tile 47 component 11).",
        "preservation": "Farther tile 35 terrain/structure, the twelve other tile 47 depth-strata components, every current-form mesh, roads, corridors, canopies and all other source faces are retained for candidate comparison.",
        "limitations": [
            "This candidate must pass the settled close view and rotated runtime recheck before publication.",
            "The selection is tied to exact screenshot rays and connected topology; it is not a broad spatial deletion rule.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": evidence["status"], "removedTriangles": evidence["removedTriangles"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
