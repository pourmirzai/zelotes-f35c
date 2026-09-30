#!/usr/bin/env python3
"""zelotes-f35c GUI — local web interface.

Run:  f35c-gui  (or python3 f35c_gui.py)
Opens http://127.0.0.1:8765 in your browser.
Works on Linux and macOS; talks to the mouse via f35c.py.
"""
import glob
import json
import os
import select
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import f35c

PORT = 8765

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zelotes F-35C</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#262b36;--txt:#e8eaf0;--mut:#8b93a7;--acc:#4f8cff;--ok:#3ecf8e}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--txt);font:15px/1.5 system-ui,'Segoe UI',sans-serif;
display:flex;justify-content:center;min-height:100vh;padding:32px 16px}
.wrap{width:100%;max-width:860px}
h1{font-size:22px;font-weight:600;margin-bottom:4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin-bottom:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.stage{display:flex;flex-direction:column;gap:6px;flex:1;min-width:110px}
.stage label{font-size:12px;color:var(--mut)}
input[type=number]{background:#0d0f13;color:var(--txt);border:1px solid var(--line);
border-radius:8px;padding:9px 10px;font-size:15px;width:100%}
input[type=number]:focus{outline:none;border-color:var(--acc)}
button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:9px 16px;
font-size:14px;font-weight:600;cursor:pointer;transition:filter .15s}
button:hover{filter:brightness(1.12)}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--txt)}
button.on{background:var(--ok)}
button:disabled{opacity:.5;cursor:default}
select{background:#0d0f13;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:9px 10px;font-size:14px}
input[type=color]{width:64px;height:40px;border:1px solid var(--line);border-radius:8px;background:none;padding:2px;cursor:pointer}
.status{font-size:13px;color:var(--mut)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);margin-right:6px}
.dot.off{background:#e5484d}
.swatch{width:38px;height:38px;border-radius:10px;border:1px solid var(--line)}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--ok);
color:#04150c;padding:10px 20px;border-radius:10px;font-weight:600;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
.grid5{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
@media(max-width:640px){.grid5{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap">
<h1>Zelotes F-35C</h1>
<div class="sub" id="status"><span class="dot off"></span>connecting…</div>

<div class="card"><h2>DPI stages</h2>
<div class="grid5" id="stages"></div>
<div class="row" style="margin-top:14px">
<button onclick="applyStages()">Apply DPI stages</button>
<span class="status">applies immediately — check the LED</span>
</div></div>

<div class="card"><h2>Active profile</h2>
<div class="row" id="profiles"></div></div>

<div class="card"><h2>Light</h2>
<div class="row">
<input type="color" id="color" value="#ffd24a" oninput="previewColor()">
<div class="swatch" id="swatch"></div>
<select id="mode">
<option value="0">Breathing</option><option value="1">Rainbow</option>
<option value="2">Breathing 2</option><option value="3" selected>Static</option>
<option value="4">Wave</option><option value="5">React to click</option>
<option value="6">Off</option>
</select>
<button onclick="applyLight()">Apply light</button>
</div>
<div class="row" style="margin-top:10px">
<span class="status">tip: red renders ~half brightness on this LED — the picker compensates automatically</span>
</div></div>

<div class="toast" id="toast"></div>
</div>
<script>
let profile=1;
async function api(path,body){const r=await fetch('/api/'+path,{method:'POST',
headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):null});
if(!r.ok)throw new Error((await r.json()).error||r.status);return r.json()}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.classList.add('show');
setTimeout(()=>e.classList.remove('show'),1600)}
function setStatus(ok,txt){document.getElementById('status').innerHTML=
'<span class="dot'+(ok?'':' off')+'"></span>'+txt}

const stagesEl=document.getElementById('stages');
for(let i=1;i<=5;i++){const d=document.createElement('div');d.className='stage';
d.innerHTML='<label>Stage '+i+'</label><input type="number" id="st'+i+'" min="100" max="26000" step="100" value="[1000,1600,2600,3200,4000][i-1]">';
stagesEl.appendChild(d)}
const profs=document.getElementById('profiles');
for(let i=1;i<=5;i++){const b=document.createElement('button');b.textContent='Profile '+i;
b.className=i===1?'on':'ghost';b.onclick=()=>setProfile(i,b);profs.appendChild(b)}
function markProfile(){} 
async function setProfile(i,b){
try{await api('set-profile',{n:i});profile=i;
[...profs.children].forEach((c,j)=>c.className=j===i-1?'on':'ghost');
toast('Profile '+i)}catch(e){toast('failed: '+e.message)}}

function previewColor(){document.getElementById('swatch').style.background=document.getElementById('color').value}
previewColor();

async function applyStages(){
const v=[];for(let i=1;i<=5;i++)v.push(parseInt(document.getElementById('st'+i).value)||800);
try{await api('set-stages',{stages:v});toast('DPI applied')}catch(e){toast('failed: '+e.message)}}

async function applyLight(){
const c=document.getElementById('color').value;
const r=parseInt(c.substr(1,2),16),g=parseInt(c.substr(3,2),16),b=parseInt(c.substr(5,2),16);
const m=parseInt(document.getElementById('mode').value);
try{await api('set-light',{r:Math.min(255,Math.round(r*1.9)),g,b,m});toast('Light applied')}
catch(e){toast('failed: '+e.message)}}

(async()=>{try{const s=await api('status');setStatus(true,'connected — '+s.device)}
catch(e){setStatus(false,'device not found (check USB / permissions)')}})();
</script></body></html>"""


class Dev(f35c.F35C):
    def __init__(self):
        self.pages = dict(PAGE00=f35c.PAGE00, PAGE18=f35c.PAGE18,
                          PAGE30=f35c.PAGE30, PAGE48=f35c.PAGE48)
        self.fd = None
        path = f35c.find_device()
        self.path = path
        if path:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)


LOCK = threading.Lock()


def with_dev(fn):
    def wrapper(*a, **kw):
        with LOCK:
            dev = Dev()
            if dev.fd is None:
                raise f35c.F35CError('device not found — plug the receiver in and check permissions')
            try:
                return fn(dev, *a, **kw)
            finally:
                os.close(dev.fd)
    return wrapper


@with_dev
def set_stages(dev, stages):
    for i, dpi in enumerate(stages, 1):
        dev.set_stage(i, int(dpi))
    return {'ok': True}


@with_dev
def set_profile(dev, n):
    dev.set_profile(int(n))
    return {'ok': True}


@with_dev
def set_light(dev, r, g, b, m):
    dev._light(rgb=(int(r), int(g), int(b)))
    dev._light(mode=int(m))
    return {'ok': True}


@with_dev
def status(dev):
    return {'device': dev.path}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/status'):
            try:
                self._json(status())
            except Exception as e:
                self._json({'error': str(e)}, 500)
            return
        body = PAGE.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        data = json.loads(self.rfile.read(n) or b'{}')
        try:
            if self.path == '/api/set-stages':
                return self._json(set_stages(data['stages']))
            if self.path == '/api/set-profile':
                return self._json(set_profile(data['n']))
            if self.path == '/api/set-light':
                return self._json(set_light(data['r'], data['g'], data['b'], data['m']))
        except Exception as e:
            return self._json({'error': str(e)}, 500)
        self._json({'error': 'unknown'}, 404)


def main():
    url = f'http://127.0.0.1:{PORT}'
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        import webview  # pywebview: native window, no browser
        print(f'zelotes-f35c GUI v{f35c.__version__} (native window)')
        webview.create_window(f'Zelotes F-35C v{f35c.__version__}', url,
                              width=920, height=760, min_size=(520, 620))
        webview.start()
        srv.shutdown()
    except Exception:
        print(f'zelotes-f35c GUI v{f35c.__version__} — {url}  (Ctrl+C to quit)')
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            srv.shutdown()


if __name__ == '__main__':
    main()
