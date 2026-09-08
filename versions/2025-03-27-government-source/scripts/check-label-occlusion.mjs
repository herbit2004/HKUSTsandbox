import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import * as THREE from 'three';

const project = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const source = fs.readFileSync(project + '/app/label-occlusion.ts', 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports });
const { createBuildingOccluders, markerOccluded } = exports;
const checks = [];
function check(name, run) {
  run();
  checks.push(name);
}
const box = (x0, z0, x1, z1) => [
  [x0, z0],
  [x1, z0],
  [x1, z1],
  [x0, z1],
  [x0, z0],
];
function footprint(id, rings, min = 0, max = 10) {
  return {
    id,
    catalogId: null,
    catalogName: null,
    officialBuildingId: id,
    officialBuildingName: id,
    parts: [{ rings }],
    boundsXZ: { min: [-100, -100], max: [100, 100] },
    minObservedFloorZ: min,
    maxObservedFloorZ: max,
  };
}
const solid = createBuildingOccluders([
  footprint('other', [box(0, 0, 10, 10)]),
]);
check('other building blocks only within observed source height', () => {
  assert.equal(markerOccluded([-5, 5, 5], [15, 5, 5], solid), true);
  assert.equal(markerOccluded([-5, 11, 5], [15, 11, 5], solid), false);
  assert.equal(markerOccluded([-5, -1, 5], [15, -1, 5], solid), false);
});
check('marker own building is excluded', () =>
  assert.equal(markerOccluded([-5, 5, 5], [5, 5, 5], solid, 'other'), false),
);
check('sloping segment checks height where it crosses footprint', () => {
  assert.equal(markerOccluded([-5, 20, 5], [15, -10, 5], solid), true);
  assert.equal(markerOccluded([-5, 35, 5], [15, 5, 5], solid), false);
});
const hole = createBuildingOccluders([
  footprint('courtyard', [box(0, 0, 10, 10), box(2, 2, 8, 8)]),
]);
check('courtyard hole and tangent remain visible', () => {
  assert.equal(markerOccluded([3, 5, 3], [7, 5, 7], hole), false);
  assert.equal(markerOccluded([2, 5, 3], [2, 5, 7], hole), false);
  assert.equal(markerOccluded([-5, 5, 0], [15, 5, 0], solid), false);
  assert.equal(markerOccluded([-5, 5, 5], [5, 5, 5], hole), true);
});
const concave = createBuildingOccluders([
  footprint('u', [
    [
      [0, 0],
      [8, 0],
      [8, 8],
      [6, 8],
      [6, 2],
      [2, 2],
      [2, 8],
      [0, 8],
      [0, 0],
    ],
  ]),
]);
check('concave academic-like recess is not a full AABB wall', () => {
  assert.equal(markerOccluded([4, 5, 9], [4, 5, 3], concave), false);
  assert.equal(markerOccluded([-1, 5, 5], [4, 5, 5], concave), true);
});
check('vertical rays obey holes and actual source interval', () => {
  assert.equal(markerOccluded([5, 15, 5], [5, -1, 5], solid), true);
  assert.equal(markerOccluded([5, 15, 5], [5, -1, 5], hole), false);
  assert.equal(markerOccluded([5, 15, 5], [5, 12, 5], solid), false);
});
check('unknown or zero source height never creates a guessed volume', () => {
  const f = footprint('unknown', [box(0, 0, 1, 1)]);
  delete f.minObservedFloorZ;
  assert.equal(
    createBuildingOccluders([f, footprint('flat', [box(0, 0, 1, 1)], 5, 5)])
      .length,
    0,
  );
});
const multipart = footprint('parts', [box(0, 0, 2, 2)]);
multipart.parts.push({ rings: [box(8, 0, 10, 2)] });
check('separated multipart gap remains open', () =>
  assert.equal(
    markerOccluded([5, 5, -2], [5, 5, 4], createBuildingOccluders([multipart])),
    false,
  ),
);

// Independent oracle: extrude the real source polygons into test-only Three meshes.
// Production code never builds or raycasts these triangle volumes.
const footprints = JSON.parse(
  fs.readFileSync(project + '/public/data/building-footprints.json', 'utf8'),
).footprints;
const actual = createBuildingOccluders(footprints);
const academic = actual.find(
  (b) => b.buildingId === 'b00000000000000000000001',
);
assert.ok(academic);
const oracle = new THREE.Group();
for (const part of academic.parts) {
  const shape = new THREE.Shape(
    part.rings[0].map(([x, z]) => new THREE.Vector2(x, -z)),
  );
  for (const ring of part.rings.slice(1))
    shape.holes.push(
      new THREE.Path(ring.map(([x, z]) => new THREE.Vector2(x, -z))),
    );
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: academic.maxY - academic.minY,
    bevelEnabled: false,
    steps: 1,
  });
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, academic.minY, 0);
  oracle.add(
    new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }),
    ),
  );
}
oracle.updateMatrixWorld(true);
const ray = new THREE.Raycaster();
let matches = 0;
check(
  '160 real Academic footprint rays match independent extruded-triangle oracle',
  () => {
    const cx = (academic.minX + academic.maxX) / 2,
      cz = (academic.minZ + academic.maxZ) / 2,
      radius = Math.hypot(
        academic.maxX - academic.minX,
        academic.maxZ - academic.minZ,
      );
    for (let i = 0; i < 160; i++) {
      const angle = i * 2.399963229728653,
        angle2 = angle + 0.25 + (i % 17) * 0.15;
      const a = [
        cx + Math.cos(angle) * radius,
        academic.minY -
          5 +
          ((i % 23) * (academic.maxY - academic.minY + 10)) / 22,
        cz + Math.sin(angle) * radius,
      ];
      const b = [
        cx + Math.cos(angle2) * radius,
        academic.minY -
          5 +
          (((i * 7) % 23) * (academic.maxY - academic.minY + 10)) / 22,
        cz + Math.sin(angle2) * radius,
      ];
      const direction = new THREE.Vector3(...b).sub(new THREE.Vector3(...a));
      ray.set(new THREE.Vector3(...a), direction.clone().normalize());
      ray.near = 0.0001;
      ray.far = direction.length() - 0.0001;
      const expected = ray.intersectObject(oracle, true).length > 0;
      assert.equal(
        markerOccluded(a, b, [academic]),
        expected,
        'actual ray ' + i,
      );
      matches++;
    }
  },
);
const report = {
  status: 'pass',
  checks: checks.length,
  names: checks,
  sourceFootprints: footprints.length,
  usableSourceHeightVolumes: actual.length,
  actualAcademicOracleRays: matches,
  productionUsesPhotogrammetryRaycasts: false,
  limits:
    'Observed floor volume is a conservative label guard, not surveyed walls/roof, full occlusion or navigation collision.',
};
const reportPath = process.argv[2];
if (reportPath)
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
