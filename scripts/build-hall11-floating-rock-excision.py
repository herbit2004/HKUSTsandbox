#!/usr/bin/env python3
"""Build an exact topology correction for the Hall XI floating white rock.

The candidate set comes from the settled second-angle runtime screenshot. Ray
hits are expanded to complete same-primitive vertex-connected components. The
large rear/floor closures are retained. The two 129-face boundary planes are
included after the first runtime candidate left their green suspended sliver
visible at the exact same pixels with the complete current facade behind it.
"""
from __future__ import annotations

import json
from pathlib import Path

from glb_source_correction import rewrite, sha

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall11-second-blob-topology-u69.json"
SOURCES = json.loads(Path("/tmp/hkust-ivillage-rebuild-source/sources.json").read_text())["sources"]
OUT = ROOT / "public/models/hires/source-corrections/hall11-floating-rock-v2"
ID = "hall11-floating-rock-v2"

SELECTED = {
    19: {f"tile19-mesh0-primitive0-fullComponent{i}" for i in range(14)},
    71: {f"tile71-mesh0-primitive0-fullComponent{i}" for i in range(12)},
}
EXPECTED_FACES = {19: 389, 71: 380}
RETAINED = {
    "tile71-mesh0-primitive0-fullComponent12",
    "tile72-mesh0-primitive0-fullComponent0",
}


def main():
    topology = json.loads(REPORT.read_text())
    by_tile = {int(tile["sourceTileIndex"]): tile for tile in topology["tiles"]}
    outputs = []
    for tile_index, component_ids in SELECTED.items():
        tile = by_tile[tile_index]
        components = {
            component["componentId"]: component
            for component in tile["fullPrimitiveVertexConnectedComponents"]
        }
        assert component_ids <= components.keys()
        faces = set()
        selected_components = []
        for component_id in sorted(component_ids):
            component = components[component_id]
            assert component["sharesVertexWithRetainedFaces"] is False
            assert component["visibleUnremovedSeedFaces"]
            current_faces = set(map(int, component["faces"]))
            assert not (faces & current_faces)
            faces.update(current_faces)
            selected_components.append({
                "componentId": component_id,
                "faces": int(component["faceCount"]),
                "seedFaces": len(component["visibleUnremovedSeedFaces"]),
                "worldBounds": component["worldBounds"],
            })
        assert len(faces) == EXPECTED_FACES[tile_index], (tile_index, len(faces))

        source_meta = SOURCES[tile_index]
        source = Path(source_meta["localPath"])
        assert source.exists() and sha(source) == source_meta["sha256"]
        relative = source.relative_to(ROOT)
        output = OUT / relative.parent.name / relative.name.replace(".glb", f".{ID}.glb")
        result = rewrite(source, faces, output)
        result.update({
            "sourceTileIndex": tile_index,
            "sourceId": source_meta["id"],
            "sourceUrl": str(relative).replace("\\", "/"),
            "correctedUrl": str(output.relative_to(ROOT)).replace("\\", "/"),
            "correctedSha256": result["derivedSha256"],
            "removedSourceTriangleIndices": sorted(faces),
            "selectedComponents": selected_components,
            "upstreamSourceCorrection": source_meta.get("sourceCorrection"),
        })
        outputs.append(result)

    evidence = {
        "status": "runtime-ray-seeded-topology-candidate-not-registered",
        "id": ID,
        "runtimeScreenshot": "docs/screenshots/v4/u69-hall11-remnant-candidate/second-angle.png",
        "rayEvidence": "/tmp/hall11-second-blob-rays.json",
        "topologyEvidence": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        "sourceTiles": outputs,
        "removedTriangles": sum(EXPECTED_FACES.values()),
        "retainedComponentIds": sorted(RETAINED),
        "selection": "Only complete vertex-connected closures hit by the visible white-rock pixels in the settled second-angle screenshot. The two thin 129-face boundary planes were added after the first candidate left their suspended green sliver visible at the same pixels.",
        "preservation": "Tile 71's 1,234-face rear component, all tile 72 faces, terrain, roads, canopy, corridors, current-form meshes and every other source face are retained.",
        "limitations": [
            "This candidate must pass the same-pose and second-angle runtime comparison before registration in the published preview.",
            "The selection is screenshot and topology bound; it is not a reusable height, bounding-box or tile-wide deletion rule.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": evidence["status"], "removedTriangles": evidence["removedTriangles"], "outputs": [x["correctedUrl"] for x in outputs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
