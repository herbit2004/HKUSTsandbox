import * as THREE from 'three';

/** Count actual texture-valued material properties, including alpha/env/AO maps.
 * Current photographic sources are MeshBasicMaterial; no lit shadow samplers. */
export function materialTextureSamplers(material: THREE.Material): number {
  return Object.values(material).reduce<number>(
    (count, value: unknown) => count + (value instanceof THREE.Texture ? 1 : 0),
    0,
  );
}

export function assertMaterialSamplerCapacity(
  material: THREE.Material,
  maskSamplers: number,
  maxFragmentTextures: number,
  additionalShaderSamplers = 0,
) {
  const required = materialTextureSamplers(material) + maskSamplers + additionalShaderSamplers;
  if (required > maxFragmentTextures)
    throw new Error(`Material ${material.name || material.type} needs ${required} fragment textures; renderer supports ${maxFragmentTextures}`);
  return required;
}
