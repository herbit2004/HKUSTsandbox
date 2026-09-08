import * as THREE from 'three';
import datasetProfile from '../public/data/dataset-profile.json';
import type {PickingSurface,SourceAssociation,SourceBuildingDomain} from './entity-picking';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {applySeaEdgeBlend} from './sea-edge-blend';
import {preparePhotographicMaterials} from './photographic-materials';
import {createBuildingSelection,type BuildingSelectionSource} from './building-selection';
import {visibleDetails,StableDetailChoice,StableDetailOrder,textureDetailPlan,type TextureDetailGroup} from './detail-priority';
import {AtomicTextures} from './atomic-textures';
import {DetailResourcePool,sharedDetailCaps,type DetailResourceBytes} from './detail-resource-pool';
import {DetailStream} from './detail-stream';
import {CampusMeshDetail} from './campus-mesh-detail';
import {AutomaticQuality,initialQualityLevel,qualityProfiles,type QualityMode,type QualityLevel} from './quality';
import {classifyEntity} from './entity-classification';
import {createBuildingOccluders,markerOccluded,type BuildingOccluder} from './label-occlusion';
import {t,type Locale} from './i18n';
import {entityDisplayName} from './entity-names';
import {MotionMetrics} from './motion-metrics';
import {AnchoredPan,pickVisiblePanAnchor} from './anchored-pan';
import {isVisibleSurfaceHit} from './entity-picking';
import {SpatialMasks,replacementSlots,partialSlots} from './spatial-masks';
import {CurrentFormCoverage} from './current-form-coverage';
import currentFormSourceProtection from '../public/models/current-forms/ivillage-rebuild/source-protection.json';
import {loadCurrentFormSet, parseCurrentFormSetManifest, type CurrentFormSet} from './current-form-set';
import {CurrentFormResidency, currentFormFixedTextureBytes} from './current-form-residency';
import {pickEntity,exteriorSourceOwner} from './entity-picking';
import pickingDomainsSource from '../public/surfaces/entrance/entity-picking-domains.json';
import namedBuildingDomainsSource from '../public/data/picking/building-domains.json';
import extraBuildingDomainsSource from '../public/data/picking/building-domains-extra.json';
import {CoherentExteriors} from './coherent-exteriors';
import {ExteriorViewPlanner} from './exterior-view-plan';
import {connectMapLabelWheel} from './map-label-wheel';
import {FirstPersonFlight,FlightGroundGuard,snapshotOrbit,returnToOrbit,type NavigationMode,type OrbitSnapshot,type FlightState} from './first-person-flight';
import {RoadCoveragePlanner,parseRoadProtection,visibleRoadClusters,type RoadCoverageDiagnostics} from './road-coverage-plan';
import roadProtectionSource from '../public/models/hires/road-protection.json';
import {WorldInterior} from './world-interior';
import {EntityRegistry,type Entity} from './entity-registry';
import {releaseObject} from './resources';
import {CameraGroundConstraint,createGridGroundSampler,createRegularTerrainPatchSampler,createAllowedFloorSampler,type HeightSampler,type AllowedFloorSampler,type HeightGrid,type GroundMetrics} from './camera-ground-constraint';
import {isMesh,textureMipBytes,exteriorEntityId,exteriorBuildingId,type Point3,type PointXZ,type Bounds3,type BoundsXZ,type Matrix16,type PolygonPart,type BuildingFootprint,type BuildingFootprintManifest,type FloorManifest,type FloorManifestEntry} from './source-types';
type NamedDomain=SourceBuildingDomain&{physicalDomainId?:string};
type AggregateDomain=NamedDomain&{physicalDomainId:string};
const pickingDomains=pickingDomainsSource as unknown as {groundSurfaces:PickingSurface[];sourceAssociations:SourceAssociation[]};
const namedBuildingDomains=namedBuildingDomainsSource as unknown as {domains:NamedDomain[]};
const extraBuildingDomains=extraBuildingDomainsSource as unknown as {domains:NamedDomain[];auditOnlyAggregateDomains:AggregateDomain[];sourceObjectOwners:Array<{sourceObjectId:string;entityId:string}>};
export type SafeFrameInsets={left:number;right?:number;top?:number;bottom?:number};
export type POI={id:string;name:string;en:string;category:string;status:string;description:string;source:string;[key:string]:unknown};
export type SceneState={
 loaded:number;total:number;buildingId:string;floorId:string;loadingFloor:boolean;selectedId:string;
 detailPool?:ReturnType<DetailResourcePool['stats']>;fixedResources?:{estimatedTextureBytes:number;textures:number;includes:string;excludes:string;currentFormBudgetBytes?:number;currentFormChargedBytes?:number;currentFormPendingBytes?:number};
 roadCoverage?:RoadCoverageDiagnostics;currentFormResidency?:ReturnType<CurrentFormResidency['stats']>;
 navigation?:{mode:NavigationMode;flight:FlightState;returnFocus:'surface'|'saved'|null;groundLift:number};
 exterior:ReturnType<CoherentExteriors['stats']>;terrainTiles:number;cacheFloors:number;cacheMiB:number;
 textures:number;geometries:number;triangles:number;camera:number[];target:number[];cadAnchor:string;
 quality?:{mode:QualityMode;level:QualityLevel;dpr:number;initialLevel?:QualityLevel;cores?:number;maxTextureSize?:number;maxFragmentTextures?:number;adaptation?:ReturnType<AutomaticQuality['stats']>};meshDetail?:ReturnType<CampusMeshDetail['stats']>;motion?:ReturnType<MotionMetrics['stats']>;viewport?:{left:number;top:number;width:number;height:number;center:number[];canvasCenter:number[];safeCenter:number[];targetPixel:number[];targetNdc:number[]};pan?:ReturnType<AnchoredPan['stats']>;immersion?:{target:boolean;progress:number};ground:GroundMetrics|null;surfaceMeshes:number;landmarks?:string[];textureDetail?:ReturnType<AtomicTextures['stats']>;detailCandidates?:string[];currentForms?:string[];currentFormAssets?:Array<{sha256:string;bytes:number;buildingIds:string[]}>;sourceProtection?:ReturnType<SpatialMasks['samplerStats']>;
};
export const initialSceneState:SceneState={
 loaded:0,total:292,buildingId:'',floorId:'',loadingFloor:false,selectedId:'',
 exterior:{building:'',loading:'',loaded:0,total:0,textureMiB:0,error:'',visibleCount:0,visibleBuildings:[],visibleIds:[],visibleTextureMiB:0,cacheGroups:0,cacheTextureMiB:0,pendingTextureMiB:0,residentTextureMiB:0,budgetTextureMiB:640,cancelling:false,retryCount:0,retryInSeconds:0,cacheHits:0,cancelled:0,timeouts:0,failures:0,failureDetail:'',failureKey:'',budgetFallbacks:0},
 terrainTiles:0,cacheFloors:0,cacheMiB:0,textures:0,geometries:0,triangles:0,
 camera:[],target:[],cadAnchor:'',ground:null,surfaceMeshes:0,
};
type Options={select:(id:string)=>void;change:(s:SceneState)=>void;error:(s:string)=>void};
type Marker={entityId:string;position:THREE.Vector3;label:HTMLButtonElement};
type ViewSnapshot={camera:Point3;target:Point3};
type Flight={start:number;from:THREE.Vector3;to:THREE.Vector3;fromTarget:THREE.Vector3;toTarget:THREE.Vector3};
type PreviewManifest={tiles:Array<{id:string;url:string;center:Point3;matrix:Matrix16}>};
type CoverageManifest=({boundsXZ:BoundsXZ;bounds?:BoundsXZ}|{boundsXZ?:undefined;bounds:BoundsXZ})&({url:string;maskUrl?:string}|{url?:undefined;maskUrl:string});
type RasterManifest={url:string;minX:number;minZ:number;maxX:number;maxZ:number};
type SurfaceFeature={entityId:string;meshBounds:Bounds3};
type SurfaceManifest={url:string;features:SurfaceFeature[]};
type FacilityPoint={id:string;entityId:string;floorId:string;position:Point3};
type OutdoorEntities={
 surfaceNodeEntityMap:Record<string,string>;
 surfaces:Array<{entityId:string;boundaryLocalXZ:{coordinates:PointXZ[][][]}}>;
 roads:Array<{entityId:string;linesLocalXZ:PointXZ[][];segments:Array<{displayGroundReference:boolean}>}>;
};
/** The checked-in manifests have source DTOs; keep the JSON transport boundary unknown. */
async function readSource<T>(url:string):Promise<T>{const value:unknown=await fetch(url).then(r=>r.json());return value as T}
function materialMap(material:THREE.Material){return 'map' in material&&material.map instanceof THREE.Texture?material.map:undefined}
function materialColor(material:THREE.Material){return 'color' in material&&material.color instanceof THREE.Color?material.color:undefined}
function maskImage(value:unknown):CanvasImageSource|undefined{
 return value instanceof HTMLImageElement||value instanceof HTMLCanvasElement||value instanceof ImageBitmap?value:undefined;
}
function objectEntityId(object:THREE.Object3D){const id:unknown=object.userData.entityId;return typeof id==='string'?id:undefined}

