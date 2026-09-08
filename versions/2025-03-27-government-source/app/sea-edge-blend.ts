// Must retain the existing surface-discard shader hook.
import * as THREE from "three";
import { isMesh, type MaterialShader } from "./source-types";
import { assertMaterialSamplerCapacity } from './material-samplers';

export function applySeaEdgeBlend(
  root: THREE.Object3D,
  texture: THREE.Texture,
  bounds: [number, number, number, number],
  waterColor: THREE.Color,
  enabled: { value: number } = { value: 1 },
) {
  texture.flipY = false;
  texture.colorSpace = THREE.NoColorSpace;
  texture.minFilter = texture.magFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.needsUpdate = true;
  const rect = new THREE.Vector4(...bounds);
  root.updateWorldMatrix(true, true);
  root.traverse((o) => {
    if (!isMesh(o) || !o.material) return;
    // The shader acts only at world Y 0..3. High-land photographic meshes
    // cannot contribute and do not reserve an unrelated coastal sampler.
    const box = new THREE.Box3().setFromObject(o);
    if (box.min.y > 3 || box.max.y < 0) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (m.userData.seaEdgeBlend) continue;
      const maskCount: unknown = m.userData.spatialMaskSamplerCount;
      const maximum: unknown = m.userData.maxFragmentTextures;
      if (typeof maskCount === 'number' && typeof maximum === 'number')
        assertMaterialSamplerCapacity(m, maskCount, maximum, 1);
      m.userData.seaEdgeBlend = true;
      const prior = m.onBeforeCompile.bind(m);
      const priorKey = m.customProgramCacheKey.bind(m);
      m.onBeforeCompile = function (shader: MaterialShader, renderer: THREE.WebGLRenderer) {
        prior.call(this, shader, renderer);
        Object.assign(shader.uniforms, {
          seaEdgeMap: { value: texture },
          seaEdgeRect: { value: rect },
          seaEdgeColor: { value: waterColor },
          seaEdgeEnabled: enabled,
        });
        shader.vertexShader = "varying vec3 vSeaEdgeWorld;\n" + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace(
          "#include <begin_vertex>",
          "#include <begin_vertex>\nvSeaEdgeWorld=(modelMatrix*vec4(transformed,1.0)).xyz;",
        );
        shader.fragmentShader =
          `varying vec3 vSeaEdgeWorld;
          uniform sampler2D seaEdgeMap; uniform vec4 seaEdgeRect;
          uniform vec3 seaEdgeColor; uniform float seaEdgeEnabled;\n` + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace(
          "#include <opaque_fragment>",
          `
          if (seaEdgeEnabled>0.5 && vSeaEdgeWorld.y>=0.0 && vSeaEdgeWorld.y<=3.0) {
            vec2 seaUV=(vSeaEdgeWorld.xz-seaEdgeRect.xy)/(seaEdgeRect.zw-seaEdgeRect.xy);
            if(all(greaterThanEqual(seaUV,vec2(0.0))) && all(lessThanEqual(seaUV,vec2(1.0)))) {
              float seaWeight=texture2D(seaEdgeMap,seaUV).r;
              outgoingLight=mix(outgoingLight,seaEdgeColor,seaWeight);
            }
          }
          #include <opaque_fragment>`,
        );
      };
      m.customProgramCacheKey = () => priorKey() + "|sea-edge-blend-v1";
      m.needsUpdate = true;
    }
  });
  return enabled;
}
