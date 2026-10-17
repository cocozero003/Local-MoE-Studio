"""Run a saved llama.cpp configuration plus Team Hub without the desktop GUI."""
import argparse
import json
import os
import subprocess
from pathlib import Path
from .backend import DEFAULTS, SETTINGS
from .model_support import memory_flags
from .team_server import start_team_server


def build_backend_command(config):
    exe=Path(str(config.get('server','')).strip().strip('"'))
    model=Path(str(config.get('model','')).strip().strip('"'))
    if not exe.is_file() or exe.name.lower() != 'llama-server.exe':
        raise ValueError('First install llama.cpp using the desktop Models page')
    if not model.is_file() or model.suffix.lower()!='.gguf':
        raise ValueError('First download and select a GGUF model using the desktop application')
    port=int(config.get('port',8081))
    context=int(config.get('context',4096))
    ngl=str(config.get('gpu_layers','auto'))
    if ngl not in ('auto','all') and (not ngl.isdigit() or int(ngl)>999):
        raise ValueError('Invalid GPU layers')
    if not (1024<=port<=65535 and 512<=context<=262144):
        raise ValueError('Invalid port or context')
    kv=str(config.get('kv','q8_0'))
    if kv not in ('q8_0','q4_0','f16'):
        raise ValueError('Invalid KV cache type')
    args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),
          '-c',str(context),'-ngl',ngl,'-fa','on' if config.get('flash',True) else 'off',
          '-ctk',kv,'-ctv',kv,'-fit','on' if config.get('fit',True) else 'off',
          '-fitt',str(int(config.get('fit_margin',1024)))]
    args.extend(memory_flags(config, model, exe))
    threads=str(config.get('threads','auto'))
    if threads!='auto':args.extend(['-t',str(int(threads))])
    return args,port


def main():
    parser=argparse.ArgumentParser(description='Start llama.cpp and authenticated Team Hub in headless mode')
    parser.add_argument('--lan',action='store_true',help='Bind Team Hub to 0.0.0.0 (trusted LAN HTTP only)')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    config=DEFAULTS.copy()
    if SETTINGS.is_file():config.update(json.loads(SETTINGS.read_text(encoding='utf-8')))
    command,backend_port=build_backend_command(config)
    if args.lan:
        print('WARNING: Do not expose this unencrypted service outside a trusted private LAN.')
    child=subprocess.Popen(command,cwd=str(Path(command[0]).parent),
             stdin=subprocess.DEVNULL,stdout=None,stderr=None,
             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        server=start_team_server(host='0.0.0.0' if args.lan else '127.0.0.1',
                 port=args.port,backend_port=backend_port,lan=args.lan)
        print('Team Hub ready at http://127.0.0.1:'+str(args.port))
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if 'server' in locals():server.server_close()
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill()

if __name__=='__main__':main()
