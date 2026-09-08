#!/usr/bin/env python3
"""Build the unregistered U71 Hall XI hanging-remnant GLB candidates.

The selection is read from the SHA-bound U71 audit.  It contains only the
seven exact components already covered by the established Hall XI ray and
source-correction provenance: 258 high faces and 10 fine faces.  This script
does not update any runtime manifest, mask, GOAL, or published artifact.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

from glb_source_correction import rewrite, sha
from hkust_source_geometry import geometry


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/source-evidence-v4/ivillage-remnants/hires-remnant-audit-u71.json"
MANIFEST = ROOT / "public/models/hires/manifest.json"
OUT = ROOT / "public/models/hires/source-corrections/hall11-hanging-remnants-u71"
ID = "hall11-hanging-remnants-u71"

EXPECTED = {
    "12-NW-11A/12-NW-11A-3/Tile_302_143_L19_0033": {
        "level": "high",
        "sha256": "817b8488ce4877b618868d003777e39f7fc7c5e867b47c0df2a01f326008d5f3",
        "componentOrdinals": [4, 5, 8],
        "removedTriangles": 258,
        "retainedTriangles": 15615,
        "derivedSha256": "c620ccdbf6050122db28cde075938daac05c890b1f848818fca9070ad2f93c63",
    },
    "12-NW-11A/12-NW-11A-3/Tile_302_143_L20_00333": {
        "level": "fine",
        "sha256": "710ac3a1b6160b1c6aa8307ab3ffe18ca0bd45646c2fb552b7fd2f5a9a6c7866",
        "componentOrdinals": [3, 4, 5, 6],
        "removedTriangles": 10,
        "retainedTriangles": 8305,
        "derivedSha256": "9f9036e07dfe3bb4c9565f9327de0289f5950ed1e01ade34e97f739e3b6acc29",
    },
}


def connected_components(triangles: np.ndarray) -> list[list[int]]:
    """Return the audit's 1e-6 m shared-position component ordering."""
    count = len(triangles)
    quantized = np.rint(triangles / 1e-6).astype(np.int64).reshape(-1, 3)
    owners = np.repeat(np.arange(count), 3)
    order = np.lexsort((quantized[:, 2], quantized[:, 1], quantized[:, 0]))
    quantized = quantized[order]
    owners = owners[order]
    parent = np.arange(count, dtype=np.int32)
    size = np.ones(count, dtype=np.int32)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    start = 0
    while start < len(quantized):
        end = start + 1
        while end < len(quantized) and np.array_equal(quantized[end], quantized[start]):
            end += 1
        root = find(int(owners[start]))
        for owner in owners[start + 1 : end]:
            other = find(int(owner))
            if other == root:
                continue
            if size[root] < size[other]:
                root, other = other, root
            parent[other] = root
            size[root] += size[other]
        start = end

    roots = np.array([find(index) for index in range(count)])
    _, labels = np.unique(roots, return_inverse=True)
    return [np.flatnonzero(labels == index).tolist() for index in range(int(labels.max()) + 1)]


def manifest_tiles(manifest: dict) -> dict[str, tuple[str, dict]]:
    result: dict[str, tuple[str, dict]] = {}
    for patch in manifest["patches"]:
        for level in ("high", "fine"):
            for tile in patch["levels"][level]["tiles"]:
                if tile["id"] not in EXPECTED:
                    continue
                assert tile["id"] not in result, f"duplicate current tile {tile['id']}"
                result[tile["id"]] = (level, tile)
    assert result.keys() == EXPECTED.keys()
    return result


