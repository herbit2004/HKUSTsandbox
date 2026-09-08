/** Bounded observations of actual scene submission; no GPU-time or VRAM estimate. */
export class MotionMetrics {
  private movingFrames: number[] = [];
  private idleFrames: number[] = [];
  private submission: number[] = [];
  private inputLatency: number[] = [];
  private lastFrame = 0;
  private inputAt: number | null = null;
  private active = false;
  private count = 0;
  private corrections = 0;
  pointer(active: boolean) { this.active = active; }
  input(time: number) { if(this.active) { this.inputAt ??= time; this.count++; } }
  frame(time: number, cpu: number, corrected: boolean) {
    const push=(list:number[],v:number)=>{list.push(v);if(list.length>240)list.shift()};
    const interval=time-this.lastFrame;
    if(this.lastFrame&&interval<1000)push(this.active?this.movingFrames:this.idleFrames,interval);
    this.lastFrame=time;push(this.submission,cpu);
    if(this.inputAt!==null){push(this.inputLatency,Math.max(0,performance.now()-this.inputAt));this.inputAt=null;}
    if(this.active&&corrected)this.corrections++;
  }
  stats() {
    const summary=(values:number[])=>{const a=values.slice().sort((x,y)=>x-y);return {samples:a.length,p50Ms:+(a[Math.floor(a.length*.5)]||0).toFixed(2),p95Ms:+(a[Math.min(a.length-1,Math.floor(a.length*.95))]||0).toFixed(2),maxMs:+(a[a.length-1]||0).toFixed(2)}};
    return {pointerActive:this.active,inputEvents:this.count,movingFrame:summary(this.movingFrames),idleFrame:summary(this.idleFrames),sceneCpu:summary(this.submission),inputToSubmission:summary(this.inputLatency),movementGroundCorrections:this.corrections};
  }
}
