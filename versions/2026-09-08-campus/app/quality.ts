export type QualityMode = 'auto' | 'smooth' | 'balanced' | 'high' | 'ultra';
export type QualityLevel = Exclude<QualityMode, 'auto'>;
export const qualityOptions: Array<{id:QualityMode;label:string;description:string}> = [
  {id:'auto',label:'自动',description:'根据设备能力和持续渲染开销调整细节。'},
  {id:'smooth',label:'流畅',description:'降低画面分辨率和细节范围，适合性能有限的设备。'},
  {id:'balanced',label:'均衡',description:'兼顾近处细节和操作流畅度。'},
  {id:'high',label:'高清',description:'扩大清晰建筑和地面细节范围。'},
  {id:'ultra',label:'最高',description:'使用可用的最高细节，资源和加载开销较大。'},
];
export type QualityProfile = {dpr:number;exteriorMiB:number;textureMiB:number;meshMiB:number;meshPixels:number;meshFine:boolean;terrainTiles:number;originalWorkers:number;detailPixels:number};
export const qualityProfiles:Record<QualityLevel,QualityProfile> = {
  smooth:{dpr:1,exteriorMiB:160,textureMiB:48,meshMiB:0,meshPixels:220,meshFine:false,terrainTiles:2,originalWorkers:1,detailPixels:110},
  balanced:{dpr:1.25,exteriorMiB:512,textureMiB:96,meshMiB:192,meshPixels:170,meshFine:false,terrainTiles:4,originalWorkers:1,detailPixels:65},
  high:{dpr:1.6,exteriorMiB:640,textureMiB:192,meshMiB:1024,meshPixels:100,meshFine:false,terrainTiles:6,originalWorkers:2,detailPixels:40},
  ultra:{dpr:2,exteriorMiB:800,textureMiB:384,meshMiB:1792,meshPixels:64,meshFine:true,terrainTiles:8,originalWorkers:2,detailPixels:24},
};
export function initialQualityLevel(cores:number,maxTextureSize:number):QualityLevel {
  if(maxTextureSize<8192||cores>0&&cores<=4)return 'smooth';
  return cores>=8?'high':'balanced';
}
/** CPU submission duration is observable; this does not estimate GPU memory. */
export class AutomaticQuality {
  level:QualityLevel;private slowFrames=0;private frames=0;private lastChange=0;private fastWindows=0;private lastRatio=0;private eligible=false;
  constructor(readonly ceiling:QualityLevel){this.level=ceiling;}
  observe(renderMilliseconds:number,time:number,eligible=true):QualityLevel {
    this.eligible=eligible;
    // Decode/upload and initial scene construction are finite work. Measure
    // sustained rendering separately, without removing adaptation to slow views.
    if(!eligible){this.frames=0;this.slowFrames=0;return this.level;}
    this.frames++;if(renderMilliseconds>24)this.slowFrames++;
    if(this.frames<180||time-this.lastChange<15000)return this.level;
    const slow=this.slowFrames/this.frames;this.lastRatio=slow;this.frames=0;this.slowFrames=0;
    if(slow>.3){this.level=this.level==='high'?'balanced':'smooth';this.lastChange=time;this.fastWindows=0;}
    else if(slow<.03){
      this.fastWindows++;
      const levels:QualityLevel[]=['smooth','balanced','high','ultra'];
      if(this.fastWindows>=5&&time-this.lastChange>=45000&&levels.indexOf(this.level)<levels.indexOf(this.ceiling)){
        this.level=levels[levels.indexOf(this.level)+1];this.lastChange=time;this.fastWindows=0;
      }
    }else this.fastWindows=0;
    return this.level;
  }
  stats(){return {eligible:this.eligible,samples:this.frames,slowFrames:this.slowFrames,lastSlowRatio:this.lastRatio,fastWindows:this.fastWindows,lastChange:this.lastChange};}
}
