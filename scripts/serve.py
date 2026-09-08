#!/usr/bin/env python3
# coding: utf-8
"""Loopback-only static preview and allowlisted, on-demand official public panoramas."""
import argparse,http.server,json,pathlib,urllib.request,urllib.parse,socketserver
from versions import selected
ROOT=pathlib.Path(__file__).resolve().parents[1]
PREVIEW=ROOT/'.preview/current'
PUBLIC=selected()/'public'
class Handler(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(PREVIEW if PREVIEW.exists() else selected()/'dist/client'),**kwargs)
 def do_GET(self):
  u=urllib.parse.urlsplit(self.path)
  if u.path=='/api/panorama':
   asset=urllib.parse.parse_qs(u.query).get('id',[''])[0]
   try:
    data=json.loads((pathlib.Path(self.directory)/'data/panoramas-online.json').read_text())
    allowed={n['asset_id'] for n in data['nodes']}
   except (OSError,ValueError,KeyError):self.send_error(503,'Panorama index unavailable');return
   if asset not in allowed:self.send_error(404,'Unknown public panorama asset');return
   try:
    source='https://navigate.ust.hk/path/api/app/assets/panorama/id?id='+asset
    with urllib.request.urlopen(source,timeout=40) as r:
     mime=r.headers.get('Content-Type','');body=r.read(32*1024*1024+1)
     if not mime.startswith('image/') or len(body)>32*1024*1024:raise ValueError('Unexpected panorama response')
    self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','private,max-age=86400');self.end_headers();self.wfile.write(body)
   except Exception:self.send_error(502,'Official panorama unavailable; local scenes remain available')
   return
  return super().do_GET()
 def log_message(self,format,*args):
  if str(args[1] if len(args)>1 else '') not in ['200','304']:super().log_message(format,*args)
class Server(socketserver.ThreadingMixIn,http.server.HTTPServer):daemon_threads=True;allow_reuse_address=True
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4317);a=parser.parse_args()
 if not ((PREVIEW if PREVIEW.exists() else selected()/'dist/client')/'index.html').exists():raise SystemExit('Static build missing: run npm run build first')
 print('HKUST Campus: http://127.0.0.1:%s/ (Ctrl-C to stop)'%a.port,flush=True)
 Server(('127.0.0.1',a.port),Handler).serve_forever()
