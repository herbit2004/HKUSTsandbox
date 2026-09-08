#!/usr/bin/env python3
"""Build the exact Hall XIII old-source boundary-remnant correction.

The removed set is one complete source vertex-connected component.  It is
accepted only when the checked neighborhood audit proves that the component is
inside/intersecting the Hall XIII current-form envelope, has no protected
ground or prior non-building witness, is almost completely hidden by the
current-form mask, and the remaining exposed faces are the mask-edge leak seen
in the settled Hall XI overview.  No height/AABB/colour rule is applied to any
other source geometry.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from glb_source_correction import rewrite, sha
from hkust_source_geometry import geometry


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hall-x-xiii-neighborhood-remnant-audit-u70.json"
SOURCES = Path("/tmp/hkust-ivillage-rebuild-source/sources.json")
OUT = ROOT / "public/models/hires/source-corrections/ivillage-hall13-boundary-remnant-v4"
ID = "ivillage-hall13-boundary-remnant-v4"
COMPONENT_ID = "tile107-component436"
SOURCE_TILE_INDEX = 107
EXPECTED_FACES = 1310


def main() -> None:
    audit = json.loads(REPORT.read_text())
    component = next(row for row in audit["components"] if row["id"] == COMPONENT_ID)
    assert component["sourceTileIndex"] == SOURCE_TILE_INDEX
    assert component["sourceId"].endswith("Tile_303_144_L21_002021")
    assert component["triangleCount"] == EXPECTED_FACES
    assert component["scopedTriangleCount"] == EXPECTED_FACES
    assert component["officialEnvelopeIntersections"] == ["ug-hall-13"]
    assert component["knownGuardTriangleCount"] == 0
    assert component["sourceProtectionGroundWitnessCount"] == 0
    assert component["alreadyCorrectedTriangleCount"] == 0
    assert component["currentFormVisibleTriangleCount"] == 3
    assert component["currentFormHiddenAreaFraction"] >= 0.997
    assert component["areaWeightedAboveDtmFraction"] >= 0.86
    assert component["areaWeightedDtmCompatibleFraction"] <= 0.001

    meta = json.loads(SOURCES.read_text())["sources"][SOURCE_TILE_INDEX]
    assert meta["id"] == component["sourceId"]
    source = Path(meta["localPath"])
    assert source.exists() and sha(source) == meta["sha256"]
    removed = set(map(int, component["scopedTriangleIndices"]))
    assert len(removed) == EXPECTED_FACES

    relative = source.relative_to(ROOT)
    output = OUT / relative.parent.name / source.name.replace(".glb", f".{ID}.glb")
    result = rewrite(source, removed, output)

    matrix = np.asarray(meta["matrix"], dtype=float).reshape(4, 4, order="F")
    original_triangles, _ = geometry(source, matrix)
    corrected_triangles, _ = geometry(output, matrix)
    expected = np.delete(original_triangles, sorted(removed), axis=0)
    assert np.array_equal(expected, corrected_triangles)

    evidence = {
        "status": "exact-component-candidate-not-registered",
        "id": ID,
        "componentId": COMPONENT_ID,
        "sourceAudit": str(REPORT.relative_to(ROOT)).replace("\\", "/"),
        "runtimePose": "docs/source-evidence-v4/ivillage-remnants/hall-xiii-east-standard-pose-u70.json",
        "runtimeRayAudit": "docs/source-evidence-v4/ivillage-remnants/hall-xiii-east-standard-rays-u70.json",
        "sourceTiles": [{
            **result,
            "sourceTileIndex": SOURCE_TILE_INDEX,
            "sourceId": meta["id"],
            "sourceUrl": str(relative).replace("\\", "/"),
            "correctedUrl": str(output.relative_to(ROOT)).replace("\\", "/"),
            "correctedSha256": result["derivedSha256"],
            "removedSourceTriangleIndices": sorted(removed),
            "matrix": meta["matrix"],
            "sourceBounds": meta["bounds"],
            "removedWorldBounds": component["bounds"],
            "upstreamSourceCorrection": meta.get("sourceCorrection"),
        }],
        "removedTriangles": EXPECTED_FACES,
        "selection": (
            "One complete source vertex-connected component at the Hall XIII replacement boundary. "
            "The component is 99.742% hidden by the current-form mask; its three exposed faces are the "
            "same boundary leak, while the component has zero protected-ground and zero prior guard faces."
        ),
        "preservation": (
            "Every other source component, DTM-compatible surface, protected ground witness, road, canopy, "
            "corridor and current-form triangle is retained byte-for-byte."
        ),
        "checks": {
            "retainedWorldTrianglesExact": True,
            "componentClosureComplete": True,
            "broadSpatialRuleUsed": False,
            "sourcePayloadSha256": meta["sha256"],
        },
        "limitations": [
            "The correction addresses this positively identified Hall XIII mask-edge source component only.",
            "Runtime publication requires independent build checks and multi-angle browser comparison."
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "status": evidence["status"],
        "sourceId": meta["id"],
        "removedTriangles": EXPECTED_FACES,
        "retainedTriangles": len(corrected_triangles),
        "output": evidence["sourceTiles"][0]["correctedUrl"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
