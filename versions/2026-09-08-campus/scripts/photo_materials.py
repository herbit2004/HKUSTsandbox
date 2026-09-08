"""Auditable photo sampling for reconstructed campus surfaces.

This module only resamples original image pixels for GPU size and computes UVs.
It does not synthesize a facade, erase shadows, or invent occluded image content.
Registration is explicitly appearance-level unless a calibrated pose is supplied.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def prepare_photo(source, output, source_url, max_width=3072):
    source, output = Path(source), Path(output)
    data = source.read_bytes()
    im = Image.open(source).convert('RGB')
    original_size = im.size
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output, quality=94, subsampling=0)
    encoded = output.read_bytes()
    return {'sourceURL': source_url, 'sourceFile': str(source),
            'sourceSHA256': hashlib.sha256(data).hexdigest(), 'sourceDimensions': list(original_size),
            'asset': str(output), 'sha256': hashlib.sha256(encoded).hexdigest(),
            'dimensions': list(im.size), 'bytes': len(encoded),
            'pixelOperation': 'Lanczos size reduction and JPEG encoding only; no generated content',
            'registration': 'appearance module correspondence; not a calibrated camera or surveyed elevation'}


def piecewise_photo_uv(x, y, model_x, model_y, photo_x, photo_y, dimensions):
    """Map a geometric surface's named breaks to photographed material breaks.

    The caller must split faces at model breaks. Returning merely four corner
    UVs across a window/floor break would incorrectly stretch that source image.
    Both axes may be reversed (e.g. model height and image pixel row).
    """
    def interpolate(v, a, b):
        if a[-1] < a[0]:
            a, b = a[::-1], b[::-1]
        if not all(q > p for p, q in zip(a, a[1:])):
            raise ValueError('Photographic control points must be strictly monotonic')
        return np.interp(v, a, b)
    return np.column_stack((interpolate(x, model_x, photo_x) / dimensions[0],
                            interpolate(y, model_y, photo_y) / dimensions[1]))


def prepare_photo_patch(source, output, source_url, quad, reference_width, size=512):
    """Rectify one inspected unobstructed material region, with no inpainting."""
    import cv2
    source,output=Path(source),Path(output)
    im=np.asarray(Image.open(source).convert('RGB'))
    corners=np.asarray(quad,dtype=np.float32)*im.shape[1]/reference_width
    if corners[:,0].min()<0 or corners[:,1].min()<0 or corners[:,0].max()>=im.shape[1] or corners[:,1].max()>=im.shape[0]:
        raise ValueError('Photo patch lies outside source image')
    transform=cv2.getPerspectiveTransform(corners,np.array([[0,0],[size-1,0],[size-1,size-1],[0,size-1]],np.float32))
    pixels=cv2.warpPerspective(im,transform,(size,size),flags=cv2.INTER_LINEAR)
    output.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(pixels).save(output)
    return {'sourceURL':source_url,'sourceSHA256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'sourceDimensions':[im.shape[1],im.shape[0]],'referenceWidth':reference_width,
        'inspectedQuad':quad,'homographySourcePixelsToAsset':transform.tolist(),
        'asset':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'dimensions':[size,size],'pixelOperation':'Projective bilinear sampling of an unobstructed original material patch; no inpainting or generated content',
        'registration':'Material-family reuse; not the measured texture placement of every roof'}


class HallPhotoModules:
    """Eight visible source rows and four bays, with explicit pixel landmarks.

    Pixels use the full news Photo 6 at a 1920-wide reference coordinate scale.
    The lowest row is obscured by branches and is deliberately excluded; its
    material is reused from the next clear row. No trees are painted on walls.
    Reuse across unphotographed elevations is recorded, not claimed as a survey.
    """
    reference_size = (1920, 1280)
    # Top boundary, window frame top, window frame bottom, bottom boundary at x=1258.
    rows = [[216, 237, 282, 317], [317, 326, 373, 418],
            [418, 426, 470, 537], [537, 543, 585, 629],
            [629, 632, 675, 714], [714, 719, 762, 803],
            [803, 805, 848, 888]]
    columns = [[1165, 1184, 1204, 1226], [1226, 1247, 1269, 1289],
               [1289, 1309, 1331, 1352], [1352, 1372, 1394, 1402]]

    def uv(self, u, y, center, width, spacing, floor_y, pitch, source_row, column):
        px = self.columns[column % len(self.columns)]
        py = self.rows[int(np.clip(source_row, 0, len(self.rows)-1))]
        result = piecewise_photo_uv(np.asarray(u), np.asarray(y),
            [center-spacing/2, center-width/2, center+width/2, center+spacing/2],
            [floor_y, floor_y+.87, floor_y+2.30, floor_y+pitch],
            px, py[::-1], self.reference_size)
        # Horizontal mortar/floor lines converge in the original perspective.
        # This adjustment follows the inspected image line slopes, not a new
        # camera pose. It keeps adjacent source bays on their own window frame.
        pixel_x, pixel_y = result[:, 0]*1920, result[:, 1]*1280
        slope = -.135 + (pixel_y-216) * .00020
        result[:, 1] += slope*(pixel_x-1258)/1280
        return result

    def save(self, path, photo_record):
        Path(path).write_text(json.dumps({'version': 1, 'photo': photo_record,
            'referenceDimensions': self.reference_size, 'rowsTopToBottom': self.rows,
            'columnsLeftToRight': self.columns,
            'registration': 'Manual window-frame and floor-band correspondences in the inspected official photograph.',
            'occlusionPolicy': 'Exclude lowest branch-occluded row; reuse nearest clear source module.',
            'reusePolicy': 'Seven visible source rows and four bays reused across the family, with windows aligned to generated openings. Unphotographed cardinal elevations are approximate.',
            'cameraPoseMeasured': False, 'newFloorEntities': False}, indent=2)+'\n')
