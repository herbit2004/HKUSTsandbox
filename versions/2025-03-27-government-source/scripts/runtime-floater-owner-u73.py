#!/usr/bin/env python3
"""Reproduce the Hall XII runtime view and identify the C58 owner by CDP."""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import time
import urllib.request

import numpy as np
import websocket


ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("HKUST_CDP_PORT", "9225"))
BASE = os.environ.get("HKUST_BASE", "http://127.0.0.1:4318/")
OUT = ROOT / "docs/source-evidence-v4/ivillage-remnants/ivillage-c58-runtime-owner-u73.json"
SHOT = ROOT / "docs/screenshots/v4/ivillage-multiangle-u73/hall12-c58-owner-u73.png"


class CDP:
    def __init__(self, url: str):
        self.socket = websocket.create_connection(url, timeout=180, origin=f"http://127.0.0.1:{PORT}")
        self.next_id = 0

    def send(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        request_id = self.next_id
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def click(self, x: float, y: float) -> None:
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})

    def drag(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x0, "y": y0, "button": "left", "buttons": 1, "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x1, "y": y1, "button": "left", "buttons": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x1, "y": y1, "button": "left", "buttons": 0, "clickCount": 1})


def project(point: list[float], camera: list[float], target: list[float], width: int, height: int, fov: float = 42.0) -> list[float]:
    camera_v = np.asarray(camera, dtype=float)
    target_v = np.asarray(target, dtype=float)
    forward = target_v - camera_v
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    relative = np.asarray(point, dtype=float) - camera_v
    depth = float(relative @ forward)
    scale = 1.0 / math.tan(math.radians(fov) / 2.0)
    ndc_x = float(relative @ right) / depth * scale / (width / height)
    ndc_y = float(relative @ up) / depth * scale
    return [(ndc_x + 1.0) * width / 2.0, (1.0 - ndc_y) * height / 2.0, depth]


pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
page = next(item for item in reversed(pages) if item.get("type") == "page" and item.get("url", "").startswith(BASE))
cdp = CDP(page["webSocketDebuggerUrl"])
cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 913, "deviceScaleFactor": 1, "mobile": False})
cdp.evaluate("localStorage.setItem('hkust-map-locale','zh-Hans');localStorage.setItem('hkust-map-quality','ultra');true")
cdp.send("Page.reload", {"ignoreCache": True})
time.sleep(15)
dom = cdp.evaluate("(()=>({ready:document.readyState,body:(document.body?.innerText||'').slice(0,600),inputs:[...document.querySelectorAll('input')].map(i=>i.getAttribute('aria-label')),world:!!document.querySelector('.atlas-world')}))()")
chosen = cdp.evaluate("""(async()=>{const input=document.querySelector('input[aria-label="搜索校园实体"]');if(!input)return {ok:false,error:'search-input-missing'};const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,'本科生宿舍12座');input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,700));const button=[...document.querySelectorAll('.entity-results>button')].find(b=>(b.querySelector('strong')?.textContent||'').includes('本科生宿舍12座'));if(!button)return {ok:false,error:'result-missing'};button.click();return {ok:true,label:button.querySelector('strong')?.textContent||''}})()""")
if not chosen.get("ok"):
    raise RuntimeError(json.dumps({"chosen": chosen, "dom": dom}, ensure_ascii=False))
time.sleep(12)
for _ in range(2):
    cdp.drag(720, 500, 1030, 475)
    time.sleep(9)
pre_state = cdp.evaluate("(()=>{try{return JSON.parse(document.querySelector('.atlas-world')?.dataset.sceneState||'null')}catch{return null}})()")
candidate = [682.6104380849634, 196.856103604855, -1039.9995217381312]
pixel = project(candidate, pre_state["camera"], pre_state["target"], 1440, 913)
screenshot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
SHOT.parent.mkdir(parents=True, exist_ok=True)
SHOT.write_bytes(base64.b64decode(screenshot["data"]))
def set_debug_source(source_id: str) -> None:
    cdp.evaluate(f"""(()=>{{const world=document.querySelector('.atlas-world');world.dataset.rawPickEnabled='1';world.dataset.rawPickOnly='1';world.dataset.rawPickSourceId={json.dumps(source_id)};world.dataset.rawPickState='';return true}})()""")


def read_raw():
    return cdp.evaluate("(()=>{const value=document.querySelector('.atlas-world')?.dataset.rawPickState;try{return JSON.parse(value||'null')}catch{return value||null}})()")


set_debug_source("12-NW-11A/12-NW-11A-4/Tile_303_143_L16_0")
cdp.click(pixel[0], pixel[1])
raw = read_raw()
set_debug_source("12-NW-11A/12-NW-11A-17/Tile_301_140_L15_0")
skyline_hits = []
for y in range(236, 289, 2):
    for x in range(1304, 1377, 2):
        cdp.evaluate("document.querySelector('.atlas-world').dataset.rawPickState='';true")
        cdp.click(x, y)
        hit = read_raw()
        if hit:
            skyline_hits.append({"pixel": [x, y], "raw": hit})
face_histogram = {}
for sample in skyline_hits:
    face = str(sample["raw"].get("faceIndex"))
    face_histogram[face] = face_histogram.get(face, 0) + 1
report = {
    "status": "runtime-owner-check",
    "runtime": BASE,
    "dom": dom,
    "chosen": chosen,
    "cameraBeforePick": pre_state.get("camera"),
    "targetBeforePick": pre_state.get("target"),
    "candidate": {"component": "C58", "centroid": candidate, "projectedPixel": pixel},
    "rawPick": raw,
    "skylineScan": {
        "sourceId": "12-NW-11A/12-NW-11A-17/Tile_301_140_L15_0",
        "roi": {"x": [1304, 1376], "y": [236, 288], "step": 2},
        "hitCount": len(skyline_hits),
        "faceHistogram": face_histogram,
        "samples": skyline_hits,
    },
    "screenshot": str(SHOT.relative_to(ROOT)),
    "limitations": ["A centroid ray can be occluded; it is positive owner evidence only when the runtime raw hit resolves to the same source primitive and face range.", "The skyline scan is limited to the two visually detached tree-like silhouettes in the recorded Hall XII pose."],
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
cdp.socket.close()
