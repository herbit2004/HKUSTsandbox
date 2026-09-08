import * as THREE from 'three';
import { SpatialMasks } from './spatial-masks';

export type CurrentFormMask = {
  url: string;
  boundsXZ: { min: number[]; max: number[] };
  width: number;
  height: number;
  pixelSizeMeters: number;
  replacementMinY: number;
  replacementMaxY: number;
  pixelMinYEncoding?: 'int-meters-alpha-255-common';
};
type ReadyMask = { descriptor: CurrentFormMask; pixels: Uint8ClampedArray };
export type CurrentFormCoverageEntry = {id: string; descriptor: CurrentFormMask; texture: THREE.Texture};

/** Only completed current forms enter this exact source-grid union. One sampler
 * covers every ready member; G/B encode the old-source upper removal guard. The
 * common lower guard protects ground below their public G/F elevation. */
export class CurrentFormCoverage {
  ready = new Map<string, ReadyMask>();
  constructor(private masks: SpatialMasks) {}

  add(id: string, descriptor: CurrentFormMask, texture: THREE.Texture) {
    this.addBatch([{id, descriptor, texture}]);
  }

  /** Decode every sibling first, then install one union between render frames. */
  addBatch(entries: readonly CurrentFormCoverageEntry[]) {
    this.addPixelsBatch(entries.map(({id, descriptor, texture}) => ({
      id, descriptor, pixels: this.decode(descriptor, texture),
    })));
  }

  private decode(descriptor: CurrentFormMask, texture: THREE.Texture) {
    const canvas = document.createElement('canvas');
    canvas.width = descriptor.width;
    canvas.height = descriptor.height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Current form mask decoder unavailable');
    const image = texture.image as HTMLImageElement;
    if (image.width !== descriptor.width || image.height !== descriptor.height)
      throw new Error('Current form mask dimensions differ from checked source');
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    return pixels;
  }

  addPixels(id: string, descriptor: CurrentFormMask, pixels: Uint8ClampedArray) {
    this.addPixelsBatch([{id, descriptor, pixels}]);
  }

  addPixelsBatch(entries: readonly (ReadyMask & {id: string})[]) {
    if (new Set(entries.map(e => e.id)).size !== entries.length)
      throw new Error('Current form batch has duplicate members');
    const previous = new Map(this.ready);
    for (const {id, descriptor, pixels} of entries) this.ready.set(id, {descriptor, pixels});
    try { this.rebuild(); } catch (error) {
      this.ready = previous;
      throw error;
    }
  }

  removeBatch(ids: readonly string[]) {
    const previous = new Map(this.ready);
    for (const id of ids) this.ready.delete(id);
    try { this.rebuild(); } catch (error) { this.ready = previous; throw error; }
  }

  private rebuild() {
    const entries = [...this.ready.values()];
    if (!entries.length) { this.masks.enable('currentForms', false); return; }
    const resolution = entries[0].descriptor.pixelSizeMeters;
    // Current-form packages can live on different terraces. Keep one texture
    // sampler, but encode each occupied pixel's absolute lower guard in alpha.
    // Alpha 255 remains the common-union minimum for the lowest package.
    const minY = Math.min(...entries.map(e => e.descriptor.replacementMinY));
    for (const { descriptor: d, pixels } of entries) {
      if (d.pixelSizeMeters !== resolution ||
        pixels.length !== d.width * d.height * 4 ||
        Math.abs(d.width * resolution - d.boundsXZ.max[0] + d.boundsXZ.min[0]) > 1e-6 ||
        Math.abs(d.height * resolution - d.boundsXZ.max[1] + d.boundsXZ.min[1]) > 1e-6 ||
        !Number.isFinite(d.replacementMaxY) || d.replacementMaxY < minY || d.replacementMaxY >= 256)
        throw new Error('Current form mask must retain its checked grid and vertical guards');
    }
    const minX = Math.min(...entries.map(e => e.descriptor.boundsXZ.min[0]));
    const minZ = Math.min(...entries.map(e => e.descriptor.boundsXZ.min[1]));
    const maxX = Math.max(...entries.map(e => e.descriptor.boundsXZ.max[0]));
    const maxZ = Math.max(...entries.map(e => e.descriptor.boundsXZ.max[1]));
    const width = Math.round((maxX - minX) / resolution);
    const height = Math.round((maxZ - minZ) / resolution);
    const data = new Uint8Array(width * height * 4);
    for (const { descriptor: d, pixels } of entries) {
      const left = (d.boundsXZ.min[0] - minX) / resolution;
      const top = (d.boundsXZ.min[1] - minZ) / resolution;
      if (!Number.isInteger(left) || !Number.isInteger(top))
        throw new Error('Current form masks must share source pixel alignment');
      const limit = Math.round(d.replacementMaxY * 256);
      for (let y = 0; y < d.height; y++) for (let x = 0; x < d.width; x++) {
        if (pixels[(y * d.width + x) * 4] <= 127) continue;
        const dest = ((top + y) * width + left + x) * 4;
        // Source masks use white RGB for ordinary building coverage. A marked
        // black G/B occupied pixel is an exact renderer handoff: its alpha is
        // still the source-removal lower guard, while 65535 lets the terrain
        // shader distinguish this pixel without another sampler.
        const source = (y * d.width + x) * 4;
        const handoff = pixels[source + 1] === 0 && pixels[source + 2] === 0;
        const encoded = Math.max(handoff ? 65535 : limit, data[dest + 1] * 256 + data[dest + 2]);
        const alpha = pixels[(y * d.width + x) * 4 + 3];
        const lower = d.pixelMinYEncoding && alpha < 255
          ? Math.max(d.replacementMinY, alpha)
          : d.replacementMinY;
        const previousLower = data[dest] > 127
          ? data[dest + 3] < 255 ? data[dest + 3] : minY
          : Infinity;
        const mergedLower = data[dest] > 127 ? Math.min(lower, previousLower) : lower;
        data[dest] = 255;
        data[dest + 1] = encoded >> 8;
        data[dest + 2] = encoded & 255;
        data[dest + 3] = mergedLower > minY ? Math.floor(mergedLower) : 255;
      }
    }
    this.masks.set('currentForms', new THREE.DataTexture(data, width, height), [minX, minZ, maxX, maxZ], minY);
    this.masks.slots.currentForms.heightEncoded.value = 2;
  }
}
