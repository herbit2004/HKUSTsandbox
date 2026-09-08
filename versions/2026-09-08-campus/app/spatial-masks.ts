import * as THREE from 'three';
import { assertMaterialSamplerCapacity } from './material-samplers';
import { insideSourceProtection, sourceProtectionFootprintGLSL } from './source-protection-footprint';
import {
  hasMaterial,
  type PolygonPart,
  type MaterialShader,
} from './source-types';

type MaskSlot = {
  texture: { value: THREE.Texture };
  bounds: { value: THREE.Vector4 };
  enabled: { value: number };
  minY: { value: number };
  maxY: { value: number };
  heightEncoded: { value: number };
  heightClearance: { value: number };
  coreOnly: { value: number };
};
export const replacementSlots = [
  'replacement',
  ...Array.from({ length: 7 }, (_, i) => `replacement${i + 2}`),
];
export const surfaceSlots = ['surface', 'surface2'] as const;
// These are CPU-side staging owners for rebuilding the single sampled R8
// partialCoverage union. They are not shader samplers. Keep enough owners for
// every source partition a wide campus view can retain; the previous limit of
// 16 silently starved later partitions even when texture budget remained.
export const partialSlots = Array.from({ length: 96 }, (_, i) =>
  i === 0 ? 'meshPartial' : `meshPartial${i + 1}`,
);
export type SpatialMaskRole =
  | 'terrain'
  | 'baseline'
  | 'photogrammetry'
  | 'exterior'
  | 'supplement';
