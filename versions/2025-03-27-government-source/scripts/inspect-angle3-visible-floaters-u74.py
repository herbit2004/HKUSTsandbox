#!/usr/bin/env python3
"""Reproduce the recorded Hall XII angle-3 pose and ray-map its sky floaters."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
import urllib.request

import websocket


ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("HKUST_CDP_PORT", "9225"))
BASE = os.environ.get("HKUST_BASE", "http://127.0.0.1:4318/")
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/angle3-visible-floater-rays-u74.json"
SHOT = ROOT / "docs/screenshots/v4/ivillage-multiangle-u73/hall12-angle-3-reproduced-u74.png"
CAMERA = [540.483, 245.422, -1355.294]
TARGET = [718.57, 144.947, -1088.105]
SOURCES = [
    "12-NW-11A/12-NW-11A-9/Tile_303_142_L15_0",
    "12-NW-11A/12-NW-11A-8/Tile_302_142_L17_003",
    "12-NW-11A/12-NW-11A-3/Tile_302_143_L16_0",
]
ROI = {"x": [1290, 1385], "y": [235, 285], "step": 2}


class CDP:
    def __init__(self, url: str):
        self.ws = websocket.create_connection(url, timeout=180, origin=f"http://127.0.0.1:{PORT}")
        self.next_id = 0

    def send(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        request_id = self.next_id
        self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def click(self, x: int, y: int) -> None:
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})


pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
page = next(item for item in reversed(pages) if item.get("type") == "page" and item.get("url", "").startswith(BASE))
cdp = CDP(page["webSocketDebuggerUrl"])
cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 913, "deviceScaleFactor": 1, "mobile": False})
cdp.send("Page.reload", {"ignoreCache": True})
deadline = time.time() + 180
state = None
while time.time() < deadline:
    time.sleep(2)
    state = cdp.evaluate("(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()")
    if state and state.get("loaded") == state.get("total") == 292:
        break
if not state or state.get("loaded") != 292:
    raise RuntimeError(f"runtime did not settle: {state}")

dispatch = cdp.evaluate(
    "(()=>{const h=document.querySelector('.atlas-world');"
    "h.dataset.diagnosticCameraEnabled='1';"
    f"h.dispatchEvent(new CustomEvent('atlas:diagnostic-camera',{{detail:{{camera:{json.dumps(CAMERA)},target:{json.dumps(TARGET)}}}}}));"
    "return JSON.parse(h.dataset.sceneState||'null')})()"
)
time.sleep(8)
pose = cdp.evaluate("JSON.parse(document.querySelector('.atlas-world').dataset.sceneState)")
if pose.get("camera") != CAMERA or pose.get("target") != TARGET:
    raise RuntimeError(json.dumps({"camera": pose.get("camera"), "target": pose.get("target"), "expectedCamera": CAMERA, "expectedTarget": TARGET}))

screenshot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
SHOT.parent.mkdir(parents=True, exist_ok=True)
SHOT.write_bytes(base64.b64decode(screenshot["data"]))

world_setup = "(()=>{const h=document.querySelector('.atlas-world');h.dataset.rawPickEnabled='1';h.dataset.rawPickOnly='1';return true})()"
cdp.evaluate(world_setup)
source_results = []
for source_id in SOURCES:
    cdp.evaluate(f"(()=>{{const h=document.querySelector('.atlas-world');h.dataset.rawPickSourceId={json.dumps(source_id)};return true}})()")
    hits = []
    for y in range(ROI["y"][0], ROI["y"][1] + 1, ROI["step"]):
        for x in range(ROI["x"][0], ROI["x"][1] + 1, ROI["step"]):
            cdp.evaluate("document.querySelector('.atlas-world').dataset.rawPickState='';true")
            cdp.click(x, y)
            raw = cdp.evaluate("(()=>{try{return JSON.parse(document.querySelector('.atlas-world').dataset.rawPickState||'null')}catch{return null}})()")
            if raw:
                hits.append({"pixel": [x, y], "raw": raw})
    faces = {}
    for sample in hits:
        key = f"{sample['raw'].get('object')}:{sample['raw'].get('faceIndex')}"
        faces[key] = faces.get(key, 0) + 1
    source_results.append({"sourceId": source_id, "hitCount": len(hits), "faceHistogram": faces, "samples": hits})
    print(json.dumps({"sourceId": source_id, "hitCount": len(hits), "faces": faces}, ensure_ascii=False), flush=True)
    if hits:
        break

report = {
    "status": "runtime-visible-sky-floater-ray-map",
    "runtime": BASE,
    "recordedPose": {"camera": CAMERA, "target": TARGET},
    "dispatchState": dispatch,
    "settledPose": {"camera": pose.get("camera"), "target": pose.get("target"), "loaded": pose.get("loaded"), "total": pose.get("total")},
    "roi": ROI,
    "sources": source_results,
    "screenshot": str(SHOT.relative_to(ROOT)),
    "safeToDelete": False,
    "reason": "This pass maps visible pixels to source faces. Deletion additionally requires topology and retained-structure checks.",
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
cdp.ws.close()
print(json.dumps({"output": str(OUT.relative_to(ROOT)), "screenshot": str(SHOT.relative_to(ROOT))}, ensure_ascii=False), flush=True)