export class CampusScene {
 exteriorViewPlanner=new ExteriorViewPlanner();
 navigationMode:NavigationMode='orbit';firstPerson:FirstPersonFlight;flightGround=new FlightGroundGuard();orbitBeforeFlight:OrbitSnapshot|null=null;returnFocus:'surface'|'saved'|null=null;flightGroundLift=0;
 disconnectLabelWheel:()=>void=()=>{};
 roadCoveragePlanner=new RoadCoveragePlanner(parseRoadProtection(roadProtectionSource));
 roadCoverageState:RoadCoverageDiagnostics|undefined;
 detailOrder=new StableDetailOrder();textureOrder=new StableDetailOrder();baselineVisibleIds=new Set<string>();
 scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(42,1,.5,9000);renderer:THREE.WebGLRenderer;controls:OrbitControls;geometry=new THREE.Group();terrain=new THREE.Group();selection=new THREE.Group();facilityPins=new THREE.Group();updates=new THREE.Group();masks=new SpatialMasks();currentFormCoverage=new CurrentFormCoverage(this.masks);textures=new AtomicTextures();detail:DetailStream;meshDetail:CampusMeshDetail;qualityMode:QualityMode='auto';qualityLevel:QualityLevel='high';automaticQuality=new AutomaticQuality('high');exteriors:CoherentExteriors;interior:WorldInterior;labels:HTMLDivElement;markers:Marker[]=[];footprints:BuildingFootprint[]=[];floorManifest:FloorManifest={floors:[]};facilityData:FacilityPoint[]=[];grid:HeightGrid|undefined;loaded=0;total=292;dead=false;raf=0;last=0;lastStats=0;observer:ResizeObserver;pointerDown=[0,0];pointerTravel=0;flight:Flight|null=null;selectedId='';opened:Entity|null=null;floorId='';homeBefore:ViewSnapshot|null=null;active=true;showLabels=true;history:ViewSnapshot[]=[];openingKey='';surfaces:SurfaceFeature[]=[];surfaceLines=new THREE.Group();outdoor:OutdoorEntities={roads:[],surfaces:[],surfaceNodeEntityMap:{}};sports=new THREE.Group();entrance=new THREE.Group();landmarks=new THREE.Group();groundGuard=new CameraGroundConstraint();groundSample:HeightSampler=()=>null;allowedFloor:AllowedFloorSampler|undefined;groundState:GroundMetrics|null=null;floorRequest=0;seaBlendTexture:THREE.Texture|null=null;seaBlendEnabled={value:1};waterColor=new THREE.Color(0x41666f);detailSamplers=new WeakMap<THREE.BufferGeometry,HeightSampler>();detailChoice=new StableDetailChoice();detailSeen=new Map<string,{score:number;lastSeen:number}>();detailCandidates:string[]=[];lastDetailUpdate=0;textureGroups:TextureDetailGroup[]=[];labelOcclusion=new Map<string,boolean>();lastOcclusion=0;labelOccluders:BuildingOccluder[]=[];motion=new MotionMetrics();anchorPan=new AnchoredPan();panControlsEnabled=true;locale:Locale='zh-Hans';panMode=false;safeFrameInsets={left:0,right:0,top:0,bottom:0};immersive=false;immersionProgress=0;immersionFrom=0;immersionStarted:number|null=null;immersionMedia=typeof matchMedia==='function'?matchMedia('(prefers-reduced-motion: reduce)'):null;pointerActive=false;lastInput=0;maskedTerrain=new WeakSet<THREE.Object3D>();qualityResourceSignature='';qualitySettledAt=0;detailPool=new DetailResourcePool(sharedDetailCaps.high);fixedResourceAt=-Infinity;fixedResourceCache={estimatedTextureBytes:0,textures:0,includes:'baseline thumbnails, fixed current forms/surfaces/terrain and active interiors',excludes:'dynamic pool, CPU image backing, geometry and driver overhead'};
 constructor(public host:HTMLElement,public registry:EntityRegistry,public options:Options){this.renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});if(datasetProfile.enhancements)this.masks.configureSourceProtection([...currentFormSourceProtection.boundsXZ.min,...currentFormSourceProtection.boundsXZ.max],this.renderer.capabilities.maxTextures);this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.setClearColor(0xbdd9e4);this.renderer.localClippingEnabled=true;host.appendChild(this.renderer.domElement);host.addEventListener('atlas:diagnostic-camera',this.diagnosticCamera);this.renderer.domElement.tabIndex=0;this.renderer.domElement.setAttribute('aria-label','统一校园沙盘，拖动旋转、滚轮缩放、点击实体');this.labels=document.createElement('div');this.labels.className='world-labels';host.appendChild(this.labels);this.disconnectLabelWheel=connectMapLabelWheel(this.labels,this.renderer.domElement);this.scene.add(this.geometry,this.terrain,this.selection,this.facilityPins,this.updates,this.surfaceLines,this.sports,this.entrance,this.landmarks,new THREE.HemisphereLight(0xffffff,0x8296a0,2));const water=new THREE.Mesh(new THREE.PlaneGeometry(30000,30000),new THREE.MeshBasicMaterial({color:this.waterColor}));water.name='sea-surface';water.rotation.x=-Math.PI/2;water.position.set(500,-.3,-1300);this.scene.add(water);this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;this.controls.dampingFactor=.14;this.controls.listenToKeyEvents(this.renderer.domElement);this.controls.maxPolarAngle=Math.PI*.487;this.controls.minDistance=8;this.controls.maxDistance=5100;this.controls.addEventListener('start',()=>this.flight=null);this.detail=new DetailStream(this.scene,this.camera,this.controls.target,this.renderer);this.detail.quality='detail';this.meshDetail=new CampusMeshDetail(this.scene,this.geometry,this.masks,()=>this.notify());this.exteriors=new CoherentExteriors(this.scene,this.masks,()=>this.notify());this.interior=new WorldInterior(this.scene,registry,()=>{this.updateFacilities();this.notify()});this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(host);this.renderer.domElement.addEventListener('contextmenu',this.preventMapContextMenu,true);this.renderer.domElement.addEventListener('pointerdown',this.down,true);this.renderer.domElement.addEventListener('pointerup',this.up,true);this.renderer.domElement.addEventListener('pointermove',this.move,true);this.renderer.domElement.addEventListener('pointercancel',this.cancelPointer,true);this.renderer.domElement.addEventListener('wheel',this.endPanForWheel,{capture:true,passive:true});this.renderer.domElement.addEventListener('lostpointercapture',this.cancelPointer);this.renderer.domElement.addEventListener('keydown',this.key);this.firstPerson=new FirstPersonFlight(this.camera,this.controls.target,this.renderer.domElement,()=>{this.writeImmersion();this.notify()});this.preset('home',false);this.resize();this.animate(0)}
 setLocale(locale:Locale){this.locale=locale;this.renderer.domElement.setAttribute('aria-label',t(locale,this.navigationMode==='fly'?'飞行地图，点击捕获鼠标，WASD移动，Space上升，Shift下降，Esc释放鼠标':'统一校园沙盘，拖动旋转、滚轮缩放、点击实体'));for(const m of this.markers){const e=this.registry.get(m.entityId);if(e){m.label.textContent=entityDisplayName(e,locale);m.label.title=entityDisplayName(e,locale)+' · '+classifyEntity(e,locale).label;}}}
 setActive(active:boolean){this.active=active;this.firstPerson.setSuspended(!active);}
 setFlightSpeed(speed:number){if([8,30,80].includes(speed)){this.firstPerson.motion.speed=speed;this.notify();}}
 setNavigationMode(mode:NavigationMode){
  if(mode===this.navigationMode||this.dead)return;
  if(mode==='fly'&&this.interior.loading)return;
  this.cancelPointer();this.flight=null;this.groundGuard.reset();this.flightGround.reset();this.flightGroundLift=0;
  if(mode==='fly'){
   this.orbitBeforeFlight=snapshotOrbit(this.camera,this.controls);this.navigationMode='fly';this.returnFocus=null;this.controls.enabled=false;this.firstPerson.setEnabled(true);
  }else{
   this.navigationMode='orbit';this.firstPerson.setEnabled(false);
   if(this.orbitBeforeFlight)this.returnFocus=returnToOrbit(this.camera,this.controls,this.orbitBeforeFlight,this.pickPanAnchor,(x,z,y)=>{const floor=this.allowedFloor?.(x,z,y),ground=floor??this.detailHeight(x,z)??this.groundSample(x,z);return ground===null?null:ground+.1;});
   this.orbitBeforeFlight=null;this.controls.enabled=true;
  }
  this.renderer.domElement.style.cursor=mode==='fly'?'crosshair':this.panMode?'grab':'';this.setLocale(this.locale);this.writeImmersion();this.notify();
 }
 setImmersive(enabled:boolean){if(this.immersive===enabled){this.writeImmersion();return;}if(this.anchorPan.active)this.cancelPointer();this.flight=null;const position=this.camera.position.clone(),target=this.controls.target.clone(),orientation=this.camera.quaternion.clone(),damping=this.controls.enableDamping;this.controls.enableDamping=false;this.controls.update();this.camera.position.copy(position);this.controls.target.copy(target);this.camera.quaternion.copy(orientation);this.camera.updateMatrixWorld();this.controls.enableDamping=damping;this.immersive=enabled;this.immersionFrom=this.immersionProgress;this.immersionStarted=null;if(this.immersionMedia?.matches)this.immersionProgress=enabled?1:0;this.writeImmersion();}
 writeImmersion(){this.applySafeFrameProjection();if(this.anchorPan.active)this.anchorPan.reproject(this.camera,this.controls.target,this.renderer.domElement.getBoundingClientRect());this.host.closest<HTMLElement>('.atlas-app')?.style.setProperty('--immersion',String(this.immersionProgress));this.labels.style.opacity=String(1-this.immersionProgress);this.labels.style.visibility=this.immersionProgress>=1?'hidden':'';this.labels.inert=this.immersive||this.immersionProgress>=1||this.firstPerson?.captured===true;this.labels.style.pointerEvents=this.labels.inert?'none':'';this.host.dataset.immersionState=JSON.stringify({target:this.immersive,progress:this.immersionProgress,viewport:this.viewportStats()});}
 advanceImmersion(time:number){const target=this.immersive?1:0;if(this.immersionProgress===target)return;if(this.immersionMedia?.matches)this.immersionProgress=target;else{this.immersionStarted??=time;const fraction=Math.max(0,Math.min(1,(time-this.immersionStarted)/300)),ease=fraction*fraction*(3-2*fraction);this.immersionProgress=this.immersionFrom+(target-this.immersionFrom)*ease;}this.writeImmersion();}
 setQuality(mode:QualityMode){this.qualityMode=mode;this.automaticQuality=new AutomaticQuality(initialQualityLevel(navigator.hardwareConcurrency||0,this.renderer.capabilities.maxTextureSize));this.applyQuality(mode==='auto'?this.automaticQuality.level:mode);}
 applyQuality(level:QualityLevel){this.qualityLevel=level;const p=qualityProfiles[level];this.renderer.setPixelRatio(Math.min(devicePixelRatio,p.dpr));this.resize();this.detail.terrainLimit=p.terrainTiles;this.detail.last=0;this.lastDetailUpdate=0;this.updateDetails(performance.now(),true);this.notify();}
 setSafeFrameInsets(insets:SafeFrameInsets){const value=(n:number|undefined)=>Number.isFinite(n)?Math.max(0,n!):0;this.safeFrameInsets={left:value(insets.left),right:value(insets.right),top:value(insets.top),bottom:value(insets.bottom)};this.writeImmersion();this.notify();}
 applySafeFrameProjection(){const w=this.host.clientWidth,h=this.host.clientHeight;if(!w||!h)return;this.camera.aspect=w/h;const factor=1-this.immersionProgress,insets={left:this.safeFrameInsets.left*factor,right:this.safeFrameInsets.right*factor,top:this.safeFrameInsets.top*factor,bottom:this.safeFrameInsets.bottom*factor};const left=Math.min(insets.left,Math.max(0,w-1)),right=Math.min(insets.right,Math.max(0,w-left-1)),top=Math.min(insets.top,Math.max(0,h-1)),bottom=Math.min(insets.bottom,Math.max(0,h-top-1));if(left||right||top||bottom)this.camera.setViewOffset(w,h,(right-left)/2,(bottom-top)/2,w,h);else{this.camera.clearViewOffset();this.camera.updateProjectionMatrix();}}
 resize(){const w=this.host.clientWidth,h=this.host.clientHeight;if(!w||!h)return;const dpr=Math.min(devicePixelRatio,qualityProfiles[this.qualityLevel].dpr);if(this.renderer.getPixelRatio()!==dpr)this.renderer.setPixelRatio(dpr);this.renderer.setSize(w,h);this.applySafeFrameProjection();}
 viewportStats(){const r=this.renderer.domElement.getBoundingClientRect();this.camera.updateMatrixWorld();const p=this.controls.target.clone().project(this.camera),canvasCenter=[r.left+r.width/2,r.top+r.height/2],v=this.camera.view,safeCenter=v?.enabled?[canvasCenter[0]-v.offsetX*r.width/v.width,canvasCenter[1]-v.offsetY*r.height/v.height]:canvasCenter.slice();return {left:r.left,top:r.top,width:r.width,height:r.height,center:safeCenter,canvasCenter,safeCenter,targetPixel:[r.left+(p.x+1)*r.width/2,r.top+(1-p.y)*r.height/2],targetNdc:p.toArray()};}
 notify(){if(this.dead)return;this.updateOpening();this.currentFormResidency?.setOpened(this.opened?this.registry.buildingSource(this.opened):'');this.updateBuildingSelection();const s:SceneState={navigation:{mode:this.navigationMode,flight:this.firstPerson.stats(),returnFocus:this.returnFocus,groundLift:this.flightGroundLift},loaded:this.loaded,total:this.total,buildingId:this.opened?.entityId||'',floorId:this.floorId,loadingFloor:this.interior.loading,selectedId:this.selectedId,exterior:this.exteriors.stats(),detailPool:this.detailPool.stats(this.detailMemoryBytes()),roadCoverage:this.roadCoverageState,fixedResources:this.fixedResourceStats(),currentFormResidency:this.currentFormResidency?.stats(),terrainTiles:this.detail.terrainObjects.size,cacheFloors:this.interior.cache.size,cacheMiB:+(this.interior.bytes/1048576).toFixed(1),textures:this.renderer.info.memory.textures,geometries:this.renderer.info.memory.geometries,triangles:this.renderer.info.render.triangles,camera:this.camera.position.toArray().map(v=>+v.toFixed(3)),target:this.controls.target.toArray().map(v=>+v.toFixed(3)),cadAnchor:typeof this.interior.root.userData.cadAnchor==='string'?this.interior.root.userData.cadAnchor:'',quality:{mode:this.qualityMode,level:this.qualityLevel,dpr:this.renderer.getPixelRatio(),initialLevel:this.automaticQuality.ceiling,cores:navigator.hardwareConcurrency,maxTextureSize:this.renderer.capabilities.maxTextureSize,maxFragmentTextures:this.renderer.capabilities.maxTextures,adaptation:this.automaticQuality.stats()},sourceProtection:this.masks.samplerStats(),meshDetail:this.meshDetail.stats(),motion:this.motion.stats(),pan:this.anchorPan.stats(),immersion:{target:this.immersive,progress:this.immersionProgress},viewport:this.viewportStats(),ground:this.groundState,surfaceMeshes:this.sports.children.length+this.entrance.children.length,landmarks:this.landmarks.children.map(g=>String(g.userData.entityId)),textureDetail:this.textures.stats(),detailCandidates:this.detailCandidates,currentForms:this.updates.children.filter(g=>g.visible).map(g=>String(g.userData.buildingId)),currentFormAssets:[...this.currentFormSets].filter(set=>set.state!=='disposed').map(set=>({sha256:set.manifest.asset.sha256,bytes:set.manifest.asset.bytes,buildingIds:set.members.map(m=>m.descriptor.buildingId)}))};this.host.dataset.sceneState=JSON.stringify(s);this.options.change(s)}
  async load(){const loader=new GLTFLoader();const [grid,manifest,fp,floors,facilities]=await Promise.all([readSource<HeightGrid>('/terrain/height-grid-5m.json'),readSource<PreviewManifest>('/models/preview-manifest.json'),readSource<BuildingFootprintManifest>('/data/building-footprints.json'),readSource<FloorManifest>('/interiors/manifest.json'),readSource<FacilityPoint[]>('/data/entity-registry-pois.json'),this.detail.init(),this.meshDetail.init(),this.exteriors.init(),this.textures.init()]);if(this.dead)return;this.grid=grid;this.groundSample=createGridGroundSampler(grid);this.footprints=fp.footprints;this.labelOccluders=createBuildingOccluders(this.footprints);this.floorManifest=floors;this.facilityData=facilities;this.total=manifest.tiles.length;this.prepareTextureGroups();const t=await loader.loadAsync('/terrain/terrain.glb');if(this.dead){releaseObject(t.scene);return}this.terrain.add(t.scene);this.detail.setCoarse(t.scene);this.masks.apply(t.scene,'terrain');this.makeMarkers();if(datasetProfile.enhancements){void this.loadSurfaces();void this.loadEntrance();void this.loadGroundReference();void this.loadLandmarks();void this.loadCurrentForms();}
 const queue=manifest.tiles.slice().sort((a,b)=>Math.hypot(a.center[0]-500,a.center[2]+1400)-Math.hypot(b.center[0]-500,b.center[2]+1400));let next=0;const worker=async()=>{while(next<queue.length&&!this.dead){const tile=queue[next++];try{const gltf=await loader.loadAsync('/models/'+tile.url);if(this.dead){releaseObject(gltf.scene);return}gltf.scene.applyMatrix4(new THREE.Matrix4().fromArray(tile.matrix));gltf.scene.name=tile.id;gltf.scene.traverse(o=>{if(!isMesh(o))return;const isArray=Array.isArray(o.material);const materials=(Array.isArray(o.material)?o.material:[o.material]).map(m=>{const map=materialMap(m);if(map){map.generateMipmaps=true;map.minFilter=THREE.LinearMipmapLinearFilter;map.anisotropy=8}const mat=new THREE.MeshBasicMaterial({map,color:materialColor(m),side:THREE.DoubleSide,vertexColors:!!o.geometry.attributes.color});this.textures.register(tile.id,mat,gltf.parser.associations.get(m)?.materials??0);m.dispose();return mat});o.material=isArray?materials:materials[0]});this.masks.apply(gltf.scene,'baseline');this.geometry.add(gltf.scene);this.meshDetail.syncBaseline()}catch{this.options.error('部分外观暂未载入，可刷新重试')}this.loaded++;this.notify()}};await Promise.all(Array.from({length:4},worker));if(this.dead)return;
 try{const c=await readSource<CoverageManifest>('/terrain/coverage/manifest.json');const b=c.boundsXZ||c.bounds;await this.masks.load('coverage','/terrain/coverage/'+(c.url||c.maskUrl),[b.min[0],b.min[1],b.max[0],b.max[1]])}catch{this.options.error('摄影覆盖边界暂未载入')}
 if(datasetProfile.enhancements)try{const sea=await readSource<RasterManifest>('/surfaces/sea-edge/manifest.json');const texture=await new THREE.TextureLoader().loadAsync('/surfaces/sea-edge/'+sea.url);if(this.dead){texture.dispose();return}this.seaBlendTexture=texture;applySeaEdgeBlend(this.geometry,texture,[sea.minX,sea.minZ,sea.maxX,sea.maxZ],this.waterColor,this.seaBlendEnabled)}catch{}
 this.geometry.updateMatrixWorld(true);const ray=new THREE.Raycaster();ray.ray.direction.set(0,-1,0);for(const m of this.markers){ray.ray.origin.set(m.position.x,500,m.position.z);const hit=ray.intersectObjects(this.geometry.children,true)[0];if(hit)m.position.y=Math.max(m.position.y,hit.point.y+6)}this.notify()}
 async loadSurfaces(){try{const [manifest,mask,outdoor]=await Promise.all([readSource<SurfaceManifest>('/surfaces/sports/manifest.json'),readSource<RasterManifest>('/surfaces/sports/sports-surface-mask.json'),readSource<OutdoorEntities>('/data/outdoor-entities.json')]);this.outdoor=outdoor;const gltf=await new GLTFLoader().loadAsync('/surfaces/sports/'+manifest.url);if(this.dead){releaseObject(gltf.scene);return}const texture=await new THREE.TextureLoader().loadAsync('/surfaces/sports/'+mask.url);if(this.dead){texture.dispose();releaseObject(gltf.scene);return}gltf.scene.traverse(o=>{if(isMesh(o)){const sourceEntityId=objectEntityId(o);o.userData.surfaceNodeId=sourceEntityId;o.userData.entityId=sourceEntityId?outdoor.surfaceNodeEntityMap[sourceEntityId]:undefined;for(const material of Array.isArray(o.material)?o.material:[o.material]){material.side=THREE.DoubleSide;const map=materialMap(material);if(map)map.anisotropy=8}}});this.surfaces=manifest.features;this.sports.add(gltf.scene);this.masks.set('surface',texture,[mask.minX,mask.minZ,mask.maxX,mask.maxZ]);this.masks.slots.surface.maxY.value=Math.max(...manifest.features.map(f=>f.meshBounds.max[1]))+.75;this.notify()}catch{this.options.error('运动场正射地表暂未载入')}}
 async loadEntrance(){const base='/surfaces/entrance/';try{const manifest=await readSource<SurfaceManifest&{mask:RasterManifest&{discardHeightClearanceMeters:number}}> (base+'manifest.json');const gltf=await new GLTFLoader().loadAsync(base+manifest.url);if(this.dead){releaseObject(gltf.scene);return}const m=manifest.mask;const texture=await new THREE.TextureLoader().loadAsync(base+m.url);if(this.dead){texture.dispose();releaseObject(gltf.scene);return}gltf.scene.traverse(o=>{if(isMesh(o))for(const material of Array.isArray(o.material)?o.material:[o.material]){material.side=THREE.DoubleSide;const map=materialMap(material);if(map)map.anisotropy=8}});this.entrance.add(gltf.scene);this.masks.setSurface('surface2',texture,[m.minX,m.minZ,m.maxX,m.maxZ],m.discardHeightClearanceMeters);this.notify()}catch{this.options.error('入口地面细节暂未载入，请刷新重试')}}
 async loadGroundReference(){const base='/surfaces/ground-reference/';try{const m=await readSource<RasterManifest&{bandMeters:number}>(base+'manifest.json');const texture=await new THREE.TextureLoader().loadAsync(base+m.url);if(this.dead){texture.dispose();return}this.masks.setGroundReference(texture,[m.minX,m.minZ,m.maxX,m.maxZ],m.bandMeters);this.notify()}catch{this.options.error('地面衔接细节暂未载入，请刷新重试')}}
 async loadLandmarks(){const base='/models/landmarks/sundial/';try{const manifest=await readSource<{entityId:string;url:string}>(base+'manifest.json');const gltf=await new GLTFLoader().loadAsync(base+manifest.url);if(this.dead){releaseObject(gltf.scene);return}gltf.scene.userData.entityId=manifest.entityId;gltf.scene.traverse(o=>{o.userData.entityId=manifest.entityId});this.landmarks.add(gltf.scene);this.notify()}catch{this.options.error('地标外观暂未载入，请刷新重试')}}
 currentFormSets=new Set<CurrentFormSet>();
 currentFormAbort=new AbortController();
 currentFormResidency=new CurrentFormResidency(()=>{this.fixedResourceAt=-Infinity;this.notify()});
 async loadCurrentForms(){
  // Only small descriptors load here. Complete original assets are admitted
  // by the shared projector and fixed-cost residency planner below.
  await Promise.all([
   this.registerCurrentFormSet('/models/current-forms/innovation/'),
   this.registerCurrentFormSet('/models/current-forms/ivillage-rebuild/',currentFormSourceProtection),
   // The uphill Hall II bridge is an independently selectable space. It has
   // no source mask until exact ownership of the old roof-band gap is proven.
   this.registerCurrentFormSet('/models/current-forms/hall2-corridor/'),
  ]);
  if(this.dead)return;
  // This is a bounded fixed-asset allowance, not an addition to the three
  // dynamic source lanes or a claim about total GPU/process memory.
  this.currentFormResidency.setBudget(this.currentFormResidency.catalogBytes());
  this.currentFormResidency.update(this.camera,this.host.clientHeight,performance.now(),this.opened?this.registry.buildingSource(this.opened):'');
 }
 async registerCurrentFormSet(base:string,p?:typeof currentFormSourceProtection){
  const controller=new AbortController(),cancel=()=>controller.abort(),signal=this.currentFormAbort.signal;
  signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel();
  const timer=setTimeout(cancel,120000);
  try{
   const response=await fetch(base+'manifest.json',{signal:controller.signal});
   if(!response.ok)throw new Error('Current form manifest unavailable');
   const input:unknown=await response.json();
   if(controller.signal.aborted||this.dead)return;
   const manifest=parseCurrentFormSetManifest(input);
   const fixedTextureBytes=currentFormFixedTextureBytes(input,manifest,p?p.width*p.height*4:0);
   this.currentFormResidency.register({id:base,manifest,fixedTextureBytes,load:async signal=>{
    const ready=await this.loadCurrentFormSet(base,p,{manifest:input,signal,fixedTextureBytes});
    if(!ready)throw new Error('Current form did not become ready');
    return ready;
   }});
  }catch{if(!this.dead&&!controller.signal.aborted)this.options.error('现状建筑整组外观暂未载入，请刷新重试')}
  finally{clearTimeout(timer);signal.removeEventListener('abort',cancel)}
 }
 async loadCurrentFormSet(base:string,p?:typeof currentFormSourceProtection,demand?:{manifest:unknown;signal:AbortSignal;fixedTextureBytes:number}){
  let ready:CurrentFormSet|undefined,protection:THREE.DataTexture|undefined,protectionInstalled=false;
  const controller=new AbortController(),sceneSignal=this.currentFormAbort.signal;
  const cancel=()=>controller.abort();
  sceneSignal.addEventListener('abort',cancel,{once:true});
  demand?.signal.addEventListener('abort',cancel,{once:true});
  if(sceneSignal.aborted||demand?.signal.aborted)cancel();
  // One deadline includes metadata and post-GLB protection, not just parsing.
  const timer=setTimeout(cancel,120000);
  const check=()=>{if(controller.signal.aborted||this.dead)throw new DOMException('Current form transaction cancelled','AbortError')};
  try{
   check();
   let manifest:unknown=demand?.manifest;
   if(!demand){
    const manifestResponse=await fetch(base+'manifest.json',{signal:controller.signal});
    if(!manifestResponse.ok)throw new Error('Current form manifest unavailable');
    manifest=await manifestResponse.json();
   }
   check();
   ready=await loadCurrentFormSet(manifest,{baseURL:base,signal:controller.signal});check();
   if(p){
    const response=await fetch(base+p.url,{signal:controller.signal});
    if(!response.ok)throw new Error('Source protection unavailable');
    const bytes=await response.arrayBuffer();check();
    if(bytes.byteLength!==p.width*p.height*4)throw new Error('Source protection size mismatch');
    const digest=await crypto.subtle.digest('SHA-256',bytes);
    const hash=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
    if(hash!==p.sha256)throw new Error('Source protection hash mismatch');
    check();
    protection=new THREE.DataTexture(new Uint8Array(bytes),p.width,p.height);
    if(ready.members.some(m=>!m.descriptor.mask||!m.mask))
     throw new Error('Protected replacement set requires every member mask');
   }
   check();
   // Process the whole set together so shared photographic materials are
   // converted once; mapped roof vertex occlusion stays intact as COLOR_0.
   preparePhotographicMaterials(ready.root,this.renderer.capabilities.getMaxAnisotropy());
   if(demand&&ready.textureBytes()+(p?p.width*p.height*4:0)>demand.fixedTextureBytes)
    throw new Error('Current form decoded textures exceed its fixed reservation');
   for(const member of ready.members){
    // Residency and opening one member hide complete roots. Shared drawing
    // polygons must not carve independently owned neighbouring buildings.
    member.root.userData.visibilityLifecycle='complete-building-root';
    member.root.userData.currentFormAssetSHA256=ready.manifest.asset.sha256;
   }
   const ids=ready.members.filter(m=>m.descriptor.mask).map(m=>m.descriptor.buildingId);
   ready.commit(this.updates,{
    activate:members=>{
     if(p&&protection){
      this.masks.setSourceProtection(protection,[...p.boundsXZ.min,...p.boundsXZ.max],p.groundBandMeters);
      protectionInstalled=true;
     }
     const masks=members.flatMap(m=>m.descriptor.mask&&m.mask?[{id:m.descriptor.buildingId,descriptor:m.descriptor.mask,texture:m.mask}]:[]);
     if(masks.length)this.currentFormCoverage.addBatch(masks);
    },
    deactivate:()=>{
     if(ids.length)this.currentFormCoverage.removeBatch(ids);
     if(protectionInstalled)this.masks.enable('sourceProtection',false);
    },
   });
   this.currentFormSets.add(ready);this.fixedResourceAt=-Infinity;this.notify();return ready;
  }catch(error){
   ready?.dispose();if(protection&&!protectionInstalled)protection.dispose();
   if(demand)throw error;
   if(!this.dead)this.options.error('现状建筑整组外观暂未载入，请刷新重试');
  }finally{
   clearTimeout(timer);sceneSignal.removeEventListener('abort',cancel);
   demand?.signal.removeEventListener('abort',cancel);
  }
 }
 exteriorRangeDomains(){return this.exteriors.bundles.flatMap(bundle=>{const entityId=exteriorEntityId(bundle);if(this.registry.get(entityId)?.type!=='zone')return [];return extraBuildingDomains.auditOnlyAggregateDomains.filter(d=>d.entityId===entityId&&d.physicalDomainId===bundle.physicalDomainId).map(d=>({...d,parts:d.parts as PolygonPart[],minY:Math.min(d.minY,bundle.bounds.min[1]),maxY:bundle.bounds.max[1],sourceObjectIds:bundle.objects.map(o=>o.id)}));});}
 detailBounds(buildingId:string|undefined,fallback:Bounds3):Bounds3{if(!buildingId)return fallback;const fp=this.footprints.find(f=>f.officialBuildingId===buildingId);if(!fp)return fallback;const b=fp.boundsXZ,ground=this.height((b.min[0]+b.max[0])/2,(b.min[1]+b.max[1])/2);return {min:[b.min[0],fp.minObservedFloorZ??ground,b.min[1]],max:[b.max[0],Math.max(fp.maxObservedFloorZ??ground+15,ground+5)+5,b.max[1]]}}
 prepareTextureGroups(){
  this.textureGroups=this.textures.regions.map(r=>({id:r.id,buildingId:r.buildingId,bounds:this.detailBounds(r.buildingId,{min:[r.minX,0,r.minZ],max:[r.maxX,200,r.maxZ]}),textures:r.textures}));
  const cells=new Map<string,typeof this.textures.catalog extends Map<string,infer T>?T[]:never>();
  for(const tile of this.textures.catalog.values()){const id=`context:${Math.floor(tile.center[0]/300)}:${Math.floor(tile.center[2]/300)}`,tiles=cells.get(id)||[];tiles.push(tile);cells.set(id,tiles)}
  for(const [id,tiles] of cells){
   const ids=new Set(tiles.map(t=>t.id)),wholeBuildings=this.textures.regions.filter(r=>r.baselineIds.some(tile=>ids.has(tile)));
   const box=new THREE.Box3();for(const tile of tiles)box.union(new THREE.Box3(new THREE.Vector3(...tile.bounds.min),new THREE.Vector3(...tile.bounds.max)));
   this.textureGroups.push({id,bounds:{min:box.min.toArray(),max:box.max.toArray()},textures:[...tiles.flatMap(t=>Object.values(t.materials)),...wholeBuildings.flatMap(r=>r.textures)]});
  }
 }
 detailMemoryBytes():DetailResourceBytes{return {exterior:this.exteriors.memoryBytes(),mesh:this.meshDetail.memoryBytes(),original:this.textures.cacheBytes+this.textures.reservedBytes}}
 fixedResourceStats(){
  const now=performance.now();if(now-this.fixedResourceAt<1500){const current=this.currentFormResidency?.stats();return {...this.fixedResourceCache,currentFormBudgetBytes:current?.targetBudgetBytes??0,currentFormChargedBytes:current?.chargedBytes??0,currentFormPendingBytes:current?.pendingBytes??0}}this.fixedResourceAt=now;
  const textures=new Set<THREE.Texture>(this.textures.bindings.map(binding=>binding.low));
  for(const root of [this.terrain,this.detail.group,this.updates,this.sports,this.entrance,this.landmarks,this.interior.root])root.traverse(object=>{if(isMesh(object))for(const material of Array.isArray(object.material)?object.material:[object.material])for(const value of Object.values(material))if(value instanceof THREE.Texture)textures.add(value)});
  const dynamic=new Set<string>([...replacementSlots,...partialSlots,'partialCoverage']);for(const [name,slot]of Object.entries(this.masks.slots))if(!dynamic.has(name)&&slot.enabled.value)textures.add(slot.texture.value);if(this.seaBlendTexture)textures.add(this.seaBlendTexture);
  let estimatedTextureBytes=0;for(const texture of textures){const image:unknown=texture.image;if(image&&typeof image==='object'&&'width'in image&&'height'in image&&typeof image.width==='number'&&typeof image.height==='number')estimatedTextureBytes+=texture.generateMipmaps?textureMipBytes(image.width,image.height):image.width*image.height*4}
  this.fixedResourceCache={...this.fixedResourceCache,estimatedTextureBytes,textures:textures.size};const current=this.currentFormResidency?.stats();return {...this.fixedResourceCache,currentFormBudgetBytes:current?.targetBudgetBytes??0,currentFormChargedBytes:current?.chargedBytes??0,currentFormPendingBytes:current?.pendingBytes??0};
 }
 updateDetails(time:number,force=false){
  if(!force&&time-this.lastDetailUpdate<350)return;this.lastDetailUpdate=time;
  this.currentFormResidency?.update(this.camera,this.host.clientHeight,time,this.opened?this.registry.buildingSource(this.opened):'');
  const profile=qualityProfiles[this.qualityLevel],cap=sharedDetailCaps[this.qualityLevel];
  const detailOrder=this.detailOrder??=new StableDetailOrder(),textureOrder=this.textureOrder??=new StableDetailOrder();
  const candidates=visibleDetails(this.camera,this.exteriors.bundles.map(b=>({id:b.id,bounds:this.detailBounds(exteriorBuildingId(b),b.bounds)})),this.host.clientHeight,profile.detailPixels,{ids:new Set(detailOrder.ids)});
  const ranked=detailOrder.rank(candidates);
  const priority=this.opened?this.exteriors.bundles.find(b=>exteriorEntityId(b)===this.opened!.entityId)?.id||'':'';
  const first=this.detailChoice.choose(candidates,time,this.exteriors.current?.bundle.id||'',priority);
  this.detailCandidates=ranked.map(candidate=>candidate.id).sort((a,b)=>Number(b===first)-Number(a===first));
  const exteriorCandidates=this.detailCandidates.map(id=>this.exteriors.bundles.find(b=>b.id===id)).filter((b):b is NonNullable<typeof b>=>!!b);
  // Geographic cells only rank demand. Each original atlas also needs a visible
  // baseline tile, independently of a previously reduced pool grant.
  const shownBaseline=new Set(this.geometry.children.filter(o=>o.visible).map(o=>o.name));
  const sourceTiles=[...this.textures.catalog.values()].filter(tile=>shownBaseline.has(tile.id));
  const visibleTiles=visibleDetails(this.camera,sourceTiles,this.host.clientHeight,0,{ids:this.baselineVisibleIds??new Set()});
  this.baselineVisibleIds=new Set(visibleTiles.map(tile=>tile.id));
  const visibleUrls=new Set(visibleTiles.flatMap(tile=>Object.values(this.textures.catalog.get(tile.id)!.materials).map(source=>source.url)));
  const textureGroups=this.textureGroups.map(group=>({...group,textures:group.textures.filter(source=>visibleUrls.has(source.url))})).filter(group=>group.textures.length);
  const textureCandidates=visibleDetails(this.camera,textureGroups,this.host.clientHeight,56,{ids:new Set(textureOrder.ids)});
  const ordered=textureOrder.rank(textureCandidates);
  const ceilings={exterior:profile.exteriorMiB*1048576,mesh:profile.meshMiB*1048576,original:profile.textureMiB*1048576};
  const nearExteriorPlan=this.exteriorViewPlanner.plan(exteriorCandidates,candidates,Math.min(cap,ceilings.exterior),cap);
  // Source centreline projection identifies the current continuous corridor.
  // Its exact terminal frontiers share the pool with complete nearby buildings;
  // unrelated road partitions do not become a campus-wide mandatory reservation.
  const roadCandidates=profile.meshMiB?visibleRoadClusters(this.camera,this.roadCoveragePlanner.manifest.clusters,this.host.clientHeight,(x,z)=>this.height(x,z)):[];
  const roadIds=new Set(roadCandidates.flatMap(candidate=>candidate.cluster.partitionIds));
  const possibleCoverage=this.meshDetail.previewCoveragePlan(this.camera,this.host.clientHeight,profile,roadIds);
  const fineById=new Map(possibleCoverage.choices.map(choice=>[choice.patch.id,choice]));
  const coverageBytes=(ids:ReadonlySet<string>)=>{
   if(!ids.size)return 0;
   const choices=[...ids].map(id=>fineById.get(id));
   return choices.every(choice=>choice!==undefined)?this.meshDetail.planBytes(choices):Infinity;
  };
  const roadPlan=this.roadCoveragePlanner.plan(roadCandidates,this.meshDetail.patches,coverageBytes,Math.max(0,cap-nearExteriorPlan.bytes));
  const protectedChoices=roadPlan.acceptedPartitionIds.map(id=>fineById.get(id)!);
  const protectedBytes=coverageBytes(new Set(roadPlan.acceptedPartitionIds));
  const exteriorPlan=protectedBytes?this.exteriorViewPlanner.plan(exteriorCandidates,candidates,Math.min(cap,ceilings.exterior),Math.max(0,cap-protectedBytes)):nearExteriorPlan;
  ceilings.exterior=exteriorPlan.budgetBytes;
  // Fine road coverage may use otherwise free pool space beyond a profile's
  // ordinary mesh ceiling; source size and the shared total cap stay unchanged.
  ceilings.mesh=Math.min(cap,Math.max(ceilings.mesh,protectedBytes));
  const meshPlan=this.meshDetail.previewPlan(this.camera,this.host.clientHeight,profile,Math.min(ceilings.mesh,cap-exteriorPlan.bytes),time,protectedChoices);
  const meshBytes=this.meshDetail.planBytes(meshPlan);
  const originalPlan=textureDetailPlan(textureGroups,ordered,Math.max(0,Math.min(ceilings.original,cap-exteriorPlan.bytes-meshBytes)));
  this.textures.releaseInvisibleSources(visibleUrls);
  this.detailPool.reconcile(cap,{exterior:exteriorPlan.bytes,mesh:meshBytes,original:originalPlan.bytes},ceilings,{
   exterior:{memoryBytes:()=>this.exteriors.memoryBytes(),setBudget:bytes=>this.exteriors.setBudget(bytes,this.qualityLevel==='smooth'?0:3,exteriorPlan.bundles)},
   mesh:{memoryBytes:()=>this.meshDetail.memoryBytes(),setBudget:bytes=>this.meshDetail.setBudget(bytes,meshPlan)},
   original:{memoryBytes:()=>this.textures.cacheBytes+this.textures.reservedBytes,setBudget:bytes=>this.textures.setBudget(bytes,profile.originalWorkers)},
  },force);
  const grants=this.detailPool.grants;
  this.exteriors.request(this.exteriors.previewPlan(exteriorPlan.bundles,grants.exterior).bundles);
  const requestedMesh=this.meshDetail.previewPlan(this.camera,this.host.clientHeight,profile,grants.mesh,time,protectedChoices);
  this.meshDetail.request(requestedMesh);
  const desiredFine=new Set(roadPlan.desiredPartitionIds);
  const acceptedFine=requestedMesh.filter(choice=>desiredFine.has(choice.patch.id)&&choice.key===fineById.get(choice.patch.id)?.key).map(choice=>choice.patch.id);
  this.roadCoverageState={...roadPlan,desiredFinePartitionIds:roadPlan.desiredPartitionIds,reservedFinePartitionIds:roadPlan.acceptedPartitionIds,acceptedFinePartitionIds:acceptedFine,readyFinePartitionIds:[...this.meshDetail.visible.values()].filter(choice=>desiredFine.has(choice.patch.id)&&choice.key===fineById.get(choice.patch.id)?.key).map(choice=>choice.patch.id),deferredFinePartitionIds:roadPlan.desiredPartitionIds.filter(id=>!acceptedFine.includes(id)),unavailableFinePartitionIds:roadPlan.desiredPartitionIds.filter(id=>!fineById.has(id)),desiredFineBytes:Number.isFinite(roadPlan.desiredBytes)?roadPlan.desiredBytes:null,reservedFineBytes:protectedBytes,profileMeshBudgetBytes:profile.meshMiB*1048576,grantedMeshBudgetBytes:grants.mesh,poolCapBytes:cap,exteriorPlanBytes:exteriorPlan.bytes};
  const accepted=textureDetailPlan(textureGroups,ordered,Math.min(originalPlan.bytes,grants.original));this.textures.request(accepted.key,accepted.images);
 }
 detailHeight=(x:number,z:number)=>{let value:number|null=null;for(const root of this.detail.terrainObjects.values()){root.traverse(o=>{if(value!==null||!isMesh(o))return;let sample=this.detailSamplers.get(o.geometry);if(!sample){try{sample=createRegularTerrainPatchSampler(o.geometry.getAttribute('position'),1);this.detailSamplers.set(o.geometry,sample)}catch{return}}value=sample(x,z)})}return value};
 height(x:number,z:number){if(!this.grid)return 0;const g=this.grid,c=Math.round((x+844800-g.first_easting)/g.easting_step),r=Math.round((820500-z-g.first_northing)/g.northing_step);return c>=0&&r>=0&&c<g.columns&&r<g.rows?g.heights[r*g.columns+c]||0:0}
 entityPosition(e:Entity):THREE.Vector3|null{const p=e.representations?.find(p=>p.position)?.position;if(p)return new THREE.Vector3(p[0],typeof p[1]==='number'&&Number.isFinite(p[1])?p[1]:this.height(p[0],p[2]),p[2]);const xz=e.representations?.find(r=>r.boundsXZ)?.boundsXZ;if(xz){const x=(xz.min[0]+xz.max[0])/2,z=(xz.min[1]+xz.max[1])/2;return new THREE.Vector3(x,this.height(x,z),z)}const b=e.bounds||e.representations?.find(r=>r.bounds)?.bounds;if(b)return new THREE.Box3(new THREE.Vector3(...b.min as [number,number,number]),new THREE.Vector3(...b.max as [number,number,number])).getCenter(new THREE.Vector3());const legacy=this.registry.legacy(e),fp=this.footprints.find(f=>f.catalogId===legacy);if(fp){const pts=fp.parts.flatMap(p=>p.rings.flat());const x=pts.reduce((s:number,p:number[])=>s+p[0],0)/pts.length,z=pts.reduce((s:number,p:number[])=>s+p[1],0)/pts.length;return new THREE.Vector3(x,this.height(x,z),z)}return null}
 makeMarkers(){for(const e of this.registry.entities.filter(e=>e.type==='building'||e.type==='outdoor_area'||e.type==='zone'||e.type==='facility'&&e.function==='landmark')){const position=this.entityPosition(e);if(!position)continue;position.y+=6;const label=document.createElement('button');label.className='entity-label';label.textContent=entityDisplayName(e,this.locale);label.title=entityDisplayName(e,this.locale)+' · '+classifyEntity(e,this.locale).label;label.dataset.entityType=classifyEntity(e).category;label.addEventListener('click',()=>this.options.select(e.entityId));this.labels.appendChild(label);this.markers.push({entityId:e.entityId,position,label})}}
 labelUnobstructed(marker:Marker){const entity=this.registry.get(marker.entityId),owner=entity&&this.registry.building(entity);return !markerOccluded(this.camera.position.toArray(),marker.position.toArray(),this.labelOccluders,owner?this.registry.buildingSource(owner):undefined);}
 buildingFloors(e:Entity):FloorManifestEntry[]{if(e.type!=='building')return [];const source=this.registry.buildingSource(e);return this.floorManifest.floors.filter(f=>f.buildingId===source)}
 async selectEntity(entityId:string,move=true){if(move)this.setNavigationMode('orbit');if(!entityId){this.clearSelection();return}const e=this.registry.get(entityId);if(!e)return;this.selectedId=e.entityId;const building=this.registry.building(e),floor=this.registry.floor(e);if(floor||e.type==='connector'&&e.stops?.length){const wanted=floor?this.registry.floorSource(floor):e.stops?.find(s=>s.sourceFloorId===this.floorId)?.sourceFloorId||e.stops?.[0].sourceFloorId;if(building&&(!this.opened||this.opened.entityId!==building.entityId))await this.openBuilding(building,wanted);else if(wanted&&this.floorId!==wanted)await this.setFloor(wanted);if(this.selectedId!==e.entityId)return;const box=this.interior.select(e.entityId);if(e.type==='floor'&&move)this.floorView();if(box&&move){const c=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3()),d=Math.max(size.x,size.z,18);const eye=c.clone().add(new THREE.Vector3(d*.7,d*1.2,d));if(e.type==='connector'||this.allowedFloor&&this.allowedFloor(eye.x,eye.z,c.y)===null)eye.copy(c).add(new THREE.Vector3(0,d*1.5,.1));this.fly(eye,c)}else if(e.type==='facility'&&move){const p=this.entityPosition(e);if(p)this.fly(p.clone().add(new THREE.Vector3(18,25,20)),p)}this.notify();return}
 if(this.opened&&building?.entityId!==this.opened.entityId)this.closeBuilding(false);releaseObject(this.selection);this.selection.clear();const legacy=this.registry.legacy(e),fp=this.footprints.find(f=>f.catalogId===legacy);if(fp&&e.type!=='building')this.outline(fp.parts,fp.maxObservedFloorZ||this.entityPosition(e)?.y||0);this.outlineOutdoor(e);const p=this.entityPosition(e)||this.entityPosition(building||e);if(p&&move){this.remember();this.fly(p.clone().add(new THREE.Vector3(180,180,220)),p)}this.notify()}
 async openBuilding(building:Entity,initialFloor?:string){this.setNavigationMode('orbit');const floors=this.buildingFloors(building);if(!floors.length)return;if(!this.opened)this.homeBefore=this.snapshot();this.opened=building;const source=this.registry.buildingSource(building),fp=this.footprints.find(f=>f.officialBuildingId===source);if(fp){this.openingKey='';this.updateOpening(true)}else{this.masks.enable('opening',false);this.options.error('该建筑缺少可核实外壳边界')}releaseObject(this.selection);this.selection.clear();const ready=await this.setFloor(initialFloor||(floors.find(f=>f.isDefault)||floors[0]).id);if(!ready||this.opened!==building)return false;if(!initialFloor)this.floorView();this.notify()}
 updateOpening(force=false){if(!this.opened)return;const source=this.registry.buildingSource(this.opened),fp=this.footprints.find(f=>f.officialBuildingId===source),bundle=this.exteriors.visible.get(this.exteriors.bundles.find(b=>exteriorEntityId(b)===this.opened!.entityId)?.id||'')?.bundle;const key=source+'/'+this.floorId+'/'+(bundle?.id||'');if(!force&&this.openingKey===key)return;this.openingKey=key;if(!fp)return;const replacement=this.exteriors.maskFor(this.opened.entityId),image=replacement?maskImage(replacement.texture.image):undefined;this.masks.polygon('opening',fp.parts,image&&replacement?{image,bounds:replacement.bounds}:undefined);const f=this.floorManifest.floors.find(f=>f.id===this.floorId);this.masks.slots.opening.minY.value=f?Math.min(...f.sourceZValues)-.2:-100000}
 async setFloor(id:string,stack=false){this.setNavigationMode('orbit');if(!this.opened)return false;const request=++this.floorRequest,building=this.opened;this.allowedFloor=undefined;this.masks.enable('interiorTerrain',false);this.floorId=id;this.updateOpening(true);await this.interior.show(this.buildingFloors(this.opened),id,stack);if(this.dead||this.opened!==building||request!==this.floorRequest||this.floorId!==id||this.interior.floorId!==id||this.interior.loading)return false;const fp=this.footprints.find(f=>f.officialBuildingId===this.registry.buildingSource(building));const current=this.interior.data.find(f=>f.id===this.floorId);if(fp&&current&&!this.interior.loading){this.allowedFloor=createAllowedFloorSampler(fp.parts,current.rooms);this.masks.polygon('interiorTerrain',current.rooms);this.masks.slots.interiorTerrain.minY.value=Math.min(...current.rooms.map(r=>r.heightSourceZ))-.2}this.updateFacilities();this.notify();return true}
 floorView(top=false){if(!this.interior.data.length)return;const box=new THREE.Box3().setFromObject(this.interior.root),p=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3()),d=Math.max(s.x,s.z,60);this.fly(p.clone().add(new THREE.Vector3(top?0:d*.35,top?d*1.45:d*.8,top?.1:d*.8)),p)}
 closeBuilding(restore=true){this.floorRequest++;this.masks.enable('interiorTerrain',false);this.opened=null;this.allowedFloor=undefined;this.floorId='';this.interior.stop();this.masks.enable('opening',false);releaseObject(this.facilityPins);this.facilityPins.clear();if(restore&&this.homeBefore)this.fly(new THREE.Vector3(...this.homeBefore.camera as [number,number,number]),new THREE.Vector3(...this.homeBefore.target as [number,number,number]));this.homeBefore=null;this.notify()}
 updateFacilities(){releaseObject(this.facilityPins);this.facilityPins.clear();if(!this.opened||this.interior.loading)return;for(const f of this.facilityData.filter(p=>this.interior.data.some(d=>d.id===p.floorId))){const m=new THREE.Mesh(new THREE.SphereGeometry(.7,10,8),new THREE.MeshBasicMaterial({color:0xd88f28,depthTest:false}));m.position.fromArray(f.position);m.position.y+=1;m.userData.entityId=f.entityId;m.renderOrder=30;this.facilityPins.add(m)}}
 clearSelection(){this.selectedId='';releaseObject(this.selection);this.selection.clear();this.selection.userData.sourceKey='';this.interior.select('');this.notify()}
 updateBuildingSelection(){
  const entity=this.registry.get(this.selectedId);if(entity?.type!=='building')return;
  const buildingId=this.registry.buildingSource(entity),sources:BuildingSelectionSource[]=[];
  if(!this.opened){
   for(const root of this.updates.children)if(root.visible&&root.userData.buildingId===buildingId)sources.push({root,kind:'current-form'});
   if(!sources.length)for(const entry of this.exteriors.visible.values())if(entry.group.visible&&exteriorEntityId(entry.bundle)===entity.entityId)sources.push({root:entry.group,kind:'source'});
  }
  const key=entity.entityId+'|'+sources.map(source=>source.kind+':'+source.root.uuid).join('|');
  if(this.selection.userData.sourceKey===key&&(!sources.length||this.selection.children.length))return;
  releaseObject(this.selection);this.selection.clear();this.selection.userData.sourceKey=key;
  const outline=createBuildingSelection(sources);if(outline){this.masks.apply(outline,'exterior');this.selection.add(outline)}
 }
 outline(parts:PolygonPart[],y:number){for(const part of parts)for(const ring of part.rings){const g=new THREE.BufferGeometry().setFromPoints(ring.map((p:number[])=>new THREE.Vector3(p[0],y+.2,p[1])));const l=new THREE.Line(g,new THREE.LineBasicMaterial({color:0x0b9ebd,transparent:true,depthTest:true,depthWrite:false}));l.renderOrder=20;this.selection.add(l)}}
 outlineOutdoor(e:Entity){const surface=this.outdoor.surfaces.find(s=>s.entityId===e.entityId);const road=this.outdoor.roads.find(r=>r.entityId===e.entityId);const lines:number[][][]=surface?surface.boundaryLocalXZ.coordinates.flat():road?road.linesLocalXZ.filter((_,i)=>road.segments[i]?.displayGroundReference):[];for(const points of lines){const g=new THREE.BufferGeometry().setFromPoints(points.map(p=>new THREE.Vector3(p[0],this.height(p[0],p[1])+.3,p[1])));this.selection.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0xf3b13e,depthTest:false})))}}
 snapshot():ViewSnapshot{return {camera:this.camera.position.toArray(),target:this.controls.target.toArray()}}
 remember(){this.history.push(this.snapshot());if(this.history.length>12)this.history.shift()}
 previous(){const s=this.history.pop();if(s)this.fly(new THREE.Vector3(...s.camera as [number,number,number]),new THREE.Vector3(...s.target as [number,number,number]))}
 fly(position:THREE.Vector3,target:THREE.Vector3){this.setNavigationMode('orbit');this.returnFocus=null;this.flight={start:performance.now(),from:this.camera.position.clone(),to:position,fromTarget:this.controls.target.clone(),toTarget:target}}
 zoom(direction:number){if(this.navigationMode==='fly')return;this.fly(this.camera.position.clone().sub(this.controls.target).multiplyScalar(direction>0?.72:1.35).add(this.controls.target),this.controls.target.clone())}
 preset(name:string,animate=true){this.setNavigationMode('orbit');const target=new THREE.Vector3(450,65,-1370),position=name==='top'?new THREE.Vector3(450,2300,-1369.9):name==='coast'?new THREE.Vector3(1800,620,-1250):new THREE.Vector3(1580,1100,-200);if(animate){this.remember();this.fly(position,target)}else{this.camera.position.copy(position);this.controls.target.copy(target);this.controls.update()}}
 setPanMode(enabled:boolean){if(this.navigationMode==='fly')return;this.panMode=enabled;this.controls.mouseButtons.LEFT=enabled?THREE.MOUSE.PAN:THREE.MOUSE.ROTATE;this.renderer.domElement.style.cursor=enabled?'grab':'';}
 pickPanAnchor=(ray:THREE.Raycaster)=>pickVisiblePanAnchor(ray,[this.interior.root,this.sports,this.entrance,this.landmarks,this.updates,this.exteriors.root,this.meshDetail.root,this.geometry,this.detail.group,this.terrain,...this.scene.children.filter(o=>o.name==='sea-surface')],hit=>isVisibleSurfaceHit(hit,this.masks));
 constrainPan(){this.groundState=this.groundGuard.constrain(this.camera,this.controls.target,{sampleGround:this.groundSample,sampleDetail:this.detailHeight,allowedFloorAt:this.allowedFloor,contextKey:(this.opened?.entityId||'outdoor')+'/'+this.floorId});this.anchorPan.record(this.camera,this.groundState.corrected,this.renderer.domElement.getBoundingClientRect());this.host.dataset.panState=JSON.stringify(this.anchorPan.stats())}
 preventMapContextMenu=(e:MouseEvent)=>{e.preventDefault();e.stopImmediatePropagation();};
 down=(e:PointerEvent)=>{if(this.navigationMode==='fly')return;this.pointerDown=[e.clientX,e.clientY];this.pointerTravel=0;this.pointerActive=true;this.lastInput=performance.now();this.motion.pointer(true);const action=e.button===0?this.controls.mouseButtons.LEFT:e.button===1?this.controls.mouseButtons.MIDDLE:this.controls.mouseButtons.RIGHT,modified=e.ctrlKey||e.metaKey||e.shiftKey;const pan=e.pointerType!=='touch'&&this.controls.enabled&&this.controls.enablePan&&((action===THREE.MOUSE.PAN&&!modified)||(action===THREE.MOUSE.ROTATE&&modified));if(!pan)return;this.flight=null;const position=this.camera.position.clone(),target=this.controls.target.clone();this.controls.enableDamping=false;this.controls.update();this.camera.position.copy(position);this.controls.target.copy(target);this.camera.lookAt(target);this.camera.updateMatrixWorld();if(!this.anchorPan.begin(this.camera,this.controls.target,e,this.renderer.domElement.getBoundingClientRect(),this.pickPanAnchor)){this.controls.enableDamping=true;return}this.panControlsEnabled=this.controls.enabled;this.controls.enabled=false;this.renderer.domElement.setPointerCapture(e.pointerId);this.renderer.domElement.style.cursor='grabbing';e.preventDefault();e.stopImmediatePropagation();};
 move=(e:PointerEvent)=>{if(this.navigationMode==='fly')return;this.motion.input(e.timeStamp);if(this.pointerActive){this.lastInput=performance.now();for(const p of [e,...(e.getCoalescedEvents?.()||[])])this.pointerTravel=Math.max(this.pointerTravel,Math.hypot(p.clientX-this.pointerDown[0],p.clientY-this.pointerDown[1]));}if(!this.anchorPan.active||e.pointerId!==this.anchorPan.pointerId)return;if(e.buttons===0){this.cancelPointer();e.preventDefault();e.stopImmediatePropagation();return;}this.anchorPan.move(this.camera,this.controls.target,e,this.renderer.domElement.getBoundingClientRect());e.preventDefault();e.stopImmediatePropagation();};
 cancelPointer=()=>{if(this.anchorPan.active){this.constrainPan();const pointerId=this.anchorPan.pointerId;this.anchorPan.end();this.controls.enabled=this.panControlsEnabled;if(this.renderer.domElement.hasPointerCapture(pointerId))this.renderer.domElement.releasePointerCapture(pointerId);this.renderer.domElement.style.cursor=this.panMode?'grab':'';this.host.dataset.panState=JSON.stringify(this.anchorPan.stats());}this.pointerActive=false;this.lastInput=performance.now();this.motion.pointer(false);this.controls.enableDamping=true;};
 endPanForWheel=()=>{if(this.anchorPan.active)this.cancelPointer()};
 diagnosticCamera=(event:Event)=>{
  if(this.host.dataset.diagnosticCameraEnabled!=='1'||!(event instanceof CustomEvent))return;
  const detail=event.detail as {camera?:unknown;target?:unknown};
  const vector=(value:unknown)=>Array.isArray(value)&&value.length===3&&value.every(Number.isFinite)?new THREE.Vector3(value[0],value[1],value[2]):null;
  const camera=vector(detail?.camera),target=vector(detail?.target);if(!camera||!target||camera.distanceToSquared(target)<1)return;
  this.setNavigationMode('orbit');this.cancelPointer();this.flight=null;this.returnFocus=null;this.camera.position.copy(camera);this.controls.target.copy(target);this.camera.lookAt(target);this.controls.update();this.applySafeFrameProjection();this.camera.updateMatrixWorld(true);this.notify();
 };
 rawPick(ray:THREE.Raycaster){
  const roots=[this.facilityPins,this.interior.root,this.sports,this.entrance,this.landmarks,this.updates,this.exteriors.root,this.meshDetail.root,this.geometry,this.detail.group,this.terrain,...this.scene.children.filter(o=>o.name==='sea-surface')];
  const scopedSourceId=this.host.dataset.rawPickSourceId?.trim(),scoped:THREE.Object3D[]=[];
  if(scopedSourceId)for(const root of roots)root.traverse(object=>{if(object.name===scopedSourceId)scoped.push(object)});
  const hit=ray.intersectObjects(scopedSourceId?scoped:roots,true).find(candidate=>isVisibleSurfaceHit(candidate,this.masks));
  if(!hit)return null;
  const ancestors:THREE.Object3D[]=[];for(let object:THREE.Object3D|null=hit.object;object;object=object.parent)ancestors.push(object);
  let layer='scene',sourceId='',sourceUrl='';
  const native=[...this.meshDetail.visible.values()].find(entry=>ancestors.includes(entry.group));
  if(native){
   layer='mesh-detail/'+native.key;
   const tileRoot=ancestors.find(object=>object.parent===native.group),index=tileRoot?native.group.children.indexOf(tileRoot):-1,tile=index>=0?native.level.tiles[index]:undefined;
   sourceId=native.patch.id;sourceUrl=tile?.url||'';
  }else{
   const baseline=ancestors.find(object=>object.parent===this.geometry);
   if(baseline){layer='baseline';sourceId=baseline.name;sourceUrl=this.geometry.children.includes(baseline)?baseline.name:'';}
   else if(ancestors.includes(this.detail.group))layer='terrain-detail';
   else if(ancestors.includes(this.terrain))layer='terrain';
   else if(ancestors.includes(this.updates))layer='current-form';
   else if(ancestors.includes(this.exteriors.root))layer='exterior';
   else if(ancestors.includes(this.sports)||ancestors.includes(this.entrance))layer='surface';
  }
  return {layer,sourceId,sourceUrl,point:hit.point.toArray(),distance:hit.distance,faceIndex:hit.faceIndex??null,object:hit.object.name,ancestors:ancestors.slice(0,6).map(object=>object.name)};
 }
 pick(ray:THREE.Raycaster){if(this.host.dataset.rawPickEnabled==='1'){this.host.dataset.rawPickState=JSON.stringify(this.rawPick(ray));if(this.host.dataset.rawPickOnly==='1')return null;}else delete this.host.dataset.rawPickState;const owners=new Map<THREE.Object3D,string>();for(const entry of this.exteriors.visible.values()){const entity=this.registry.get(exteriorEntityId(entry.bundle));if(!entity)continue;for(const child of entry.group.children){const sourceOwner=exteriorSourceOwner(child,entity.entityId,extraBuildingDomains.sourceObjectOwners);if(sourceOwner&&this.registry.get(sourceOwner))owners.set(child,sourceOwner);}}const result=pickEntity(ray,{registry:this.registry,masks:this.masks,footprints:this.footprints,buildingDomains:[...namedBuildingDomains.domains,...extraBuildingDomains.domains].map(d=>({...d,parts:d.parts as PolygonPart[]})),rangeDomains:this.exteriorRangeDomains(),owners,groundAt:this.groundSample,roads:this.outdoor.roads,surfaces:[...this.outdoor.surfaces.map(s=>({entityId:s.entityId,parts:s.boundaryLocalXZ.coordinates.map(rings=>({rings}))})),...this.footprints.flatMap(f=>{const e=this.registry.get(f.catalogId||'outdoor_area:'+f.officialBuildingId);return e?.type==='outdoor_area'?[{entityId:e.entityId,parts:f.parts}]:[]}),...pickingDomains.groundSurfaces.map(s=>({entityId:s.entityId,parts:s.parts as PolygonPart[]}))],sourceAssociations:pickingDomains.sourceAssociations.map(s=>({...s,parts:s.parts as PolygonPart[]})),roots:[this.facilityPins,this.interior.root,this.sports,this.entrance,this.landmarks,this.updates,this.exteriors.root,this.meshDetail.root,this.geometry,this.detail.group,this.terrain]});this.host.dataset.pickState=JSON.stringify(result?{entityId:result.entityId||'',method:result.method,physicalDomainId:result.physicalDomainId,point:result.hit.point.toArray(),object:result.hit.object.name}:null);if(result?.entityId)this.options.select(result.entityId);return result;}
 up=(e:PointerEvent)=>{if(this.navigationMode==='fly'){e.stopImmediatePropagation();return;}const dragged=Math.max(this.pointerTravel,Math.hypot(e.clientX-this.pointerDown[0],e.clientY-this.pointerDown[1]))>5;if(this.anchorPan.active&&e.pointerId===this.anchorPan.pointerId){this.anchorPan.move(this.camera,this.controls.target,e,this.renderer.domElement.getBoundingClientRect());this.cancelPointer();e.preventDefault();e.stopImmediatePropagation();}else this.cancelPointer();if(e.button!==0||dragged)return;const rect=this.renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),this.camera);this.pick(ray)};
 key=(e:KeyboardEvent)=>{if(this.navigationMode==='fly')return;if(e.key==='Home')this.preset('home');if(e.key==='+'||e.key==='=')this.zoom(1);if(e.key==='-')this.zoom(-1)};
 animate=(time:number)=>{if(this.dead)return;this.raf=requestAnimationFrame(this.animate);const deltaSeconds=this.last?(time-this.last)/1000:0;this.last=time;if(!this.active)return;const frameStart=performance.now();this.advanceImmersion(time);if(this.navigationMode==='fly'){const before=this.camera.position.clone();this.firstPerson.step(deltaSeconds);this.flightGroundLift=this.flightGround.constrain(this.camera,this.controls.target,before,(x,z,y)=>this.allowedFloor?.(x,z,y)??this.detailHeight(x,z)??this.groundSample(x,z));this.groundState=null;}else{if(this.flight&&!this.anchorPan.active){const f=this.flight,t=Math.min((performance.now()-f.start)/800,1),v=t*t*(3-2*t);this.camera.position.lerpVectors(f.from,f.to,v);this.controls.target.lerpVectors(f.fromTarget,f.toTarget,v);if(t>=1)this.flight=null}if(!this.anchorPan.active)this.controls.update();this.groundState=this.groundGuard.constrain(this.camera,this.controls.target,{sampleGround:this.groundSample,sampleDetail:this.detailHeight,allowedFloorAt:this.allowedFloor,contextKey:(this.opened?.entityId||'outdoor')+'/'+this.floorId});if(this.groundState.sweepBlocked)this.flight=null;}if(this.anchorPan.needsRecord){this.anchorPan.record(this.camera,this.groundState?.corrected||false,this.renderer.domElement.getBoundingClientRect());this.host.dataset.panState=JSON.stringify(this.anchorPan.stats());}if(!this.pointerActive&&time-this.lastInput>180){this.detail.update(false,false,true);this.updateDetails(time);}for(const child of this.detail.group.children)if(!this.maskedTerrain.has(child)){this.masks.apply(child,'terrain');this.maskedTerrain.add(child);}const w=this.host.clientWidth,h=this.host.clientHeight,rects:number[][]=[];const testOcclusion=time-this.lastOcclusion>650;if(testOcclusion)this.lastOcclusion=time;let count=0;for(const m of this.markers.slice().sort((a,b)=>Number(b.entityId===this.selectedId)-Number(a.entityId===this.selectedId))){const p=m.position.clone().project(this.camera),x=(p.x+1)*w/2,y=(1-p.y)*h/2;let visible=this.showLabels&&!this.opened&&p.z<1&&p.z>-1&&x>10&&x<w-10&&y>20&&y<h-40&&count<8&&!rects.some(r=>Math.abs(r[0]-x)<155&&Math.abs(r[1]-y)<35);if(visible&&m.entityId!==this.selectedId){if(testOcclusion||!this.labelOcclusion.has(m.entityId))this.labelOcclusion.set(m.entityId,this.labelUnobstructed(m));visible=this.labelOcclusion.get(m.entityId)!;}m.label.style.display=visible?'block':'none';if(visible){count++;rects.push([x,y]);m.label.style.left=x+'px';m.label.style.top=y+'px';m.label.classList.toggle('selected',m.entityId===this.selectedId)}}this.currentFormResidency?.refreshVisibility(this.camera,this.host.clientHeight,time,this.opened?this.registry.buildingSource(this.opened):'');this.renderer.render(this.scene,this.camera);this.motion.frame(time,performance.now()-frameStart,!!this.groundState?.corrected);if(this.qualityMode==='auto'){const signature=this.renderer.info.memory.textures+'/'+this.renderer.info.memory.geometries;if(signature!==this.qualityResourceSignature){this.qualityResourceSignature=signature;this.qualitySettledAt=time+1500;}const level=this.automaticQuality.observe(performance.now()-frameStart,time,this.loaded===this.total&&time>=this.qualitySettledAt);if(level!==this.qualityLevel)this.applyQuality(level);}if(time-this.lastStats>1500){this.notify();this.lastStats=time}};
 dispose(){this.cancelPointer();this.dead=true;this.firstPerson.dispose();this.disconnectLabelWheel();this.currentFormAbort.abort();this.currentFormResidency?.dispose();for(const set of this.currentFormSets)set.dispose();this.currentFormSets.clear();cancelAnimationFrame(this.raf);this.observer.disconnect();this.controls.dispose();this.host.removeEventListener('atlas:diagnostic-camera',this.diagnosticCamera);this.renderer.domElement.removeEventListener('contextmenu',this.preventMapContextMenu,true);this.renderer.domElement.removeEventListener('pointerdown',this.down,true);this.renderer.domElement.removeEventListener('pointerup',this.up,true);this.renderer.domElement.removeEventListener('pointermove',this.move,true);this.renderer.domElement.removeEventListener('pointercancel',this.cancelPointer,true);this.renderer.domElement.removeEventListener('wheel',this.endPanForWheel,true);this.renderer.domElement.removeEventListener('lostpointercapture',this.cancelPointer);this.renderer.domElement.removeEventListener('keydown',this.key);this.interior.dispose();this.exteriors.dispose();this.textures.dispose();this.meshDetail.dispose();this.detail.dispose();this.masks.dispose();this.seaBlendTexture?.dispose();releaseObject(this.scene);this.renderer.dispose();this.host.replaceChildren()}
}
export function pointInRings(x:number,z:number,rings:number[][][]){const inside=(ring:number[][])=>{let value=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>z)!==(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])value=!value}return value};return inside(rings[0])&&!rings.slice(1).some(inside)}