/** Shader and CPU picking share exactly the same enabled mask roles. */
export function spatialMaskNames(role: SpatialMaskRole): string[] {
  if (role === 'terrain')
    return [
      'coverage',
      ...replacementSlots,
      'interiorTerrain',
      'currentForms',
      'groundReference',
      ...surfaceSlots,
    ];
  if (role === 'baseline')
    return [
      ...replacementSlots,
      'opening',
      'partialCoverage',
      'currentForms',
      'groundReference',
      'sourceProtection',
      ...surfaceSlots,
    ];
  if (role === 'photogrammetry')
    return [...replacementSlots, 'opening', 'currentForms', 'groundReference', 'sourceProtection', ...surfaceSlots];
  if (role === 'supplement')
    return ['opening', 'partialCoverage', 'currentForms', ...surfaceSlots];
  return ['opening', ...surfaceSlots];
}
export class SpatialMasks {
  slots: Record<string, MaskSlot> = {};
  private sourceProtectionScope: THREE.Box3 | null = null;
  private sourceProtectionParts: PolygonPart[] = [];
  private sourceProtectionPolygonShader = '';
  private sourceProtectionPolygonKey = '';
  private maxFragmentTextures = Infinity;
  private materialDemand = new Map<THREE.Material, { names: string[]; required: number }>();
  private partialPixels = new WeakMap<
    object,
    {
      data: Uint8Array;
      width: number;
      height: number;
    }
  >();
  private partialUnion = {
    width: 1,
    height: 1,
    bytes: 1,
    metersPerPixel: 0,
    enabledSlots: 0,
  };
  constructor() {
    for (const name of [
      'coverage',
      ...replacementSlots,
      'opening',
      'interiorTerrain',
      ...partialSlots,
      'partialCoverage',
      'currentForms',
      'groundReference',
      'sourceProtection',
      ...surfaceSlots,
    ]) {
      const texture = new THREE.DataTexture(
        new Uint8Array([0, 0, 0, 255]),
        1,
        1,
      );
      texture.needsUpdate = true;
      this.slots[name] = {
        texture: { value: texture },
        bounds: { value: new THREE.Vector4(0, 0, 1, 1) },
        enabled: { value: 0 },
        minY: { value: -100000 },
        maxY: { value: 100000 },
        heightEncoded: { value: 0 },
        heightClearance: { value: 0 },
        coreOnly: { value: 0 },
      };
    }
  }
  /** Configured before any photographic source is admitted. The extra sampler
   * exists only on source meshes intersecting this checked, narrow support area. */
  configureSourceProtection(bounds: number[], maxFragmentTextures: number, parts?: PolygonPart[]) {
    if (this.materialDemand.size) throw new Error('Source protection scope must be configured before source materials');
    if (!Number.isInteger(maxFragmentTextures) || maxFragmentTextures < 1)
      throw new Error('Renderer fragment texture capability unavailable');
    this.maxFragmentTextures = maxFragmentTextures;
    this.sourceProtectionParts = parts ?? [{ rings: [[[bounds[0], bounds[1]], [bounds[2], bounds[1]], [bounds[2], bounds[3]], [bounds[0], bounds[3]], [bounds[0], bounds[1]]]] }];
    if (!this.sourceProtectionParts.length) throw new Error('Missing source protection polygon');
    this.sourceProtectionPolygonShader = sourceProtectionFootprintGLSL(this.sourceProtectionParts);
    this.sourceProtectionPolygonKey = JSON.stringify(this.sourceProtectionParts);
    this.sourceProtectionScope = new THREE.Box3(
      new THREE.Vector3(bounds[0], 1, bounds[1]),
      new THREE.Vector3(bounds[2], 254, bounds[3]),
    );
  }
  insideSourceProtection(x: number, z: number) {
    return insideSourceProtection(x, z, this.sourceProtectionParts);
  }
  setSourceProtection(texture: THREE.DataTexture, bounds: number[], bandMeters: number) {
    // A mapped baseline intersecting this area needs 15 mask samplers + map.
    // Check the future baseline path even if its asynchronous load has not run.
    if (this.maxFragmentTextures < 16)
      throw new Error('Hall source protection needs 16 fragment texture units; keep original source without Hall deletion');
    for (const [material, demand] of this.materialDemand)
      assertMaterialSamplerCapacity(material, demand.names.length, this.maxFragmentTextures,
        material.userData.seaEdgeBlend ? 1 : 0);
    this.set('sourceProtection', texture, bounds);
    this.slots.sourceProtection.heightClearance.value = bandMeters;
  }
  samplerStats() {
    return {
      maxFragmentTextures: Number.isFinite(this.maxFragmentTextures) ? this.maxFragmentTextures : null,
      maximumMaterialDemand: Math.max(0, ...[...this.materialDemand.values()].map(v => v.required)),
      protectedSourceMaterials: [...this.materialDemand.values()].filter(v => v.names.includes('sourceProtection')).length,
      sourceProtectionEnabled: !!this.slots.sourceProtection.enabled.value,
    };
  }
  set(name: string, texture: THREE.Texture, bounds: number[], minY = -100000) {
    const slot = this.slots[name];
    const old = {
      texture: slot.texture.value,
      bounds: slot.bounds.value.clone(),
      enabled: slot.enabled.value,
      minY: slot.minY.value,
      heightEncoded: slot.heightEncoded.value,
      coreOnly: slot.coreOnly.value,
    };
    texture.flipY = false;
    texture.colorSpace = THREE.NoColorSpace;
    texture.minFilter = texture.magFilter = THREE.NearestFilter;
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    slot.texture.value = texture;
    slot.bounds.value.fromArray(bounds);
    slot.enabled.value = 1;
    slot.minY.value = minY;
    slot.heightEncoded.value = 0;
    slot.coreOnly.value = 0;
    if (partialSlots.some((partial) => partial === name)) {
      try {
        this.rebuildPartialCoverage();
      } catch (error) {
        slot.texture.value = old.texture;
        slot.bounds.value.copy(old.bounds);
        slot.enabled.value = old.enabled;
        slot.minY.value = old.minY;
        slot.heightEncoded.value = old.heightEncoded;
        slot.coreOnly.value = old.coreOnly;
        texture.dispose();
        throw error;
      }
    }
    old.texture.dispose();
  }
  /** R is coverage; G/B preserve source ground Y as G*255+B*255/256. */
  setSurface(
    name: (typeof surfaceSlots)[number],
    texture: THREE.Texture,
    bounds: number[],
    clearanceMeters: number,
  ) {
    this.set(name, texture, bounds);
    this.slots[name].heightEncoded.value = 1;
    this.slots[name].heightClearance.value = clearanceMeters;
  }
  /** Preserve only source photograph ground already verified against DTM. */
  setGroundReference(texture: THREE.Texture, bounds: number[], bandMeters = 1) {
    this.set('groundReference', texture, bounds);
    this.slots.groundReference.heightClearance.value = bandMeters;
  }
  /** R is full baseline coverage; G is verified individual building coverage. */
  setPhotogrammetryCore(name: string, enabled: boolean) {
    this.slots[name].coreOnly.value = enabled ? 1 : 0;
  }
  enable(name: string, value: boolean) {
    const slot = this.slots[name];
    const previous = slot.enabled.value;
    if (previous === (value ? 1 : 0)) return;
    slot.enabled.value = value ? 1 : 0;
    if (partialSlots.some((partial) => partial === name)) {
      try {
        this.rebuildPartialCoverage();
      } catch (error) {
        slot.enabled.value = previous;
        throw error;
      }
    }
  }
  /** Extra GPU storage beyond the individual entry-owned mask textures. */
  partialCoverageStats() {
    return { ...this.partialUnion };
  }
  private readPartialPixels(texture: THREE.Texture) {
    const source = texture.image as {
      width: number;
      height: number;
      data?: ArrayLike<number>;
    };
    const cached = this.partialPixels.get(source);
    if (cached) return cached;
    const { width, height } = source;
    if (
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width < 1 ||
      height < 1
    )
      throw new Error('Partial mask has invalid source dimensions');
    let pixels: ArrayLike<number>;
    let channels: number;
    if (source.data) {
      pixels = source.data;
      channels = pixels.length / (width * height);
    } else {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('Partial mask pixel reader unavailable');
      context.drawImage(source as CanvasImageSource, 0, 0);
      pixels = context.getImageData(0, 0, width, height).data;
      channels = 4;
    }
    const data = new Uint8Array(width * height);
    for (let i = 0; i < data.length; i++)
      data[i] = pixels[i * channels] > 127 ? 255 : 0;
    const result = { data, width, height };
    this.partialPixels.set(source, result);
    return result;
  }
  /** Exact logical OR on the finest input grid: one sampler for four source masks. */
  private rebuildPartialCoverage() {
    const active = partialSlots.flatMap((name) => {
      const slot = this.slots[name];
      if (!slot.enabled.value) return [];
      const pixels = this.readPartialPixels(slot.texture.value);
      if (!pixels.data.some((value) => value > 127)) return [];
      const bounds = slot.bounds.value;
      const resolution = (bounds.z - bounds.x) / pixels.width;
      if (
        resolution <= 0 ||
        Math.abs(resolution - (bounds.w - bounds.y) / pixels.height) > 1e-6
      )
        throw new Error(
          'Partial mask source pixels must form a square world grid',
        );
      return [{ ...pixels, bounds, resolution }];
    });
    if (!active.length) {
      const texture = new THREE.DataTexture(
        new Uint8Array([0]),
        1,
        1,
        THREE.RedFormat,
      );
      this.set('partialCoverage', texture, [0, 0, 1, 1]);
      this.slots.partialCoverage.enabled.value = 0;
      this.partialUnion = {
        width: 1,
        height: 1,
        bytes: 1,
        metersPerPixel: 0,
        enabledSlots: 0,
      };
      return;
    }
    const resolution = Math.min(...active.map((mask) => mask.resolution));
    const minX = Math.min(...active.map((mask) => mask.bounds.x));
    const minZ = Math.min(...active.map((mask) => mask.bounds.y));
    const maxX = Math.max(...active.map((mask) => mask.bounds.z));
    const maxZ = Math.max(...active.map((mask) => mask.bounds.w));
    const width = Math.round((maxX - minX) / resolution);
    const height = Math.round((maxZ - minZ) / resolution);
    // Preserve every source pixel. Reject an oversized union instead of downsampling.
    if (width > 4096 || height > 4096 || width * height > 16 * 1024 * 1024)
      throw new Error(
        'Partial source union exceeds its exact-grid memory limit',
      );
    const aligned = active.map((mask) => {
      const raw = [
        (mask.bounds.x - minX) / resolution,
        (mask.bounds.y - minZ) / resolution,
        mask.resolution / resolution,
      ];
      const [x, z, scale] = raw.map(Math.round);
      if (raw.some((value, i) => Math.abs(value - [x, z, scale][i]) > 1e-6))
        throw new Error(
          'Partial source masks do not share an exact pixel grid',
        );
      return { ...mask, x, z, scale };
    });
    const data = new Uint8Array(width * height);
    for (const mask of aligned)
      for (let row = 0; row < mask.height; row++)
        for (let col = 0; col < mask.width; col++) {
          if (!mask.data[row * mask.width + col]) continue;
          for (let dy = 0; dy < mask.scale; dy++) {
            const start =
              (mask.z + row * mask.scale + dy) * width +
              mask.x +
              col * mask.scale;
            data.fill(255, start, start + mask.scale);
          }
        }
    const texture = new THREE.DataTexture(data, width, height, THREE.RedFormat);
    texture.unpackAlignment = 1;
    this.set('partialCoverage', texture, [minX, minZ, maxX, maxZ]);
    this.partialUnion = {
      width,
      height,
      bytes: data.byteLength,
      metersPerPixel: resolution,
      enabledSlots: active.length,
    };
  }
  async load(name: string, url: string, bounds: number[]) {
    const image = await new THREE.TextureLoader().loadAsync(url);
    this.set(name, image, bounds);
  }
  polygon(
    name: string,
    parts: PolygonPart[],
    raster?: { image: CanvasImageSource; bounds: number[] },
  ) {
    const points = parts.flatMap((p) => p.rings.flat());
    if (!points.length) {
      this.enable(name, false);
      return;
    }
    const xs = points.map((p) => p[0]),
      zs = points.map((p) => p[1]);
    if (raster) {
      xs.push(raster.bounds[0], raster.bounds[2]);
      zs.push(raster.bounds[1], raster.bounds[3]);
    }
    const minX = Math.min(...xs) - 0.2,
      minZ = Math.min(...zs) - 0.2,
      maxX = Math.max(...xs) + 0.2,
      maxZ = Math.max(...zs) + 0.2;
    const canvas = document.createElement('canvas');
    canvas.width = Math.min(2048, Math.max(64, Math.ceil((maxX - minX) * 5)));
    canvas.height = Math.min(2048, Math.max(64, Math.ceil((maxZ - minZ) * 5)));
    const c = canvas.getContext('2d')!;
    c.fillStyle = '#000';
    c.fillRect(0, 0, canvas.width, canvas.height);
    if (raster)
      c.drawImage(
        raster.image,
        ((raster.bounds[0] - minX) / (maxX - minX)) * canvas.width,
        ((raster.bounds[1] - minZ) / (maxZ - minZ)) * canvas.height,
        ((raster.bounds[2] - raster.bounds[0]) / (maxX - minX)) * canvas.width,
        ((raster.bounds[3] - raster.bounds[1]) / (maxZ - minZ)) * canvas.height,
      );
    c.fillStyle = '#fff';
    for (const p of parts) {
      c.beginPath();
      for (const ring of p.rings) {
        ring.forEach((v, i) => {
          const x = ((v[0] - minX) / (maxX - minX)) * canvas.width,
            y = ((v[1] - minZ) / (maxZ - minZ)) * canvas.height;
          if (i) c.lineTo(x, y);
          else c.moveTo(x, y);
        });
        c.closePath();
      }
      c.fill('evenodd');
    }
    this.set(name, new THREE.CanvasTexture(canvas), [minX, minZ, maxX, maxZ]);
  }
  apply(root: THREE.Object3D, role: SpatialMaskRole) {
    root.updateWorldMatrix(true, true);
    const scoped = new Set<THREE.Material>();
    if (this.sourceProtectionScope && this.maxFragmentTextures >= 16 && (role === 'baseline' || role === 'photogrammetry'))
      root.traverse(o => {
        if (!hasMaterial(o) || !(o instanceof THREE.Mesh)) return;
        if (!new THREE.Box3().setFromObject(o).intersectsBox(this.sourceProtectionScope!)) return;
        for (const material of Array.isArray(o.material) ? o.material : [o.material]) scoped.add(material);
      });
    root.traverse((o) => {
      if (!hasMaterial(o)) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m.userData.spatialMask) return;
        const names = spatialMaskNames(role).filter(name => name !== 'sourceProtection' || scoped.has(m));
        const required = assertMaterialSamplerCapacity(m, names.length, this.maxFragmentTextures,
          m.userData.seaEdgeBlend ? 1 : 0);
        this.materialDemand.set(m, { names, required });
        m.addEventListener('dispose', () => this.materialDemand.delete(m));
        m.userData.spatialMask = true;
        m.userData.spatialMaskRole = role;
        m.userData.spatialMaskSamplerCount = names.length;
        m.userData.maxFragmentTextures = this.maxFragmentTextures;
        m.userData.sourceProtectionSampler = scoped.has(m);
        const previous = m.onBeforeCompile.bind(m),
          inheritedKey = m.customProgramCacheKey();
        m.onBeforeCompile = (
          shader: MaterialShader,
          renderer: THREE.WebGLRenderer,
        ) => {
          previous?.(shader, renderer);
          const additional = Object.entries(shader.uniforms).filter(([name, uniform]) =>
            uniform.value instanceof THREE.Texture && !(name in m)).length;
          assertMaterialSamplerCapacity(m, names.length, this.maxFragmentTextures, additional);
          for (const name of names) {
            const s = this.slots[name];
            shader.uniforms['u_' + name] = s.texture;
            shader.uniforms['b_' + name] = s.bounds;
            shader.uniforms['e_' + name] = s.enabled;
            shader.uniforms['y_' + name] = s.minY;
            shader.uniforms['h_' + name] = s.maxY;
            shader.uniforms['d_' + name] = s.heightEncoded;
            shader.uniforms['c_' + name] = s.heightClearance;
            shader.uniforms['k_' + name] = s.coreOnly;
          }

          shader.vertexShader =
            'varying vec3 vCampusWorld;\n' + shader.vertexShader;
          shader.vertexShader = shader.vertexShader.replace(
            '#include <begin_vertex>',
            '#include <begin_vertex>\nvCampusWorld=(modelMatrix*vec4(position,1.0)).xyz;',
          );
          let code = 'varying vec3 vCampusWorld;\n';
          for (const name of names)
            code += `uniform sampler2D u_${name}; uniform vec4 b_${name}; uniform float e_${name}; uniform float y_${name}; uniform float h_${name}; uniform float d_${name}; uniform float c_${name}; uniform float k_${name};\n`;
          if (
            role === 'terrain' ||
            role === 'baseline' ||
            role === 'photogrammetry'
          ) {
            code += `
vec4 campusGroundSample(vec2 positionXZ) {
  if (e_groundReference < 0.5) return vec4(0.0);
  vec2 uv = (positionXZ-b_groundReference.xy)/(b_groundReference.zw-b_groundReference.xy);
  if (any(lessThan(uv,vec2(0.0))) || any(greaterThan(uv,vec2(1.0)))) return vec4(0.0);
  return texture2D(u_groundReference,uv);
}
bool campusPreserveSourceGround(vec3 world) {
  vec4 ground = campusGroundSample(world.xz);
  if (ground.r < 0.5) return false;
  float sourceY = ground.g*255.0 + ground.b*(255.0/256.0);
  vec3 faceNormal = normalize(cross(dFdx(world),dFdy(world)));
  return abs(world.y-sourceY) <= c_groundReference && abs(faceNormal.y) >= 0.6;
}
`;
          }
          if (names.includes('sourceProtection')) code += this.sourceProtectionPolygonShader + `
bool campusPreserveCurrentFormSource(vec3 world) {
  if (e_sourceProtection < 0.5) return false;
  vec2 uv=(world.xz-b_sourceProtection.xy)/(b_sourceProtection.zw-b_sourceProtection.xy);
  if(any(lessThan(uv,vec2(0.0)))||any(greaterThan(uv,vec2(1.0)))) return false;
  vec4 p=texture2D(u_sourceProtection,uv)*255.0;
  bool ground=p.r>0.5 && abs(world.y-p.r-p.g/256.0)<=c_sourceProtection
    && abs(normalize(cross(dFdx(world),dFdy(world))).y)>=0.6;
  bool structure=p.b<254.5 && p.a<254.5 && world.y>=p.b && world.y<=p.a && campusInsideSourceProtection(world.xz);
  return ground || structure;
}
`;
          shader.fragmentShader = code + shader.fragmentShader;
          let discard = '';
          for (const name of names) {
            if (name === 'groundReference' || name === 'sourceProtection') continue;
            if (role === 'terrain' && replacementSlots.includes(name)) continue;
            const fallback =
              role === 'terrain' && name === 'coverage'
                ? `&&!((${replacementSlots.map((n) => `(e_${n}>0.5&&all(greaterThanEqual(vCampusWorld.xz,b_${n}.xy))&&all(lessThanEqual(vCampusWorld.xz,b_${n}.zw))&&texture2D(u_${n},(vCampusWorld.xz-b_${n}.xy)/(b_${n}.zw-b_${n}.xy)).r>0.5)`).join('||')}||(e_currentForms>0.5&&all(greaterThanEqual(vCampusWorld.xz,b_currentForms.xy))&&all(lessThanEqual(vCampusWorld.xz,b_currentForms.zw))&&all(greaterThan(texture2D(u_currentForms,(vCampusWorld.xz-b_currentForms.xy)/(b_currentForms.zw-b_currentForms.xy)).rgb,vec3(0.999)))))&&! (campusGroundSample(vCampusWorld.xz).r>0.5))`
                : '';
            const retainGround =
              name === 'currentForms' && (role === 'baseline' || role === 'photogrammetry')
                ? '&&!campusPreserveSourceGround(vCampusWorld)' + (names.includes('sourceProtection') ? '&&!campusPreserveCurrentFormSource(vCampusWorld)' : '') :
              (role === 'baseline' || role === 'photogrammetry') &&
              replacementSlots.includes(name)
                ? '&&!campusPreserveSourceGround(vCampusWorld)'
                : '';
            const channel =
              role === 'photogrammetry' && replacementSlots.includes(name)
                ? `mix(groundMask.r,groundMask.g,k_${name})`
                : 'groundMask.r';
            const pixelFloor = name === 'currentForms' ? '&&(groundMask.a>=0.999||vCampusWorld.y>=groundMask.a*255.0)' : '';
            discard += `if(e_${name}>0.5&&vCampusWorld.y>=y_${name}&&vCampusWorld.y<=h_${name}${fallback}${retainGround}){vec2 uv=(vCampusWorld.xz-b_${name}.xy)/(b_${name}.zw-b_${name}.xy);if(all(greaterThanEqual(uv,vec2(0.0)))&&all(lessThanEqual(uv,vec2(1.0)))){vec4 groundMask=texture2D(u_${name},uv);if(${channel}>0.5${pixelFloor}&&(d_${name}<0.5||(vCampusWorld.y<=groundMask.g*255.0+groundMask.b*(255.0/256.0)+c_${name}&&(d_${name}>1.5||abs(normalize(cross(dFdx(vCampusWorld),dFdy(vCampusWorld))).y)>=0.6))))discard;}}\n`;
          }
          shader.fragmentShader = shader.fragmentShader.replace(
            '#include <clipping_planes_fragment>',
            '#include <clipping_planes_fragment>\n' + discard,
          );
        };
        m.customProgramCacheKey = () =>
          `campus-mask-v13-${role}-${scoped.has(m) ? this.sourceProtectionPolygonKey : 'ordinary'}|${inheritedKey}`;
        m.needsUpdate = true;
      }
    });
  }
  dispose() {
    for (const s of Object.values(this.slots)) s.texture.value.dispose();
  }
}
