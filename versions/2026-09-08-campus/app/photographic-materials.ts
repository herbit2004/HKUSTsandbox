import * as THREE from 'three';

/** Reused material photographs can carry an explicit, reviewable display
 * calibration. This never changes the source image or the native campus tiles. */
function applyPhotoCalibration(material: THREE.Material) {
  const profile: unknown = material.userData.campusPhotoCalibration;
  if (!profile || typeof profile !== 'object' || material.userData.photoCalibrationInstalled) return;
  const {saturation, exposure, linearTint} = profile as {saturation: number; exposure: number; linearTint: number[]};
  if (!Number.isFinite(saturation) || saturation < 0 || saturation > 1 ||
      !Number.isFinite(exposure) || exposure <= 0 || exposure > 2 ||
      !Array.isArray(linearTint) || linearTint.length !== 3 || linearTint.some(v=>!Number.isFinite(v)||v<=0||v>2))
    throw new Error('Invalid photographic display calibration');
  const before = material.onBeforeCompile.bind(material), key = material.customProgramCacheKey();
  material.onBeforeCompile = (shader, renderer) => {
    before(shader, renderer);
    shader.uniforms.campusPhotoSaturation = {value:saturation};
    shader.uniforms.campusPhotoExposure = {value:exposure};
    shader.uniforms.campusPhotoTint = {value:new THREE.Vector3(...linearTint)};
    shader.fragmentShader = 'uniform float campusPhotoSaturation;\nuniform float campusPhotoExposure;\nuniform vec3 campusPhotoTint;\n' + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace('#include <map_fragment>', `#include <map_fragment>
      float campusPhotoLuminance = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
      diffuseColor.rgb = mix(vec3(campusPhotoLuminance), diffuseColor.rgb, campusPhotoSaturation)
        * campusPhotoExposure * campusPhotoTint;`);
  };
  material.customProgramCacheKey = () => key+'|campus-photo-calibration-v1';
  material.userData.photoCalibrationInstalled = true;
  material.needsUpdate = true;
}

/** Photo-derived elevations already contain lighting, like the original campus
 * photography. Keep those pixels unlit rather than shading them a second time. */
export function preparePhotographicMaterials(root: THREE.Object3D, maximumAnisotropy = 8) {
  const replacements = new Map<THREE.Material, THREE.Material>();
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    const convert = (source: THREE.Material) => {
      if (replacements.has(source)) return replacements.get(source)!;
      const mapped = source as THREE.MeshStandardMaterial;
      const bakedLighting = source.userData.campusBakedLighting === true;
      if (!mapped.map && !bakedLighting) return source;
      if (mapped.map) {
        mapped.map.anisotropy = Math.min(8, maximumAnisotropy);
        mapped.map.generateMipmaps = true;
        mapped.map.minFilter = THREE.LinearMipmapLinearFilter;
      }
      // KHR_materials_unlit assets already use the photographic display path.
      // Retain their shared material and baked COLOR_0 instead of rebuilding it.
      if (source instanceof THREE.MeshBasicMaterial) { applyPhotoCalibration(source); return source; }
      const material = new THREE.MeshBasicMaterial({
        map:mapped.map,color:mapped.color,side:mapped.side,
        transparent:mapped.transparent,opacity:mapped.opacity,alphaTest:mapped.alphaTest,
        alphaMap:mapped.alphaMap,vertexColors:mapped.vertexColors,
        toneMapped:mapped.toneMapped,depthTest:mapped.depthTest,depthWrite:mapped.depthWrite,
        polygonOffset:mapped.polygonOffset,polygonOffsetFactor:mapped.polygonOffsetFactor,
        polygonOffsetUnits:mapped.polygonOffsetUnits,
      });
      material.name = source.name;
      material.userData = {...source.userData,
        runtimeAppearance:mapped.map?'unlit-photo-derived':'unlit-baked-current-form'};
      applyPhotoCalibration(material);
      replacements.set(source, material);
      source.dispose();
      return material;
    };
    object.material = Array.isArray(object.material) ? object.material.map(convert) : convert(object.material);
  });
}
