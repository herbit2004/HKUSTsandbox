"""Shared, deterministic geometry and GLB packing for all four i-Village halls.

Positions remain in the project's source-local frame. Each building is a
separate named root in ONE GLB, sharing the same material/texture definitions.
"""
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import triangulate


def polygons(shape):
    return [p for p in getattr(shape, 'geoms', [shape])
            if p.geom_type == 'Polygon' and p.area > 1e-8]


class BuildingMesh:
    def __init__(self, entity_id, building_id, name, photo_modules=None):
        self.entity_id, self.building_id, self.name = entity_id, building_id, name
        self.faces = {}
        self.features = {}
        self.photo_modules = photo_modules

    def triangle(self, points, material, uv=None, feature='shell'):
        points = np.asarray(points, dtype=float)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        length = np.linalg.norm(normal)
        if length < 1e-9:
            return
        normal /= length
        self.faces.setdefault(material, []).append((points, normal,
            np.zeros((3, 2)) if uv is None else np.asarray(uv), feature))
        self.features[feature] = self.features.get(feature, 0) + 1

    def quad(self, points, material, uv=None, feature='shell'):
        uv = np.zeros((4, 2)) if uv is None else np.asarray(uv)
        for ix in [[0, 1, 2], [0, 2, 3]]:
            self.triangle(np.asarray(points)[ix], material, uv[ix], feature)

    def surface(self, shape, height, material, feature='roof'):
        for poly in polygons(shape):
            for triangle in triangulate(poly):
                if triangle.difference(poly).area > 1e-7:
                    continue
                xz = np.asarray(triangle.exterior.coords)[:3]
                p = np.array([[x, height(x, z) if callable(height) else height, z]
                              for x, z in xz])
                if np.cross(p[1] - p[0], p[2] - p[0])[1] < 0:
                    p = p[::-1]
                self.triangle(p, material, p[:, [0, 2]] / (6 if self.photo_modules and material==2 else 2), feature)

    def wall(self, start, end, lower, upper, material, feature='solid-wall'):
        start, end = np.asarray(start), np.asarray(end)
        bottom = [lower(*p) if callable(lower) else lower for p in [start, end]]
        top = [upper(*p) if callable(upper) else upper for p in [start, end]]
        p = [[start[0], bottom[0], start[1]], [end[0], bottom[1], end[1]],
             [end[0], top[1], end[1]], [start[0], top[0], start[1]]]
        length = np.linalg.norm(end - start)
        uv = [[0,bottom[0]/1.6],[length/1.6,bottom[1]/1.6],
              [length/1.6,top[1]/1.6],[0,top[0]/1.6]]
        if self.photo_modules and feature in ('pale-vertical-core','core-vertical-glazing'):
            # Same untouched photograph, separate inspected wall / glazing
            # regions. Exclude the neighbouring blue facade and vegetation.
            x0,x1,y0,y1 = (724,780,225,1015) if feature=='pale-vertical-core' else (796,809,291,973)
            uv=np.array([[x0,y1],[x1,y1],[x1,y0],[x0,y0]])/[1920,1280]
            material = 12 if feature=='pale-vertical-core' else 13
        self.quad(p,material,uv,feature)

    def solid(self, shape, lower, upper, material, feature='core'):
        self.surface(shape, upper, material, feature)
        for poly in polygons(shape):
            for ring in [poly.exterior, *poly.interiors]:
                points = list(ring.coords)
                for a, b in zip(points, points[1:]):
                    self.wall(a, b, lower, upper, material, feature)

    def facade(self, start, end, base, roof, outward, phase=0,
               pitch=3.15, spacing=2.35, material=0, ground_at=None):
        """Actual openings/reveals/glazing, not windows painted across a wall.

        Window pitch and reveal depths are declared appearance parameters;
        they create no unprovided room, floor or window registry entities.
        """
        a, b, n = np.asarray(start), np.asarray(end), np.asarray(outward)
        length = np.linalg.norm(b-a)
        if length < .03:
            return
        tangent = (b-a)/length
        top_a, top_b = roof(*a), roof(*b)

        def xz(u, depth=0):
            return a + tangent*u + n*depth

        def top(u):
            return top_a + (top_b-top_a)*u/length

        def rect(u0, u1, lo, hi, mat, depth=0, feature='facade'):
            if u1-u0 < 1e-6:
                return
            photographic = self.photo_modules is not None and mat in (0,4,5,6) and count > 0
            # Wall strips need the same per-bay UV partitions as their actual
            # windows. A full-width strip with four UV corners stretches every
            # photographed window across the building and creates double frames.
            breaks = sorted({u0,u1,*[float(v) for c in centers
                for v in (c-spacing/2,c-.5,c+.5,c+spacing/2) if u0+1e-7<v<u1-1e-7]}) if photographic else [u0,u1]
            for left,right in zip(breaks,breaks[1:]):
                h0, h1 = min(hi, top(left)), min(hi, top(right))
                l0, l1 = min(lo, h0), min(lo, h1)
                s, e = xz(left, depth), xz(right, depth)
                uv = [[(left+phase)/1.6, l0/1.6], [(right+phase)/1.6, l1/1.6],
                      [(right+phase)/1.6, h1/1.6], [(left+phase)/1.6, h0/1.6]]
                output_mat = mat
                if photographic:
                    col = int(np.argmin(abs(centers-(left+right)/2)))
                    total_rows = max(1,int((min(top_a,top_b)-base)/pitch))
                    source_row = round(6*(1-np.clip(row/max(1,total_rows-1),0,1)))
                    uv = self.photo_modules.uv([left,right,right,left], [l0,l1,h1,h0],
                        centers[col], 1.0, spacing, floors[row], pitch, source_row, col)
                    # A closed strip (below source ground or a truncated top
                    # floor) must not acquire a photographed fake window.
                    # Existing actual glazed quads use materials 4..6 here.
                    crosses_window = right > centers[col]-.5+1e-6 and left < centers[col]+.5-1e-6
                    if mat==0 and crosses_window and hi>floors[row]+.87+1e-6 and lo<floors[row]+2.30-1e-6:
                        uv[:,0]=np.array([1277,1285,1285,1277])/1920
                    output_mat = 0
                elif self.photo_modules is not None and mat==0:
                    # Tiny unsplit corners have no window bay; world-repeat UVs
                    # would sample arbitrary background from the full photograph.
                    yy=np.clip((max(top_a,top_b)-np.array([l0,l1,h1,h0]))/
                        max(1,max(top_a,top_b)-base),0,1)*640+235
                    uv=np.column_stack((np.array([1277,1285,1285,1277])/1920,yy/1280))
                self.quad([[s[0],l0,s[1]],[e[0],l1,e[1]],
                           [e[0],h1,e[1]],[s[0],h0,s[1]]],output_mat,uv,feature)

        floors = np.arange(base, max(top_a, top_b)+pitch, pitch)
        # Avoid placing a sliver of a window at a terrace edge. Keep a real pier
        # at each corner; row/column alignment stays fixed while the camera moves.
        count = max(0, int((length-.8)/spacing))
        centers = (np.arange(count)-(count-1)/2)*spacing+length/2
        for row, lo in enumerate(floors[:-1]):
            hi = min(lo+pitch, max(top_a, top_b))
            if hi <= lo:
                continue
            sill, head = lo+.87, lo+2.30
            if hi < head+.25 or count == 0:
                rect(0, length, lo, hi, material)
                continue
            rect(0, length, lo, sill, material)
            rect(0, length, head, hi, material)
            cursor = 0
            for column, center in enumerate(centers):
                width = 1.0
                u0, u1 = center-width/2, center+width/2
                if head+.18 > min(top(u0),top(u1)):
                    continue
                # The new facade remains closed by recessed glazing. A coarse
                # terrain sample at a wall must not erase an entire exposed
                # window row; original ground geometry handles burial/occlusion.
                # Preserve the old branch only for reproducing its historical asset.
                if self.photo_modules is None and ground_at is not None and ground_at(*xz(center)) > head:
                    continue
                rect(cursor,u0,sill,head,material)
                # Dark reveal, set back 0.13 m; all four edges have real depth.
                outer = [[*xz(u0)[:1],sill,xz(u0)[1]], [*xz(u1)[:1],sill,xz(u1)[1]],
                         [*xz(u1)[:1],head,xz(u1)[1]], [*xz(u0)[:1],head,xz(u0)[1]]]
                inner = [[p[0]-n[0]*.13,p[1],p[2]-n[1]*.13] for p in outer]
                for i in range(4):
                    j=(i+1)%4
                    self.quad([outer[i],outer[j],inner[j],inner[i]],3,feature='window-reveal')
                rect(u0,u1,sill,head,4+(row+column)%3,-.135,'recessed-glazing')
                # Slim frame and a single vertical opening division are visible
                # in reference photographs; dimensions remain appearance-only.
                for left,right in [(u0,u0+.045),(u1-.045,u1),(center-.022,center+.022)]:
                    rect(left,right,sill,head,3,-.01,'window-frame')
                rect(u0,u1,sill,sill+.045,3,-.01,'window-frame')
                rect(u0,u1,head-.045,head,3,-.01,'window-frame')
                cursor=u1
            rect(cursor,length,sill,head,material)

        for h in np.arange(base+pitch,max(top_a,top_b)-.35,pitch):
            if h > min(top_a,top_b)-.3:
                continue
            # Continuous cream horizontal sunshade, including a dark underside.
            p0,p1,p2,p3=xz(0,.01),xz(length,.01),xz(length,.32),xz(0,.32)
            self.quad([[p0[0],h,p0[1]],[p1[0],h,p1[1]],[p2[0],h+.08,p2[1]],[p3[0],h+.08,p3[1]]],1,feature='sunshade-top')
            self.wall(p3,p2,h-.12,h+.08,1,'sunshade-edge')
            self.quad([[p3[0],h-.12,p3[1]],[p2[0],h-.12,p2[1]],[p1[0],h-.12,p1[1]],[p0[0],h-.12,p0[1]]],3,feature='sunshade-underside')


