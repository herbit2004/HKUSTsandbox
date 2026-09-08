/** Create a flat, georeferenced floor from visibility-filtered official rooms.
 * All x/z coordinates are already local to E844800/N820500; source room Z is y.
 * No invented wall height or room volume is created here.
 */
export function createRoomFloor(THREE, floor, {opacity = 0.9, lines = true} = {}) {
  const group = new THREE.Group();
  group.name = `${floor.buildingName} — ${floor.floorName}`;
  group.userData.floor = floor;
  for (const room of floor.rooms) {
    const shape = new THREE.Shape(room.rings[0].map(([x, z]) => new THREE.Vector2(x, -z)));
    for (const ring of room.rings.slice(1)) {
      shape.holes.push(new THREE.Path(ring.map(([x, z]) => new THREE.Vector2(x, -z))));
    }
    const geometry = new THREE.ShapeGeometry(shape);
    geometry.rotateX(-Math.PI / 2);
    geometry.translate(0, room.heightSourceZ, 0);
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
      color: room.color, transparent: opacity < 1, opacity, side: THREE.DoubleSide,
    }));
    mesh.name = room.name || room.type || room.id;
    mesh.userData.room = room;
    mesh.userData.floorId = floor.id;
    mesh.userData.interpretation = 'Official room boundary polygon; zero thickness; not a surveyed wall volume.';
    group.add(mesh);
    if (lines) {
      const vertices = [];
      for (const ring of room.rings) {
        for (let i = 0; i < ring.length - 1; i++) {
          vertices.push(ring[i][0], room.heightSourceZ + 0.015, ring[i][1],
                        ring[i+1][0], room.heightSourceZ + 0.015, ring[i+1][1]);
        }
      }
      const linesGeometry = new THREE.BufferGeometry();
      linesGeometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
      const outline = new THREE.LineSegments(linesGeometry,
        new THREE.LineBasicMaterial({color: 0x31495a, transparent: true, opacity: 0.7}));
      outline.userData.floorId = floor.id;
      outline.userData.roomId = room.id;
      group.add(outline);
    }
  }
  return group;
}