def main() -> None:
    audit = json.loads(AUDIT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    assert audit["status"] == "read-only-audit-complete-no-assets-modified"
    assert audit["conclusion"]["exactCandidateComponents"] == 7

    audited: dict[tuple[str, int], dict] = {}
    for group in audit["exactCorrectionCandidates"]:
        assert group["confidence"] == "high"
        assert group["classification"] in {
            "exact-high-frontier-correction-candidate",
            "exact-fine-frontier-correction-candidate",
        }
        for component in group["components"]:
            key = (component["tileId"], int(component["componentOrdinal"]))
            assert key not in audited
            audited[key] = component

    expected_keys = {
        (tile_id, ordinal)
        for tile_id, contract in EXPECTED.items()
        for ordinal in contract["componentOrdinals"]
    }
    assert audited.keys() == expected_keys, "U71 exact candidate set changed"

    tiles = manifest_tiles(manifest)
    outputs = []
    for tile_id, contract in EXPECTED.items():
        level, meta = tiles[tile_id]
        assert level == contract["level"]
        assert meta["sha256"] == contract["sha256"]
        source = ROOT / "public/models/hires" / meta["url"]
        assert source.is_file()
        assert sha(source) == contract["sha256"]

        selected = []
        face_union: set[int] = set()
        for ordinal in contract["componentOrdinals"]:
            component = audited[(tile_id, ordinal)]
            assert component["sha256"] == contract["sha256"]
            assert component["sourceB3dmSha256"] == meta["sourceB3dmSha256"]
            assert component["faceCount"] == len(component["faceOrdinals"])
            assert component["terrainContactWitnessCountAtOrBelow1m"] == 0
            assert component["currentFormVisibleWitnessFraction"] == 1.0
            faces = set(map(int, component["faceOrdinals"]))
            assert len(faces) == component["faceCount"]
            assert not face_union.intersection(faces)
            face_union.update(faces)
            selected.append({
                "componentOrdinal": ordinal,
                "faceCount": component["faceCount"],
                "faceOrdinals": sorted(faces),
                "areaSquareMeters": component["areaSquareMeters"],
                "bounds": component["bounds"],
                "dtmGapMetersAllVerticesAndCentroids": component["dtmGapMetersAllVerticesAndCentroids"],
            })
        assert len(face_union) == contract["removedTriangles"]

        matrix = np.asarray(meta["matrix"], dtype=float).reshape(4, 4, order="F")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            original_triangles, _ = geometry(source, matrix)
        assert np.isfinite(original_triangles).all()
        components = connected_components(original_triangles)
        for component in selected:
            assert component["componentOrdinal"] < len(components)
            assert components[component["componentOrdinal"]] == component["faceOrdinals"]

        output = OUT / level / source.name.replace(".glb", f".{ID}.glb")
        result = rewrite(source, face_union, output)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            corrected_triangles, _ = geometry(output, matrix)
        expected_triangles = np.delete(original_triangles, sorted(face_union), axis=0)
        assert np.array_equal(expected_triangles, corrected_triangles)
        assert result["sourceSha256"] == contract["sha256"]
        assert result["removedTriangles"] == contract["removedTriangles"]
        assert result["sourceTriangles"] == len(original_triangles)
        assert len(corrected_triangles) == contract["retainedTriangles"]
        assert len(corrected_triangles) == len(original_triangles) - len(face_union)
        assert sha(output) == result["derivedSha256"]
        assert result["derivedSha256"] == contract["derivedSha256"]

        outputs.append({
            **result,
            "level": level,
            "sourceId": tile_id,
            "sourceUrl": str(source.relative_to(ROOT)).replace("\\", "/"),
            "sourceB3dmSha256": meta["sourceB3dmSha256"],
            "correctedUrl": str(output.relative_to(ROOT)).replace("\\", "/"),
            "correctedSha256": result["derivedSha256"],
            "retainedTriangles": len(corrected_triangles),
            "removedSourceTriangleIndices": sorted(face_union),
            "selectedComponents": selected,
            "matrix": meta["matrix"],
            "sourceBounds": meta["bounds"],
            "predecessorSourceCorrection": meta.get("sourceCorrection"),
        })

    assert sum(item["removedTriangles"] for item in outputs) == 268
    assert {item["level"]: item["removedTriangles"] for item in outputs} == {
        "high": 258,
        "fine": 10,
    }
    evidence = {
        "status": "exact-component-candidate-not-registered",
        "id": ID,
        "sourceAudit": str(AUDIT.relative_to(ROOT)).replace("\\", "/"),
        "sourceAuditSha256": sha(AUDIT),
        "sourceManifest": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "sourceManifestSha256": sha(MANIFEST),
        "rayAndPredecessorEvidence": [
            "docs/source-evidence-v4/ivillage-remnants/hall11-second-blob-topology-u69.json",
            "public/models/hires/source-corrections/hall11-floating-rock-v2/evidence.json",
            "public/models/hires/partial-ug10/fine-fragment-correction-evidence.json",
        ],
        "sourceTiles": outputs,
        "removedTriangles": 268,
        "removedTrianglesByLevel": {"high": 258, "fine": 10},
        "selection": (
            "Only U71 exactCorrectionCandidates in Hall XI's already ray-confirmed hanging-remnant "
            "volumes: current high component ordinals 4, 5 and 8, plus current fine component "
            "ordinals 3 through 6."
        ),
        "preservation": (
            "Every other high/fine face is retained in original triangle order. The current fine "
            "asset's complete hall11-floating-rock-v2 predecessor sourceCorrection chain is retained "
            "as provenance; no runtime manifest or mask is changed."
        ),
        "checks": {
            "inputAssetSha256Exact": True,
            "auditCandidateSetExact": True,
            "faceUnionDisjointAndExact": True,
            "componentClosureRecomputedExact": True,
            "retainedWorldTrianglesExact": True,
            "outputTriangleCountsExact": True,
            "outputSha256ExpectedAndRecomputedExact": True,
            "runtimeRegistrationPerformed": False,
        },
        "limitations": [
            "These GLBs are candidate artifacts and are not referenced by the runtime manifest.",
            "Registration, build, browser owner-ray validation, and publication remain separate work.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    evidence_path = OUT / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    assert json.loads(evidence_path.read_text())["status"] == "exact-component-candidate-not-registered"
    print(json.dumps({
        "status": evidence["status"],
        "removedTriangles": evidence["removedTriangles"],
        "outputs": [{
            "level": item["level"],
            "sourceTriangles": item["sourceTriangles"],
            "removedTriangles": item["removedTriangles"],
            "retainedTriangles": item["retainedTriangles"],
            "derivedSha256": item["derivedSha256"],
            "bytes": item["bytes"],
            "correctedUrl": item["correctedUrl"],
        } for item in outputs],
        "evidence": str(evidence_path.relative_to(ROOT)).replace("\\", "/"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