def write_glb(path, buildings, texture_path, provenance, photographic=False, paving_path=None):
    palette = [('blue-ceramic-cladding',[1,1,1,1]),('cream-shading-and-cores',[.78,.77,.71,1]),
        ('roof-paving',[.48,.49,.47,1]),('window-reveal-and-frame',[.19,.23,.26,1]),
        ('glazing-charcoal',[.075,.12,.16,1]),('glazing-slate',[.11,.17,.21,1]),
        ('glazing-muted-sky',[.16,.23,.28,1]),('photovoltaic',[.17,.27,.34,1]),
        ('pv-frame',[.52,.57,.6,1]),('walkway-glazing',[.22,.38,.4,1]),
        ('roof-edge-shadow',[.34,.36,.36,1])]
    if photographic:
        # Palette values were chosen as display/photo RGB. glTF factors are
        # linear: writing display 0.78 directly makes it appear ~0.895 on screen.
        # Original JPEG pixels remain encoded sRGB and are decoded by the loader.
        palette[2]=('roof-paving',[.64,.63,.60,1])
    def material_factor(color):
        if not photographic:return color
        rgb=np.asarray(color[:3]);linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        return [*linear.tolist(),color[3]]
    materials = []
    for i,(name,color) in enumerate(palette):
        pbr={'baseColorFactor':material_factor(color),'metallicFactor':0,'roughnessFactor':.9}
        if i==0:pbr['baseColorTexture']={'index':0}
        materials.append({'name':name,'pbrMetallicRoughness':pbr,'doubleSided':True,
                          'extensions':{'KHR_materials_unlit':{}}})
    if paving_path:
        materials[2]['pbrMetallicRoughness'].update(baseColorFactor=[1,1,1,1],baseColorTexture={'index':1})
        materials[2]['extras']={'appearanceRole':'source-material-swatch','bakeStructureShadow':True}
    if photographic:
        # Non-facade surfaces have no registered source UVs yet. Keep them a
        # separate explicit material; they must never sample a whole photo at
        # arbitrary world-metric coordinates (which would paint sky on a roof).
        materials.append({'name':'blue-parapet-awaiting-photo-registration',
            'pbrMetallicRoughness':{'baseColorFactor':material_factor([.28,.43,.54,1]),'metallicFactor':0,'roughnessFactor':.9},
            'doubleSided':True,'extensions':{'KHR_materials_unlit':{}}})
        palette.append(('blue-parapet-awaiting-photo-registration',[.28,.43,.54,1]))
        for name in ('registered-photo-pale-core','registered-photo-core-glazing'):
            materials.append({'name':name,'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],
                'baseColorTexture':{'index':0},'metallicFactor':0,'roughnessFactor':.9},
                'doubleSided':True,'extensions':{'KHR_materials_unlit':{}}})
            palette.append((name,[1,1,1,1]))
    gltf={'asset':{'version':'2.0','generator':'HKUST unified i-Village reconstruction'},
          'extensionsUsed':['KHR_materials_unlit'],'scene':0,'scenes':[{'nodes':[]}],
          'nodes':[],'meshes':[],'materials':materials,'images':[],'textures':[{'source':0,'sampler':0}],
          'samplers':[{'magFilter':9729,'minFilter':9987,'wrapS':33071 if photographic else 10497,'wrapT':33071 if photographic else 10497}],
          'buffers':[{}],'bufferViews':[],'accessors':[],'extras':provenance}
    binary=bytearray()

    def view(raw):
        binary.extend(b'\0'*((-len(binary))%4))
        i=len(gltf['bufferViews'])
        gltf['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(raw)})
        binary.extend(raw)
        return i

    def accessor(values,kind):
        values=np.asarray(values,dtype='<f4')
        i=len(gltf['accessors'])
        desc={'bufferView':view(values.tobytes()),'componentType':5126,'count':len(values),'type':kind}
        if kind=='VEC3':desc.update(min=values.min(0).tolist(),max=values.max(0).tolist())
        gltf['accessors'].append(desc)
        return i

    gltf['images'].append({'bufferView':view(Path(texture_path).read_bytes()),
        'mimeType':'image/jpeg' if Path(texture_path).suffix.lower() in ('.jpg','.jpeg') else 'image/png',
        'name':'registered-original-photograph' if photographic else 'shared-blue-ceramic'})
    if paving_path:
        gltf['images'].append({'bufferView':view(Path(paving_path).read_bytes()),'mimeType':'image/png','name':'original-roof-paving-patch'})
        gltf['textures'].append({'source':1,'sampler':1})
        gltf['samplers'].append({'magFilter':9729,'minFilter':9987,'wrapS':10497,'wrapT':10497})
    reports=[]
    # Fixed neutral daylight gives the generated architecture stable readable
    # depth alongside already-lit photographic sources, without double lighting.
    sun=np.array([-.5,.75,-.4]);sun/=np.linalg.norm(sun)
    for building in buildings:
        root=len(gltf['nodes'])
        gltf['scenes'][0]['nodes'].append(root)
        gltf['nodes'].append({'name':building.name,'children':[],
            'extras':{'entityId':building.entity_id,'buildingId':building.building_id,'representation':'unified-reconstruction'}})
        all_positions=[]
        for material,faces in sorted(building.faces.items()):
            t=np.array([f[0] for f in faces]);n=np.repeat(np.array([f[1] for f in faces]),3,axis=0)
            uv=np.array([f[2] for f in faces]).reshape(-1,2)
            shade=np.ones(len(n)) if photographic and material in (0,12,13) else np.clip(.86+.14*(n@sun),.7,1)
            colors=np.repeat(shade[:,None],3,axis=1)
            positions=t.reshape(-1,3);all_positions.append(positions)
            primitive={'mode':4,'material':material,'attributes':{
                'POSITION':accessor(positions,'VEC3'),'NORMAL':accessor(n,'VEC3'),
                'COLOR_0':accessor(colors,'VEC3')}}
            if photographic:
                ranges=[]
                for index,face in enumerate(faces):
                    if ranges and ranges[-1][2]==face[3]:ranges[-1][1]+=1
                    else:ranges.append([index,1,face[3]])
                primitive['extras']={'featureTriangleRanges':ranges,
                    'meaning':'Appearance geometry tags only; not additional floor/room/window entities'}
            if material==0 or photographic and material in (12,13) or paving_path and material==2:primitive['attributes']['TEXCOORD_0']=accessor(uv,'VEC2')
            mesh=len(gltf['meshes']);gltf['meshes'].append({'name':building.name+'/'+palette[material][0],'primitives':[primitive]})
            node=len(gltf['nodes']);gltf['nodes'][root]['children'].append(node)
            gltf['nodes'].append({'name':building.name+'/'+palette[material][0],'mesh':mesh})
        pos=np.concatenate(all_positions)
        assert np.isfinite(pos).all()
        reports.append({'entityId':building.entity_id,'buildingId':building.building_id,
            'nodeName':building.name,'triangles':len(pos)//3,'bounds':{'min':pos.min(0).tolist(),'max':pos.max(0).tolist()},
            'features':building.features})
    gltf['buffers'][0]['byteLength']=len(binary)
    binary.extend(b'\0'*((-len(binary))%4))
    encoded=json.dumps(gltf,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    payload=struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(binary))+struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    Path(path).write_bytes(payload)
    return {'url':Path(path).name,'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload),
            'members':reports,'sharedTextureCount':len(gltf['images']),'drawPrimitives':len(gltf['meshes'])}
