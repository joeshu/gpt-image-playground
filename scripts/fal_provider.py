#!/usr/bin/env python3
"""Small fal.ai queue adapter using the REST API (no SDK dependency)."""
import argparse, base64, json, mimetypes, os, time, urllib.request
from pathlib import Path

try:
    from security import fetch_image, display_url, redact
except ImportError:
    from scripts.security import fetch_image, display_url, redact

def read_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def image_value(v):
    if str(v).startswith(('data:','http://','https://')): return v
    p=Path(v); mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}'
def call(url,key,method='GET',body=None,timeout=120):
    req=urllib.request.Request(url,method=method,headers={'Authorization':'Key '+key,'Content-Type':'application/json','Accept':'application/json'},data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode())
def urls(value):
    found=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if k in ('url','image_url') and isinstance(v,str) and v.startswith(('http://','https://')): found.append(v)
                else: walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(value); return found
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--task',required=True); ap.add_argument('--out-prefix',default='gip-fal'); ap.add_argument('--attachments-dir',default='/var/minis/attachments/gpt-image-playground'); ap.add_argument('--workspace-dir',default='/var/minis/workspace/gpt-image-playground'); ap.add_argument('--dry-run',action='store_true'); ap.add_argument('--poll-interval',type=int,default=2); ap.add_argument('--poll-timeout',type=int,default=900); args=ap.parse_args()
    task=read_json(args.task); key=os.environ.get(task.get('api_key_env','FAL_KEY')) or os.environ.get('FAL_KEY')
    model=task.get('model','fal-ai/gpt-image-1'); base=(task.get('endpoint') or 'https://queue.fal.run').rstrip('/'); submit=base+'/'+model.lstrip('/') if '/queue.fal.run' in base else base
    body={'prompt':task['prompt'],'image_size':task.get('size','square'),'num_images':task.get('n',1)}
    if task.get('images'): body['image_urls']=[image_value(x) for x in task['images']]
    if task.get('quality'): body['quality']=task['quality']
    reqpath=Path(args.workspace_dir)/f'{args.out_prefix}-fal-request.json'; reqpath.parent.mkdir(parents=True,exist_ok=True); reqpath.write_text(json.dumps({'endpoint':display_url(submit),'model':model,'body':redact(body),'api_key_source':task.get('api_key_env','FAL_KEY')},ensure_ascii=False,indent=2),encoding='utf-8')
    if args.dry_run: print(json.dumps({'status':'dry_run','provider':'fal','endpoint':submit,'model':model,'request_file':str(reqpath)},ensure_ascii=False)); return
    if not key: raise ValueError('缺少 FAL_KEY')
    accepted=call(submit,key,'POST',body); rid=accepted.get('request_id') or accepted.get('id')
    if not rid: raise ValueError('fal 响应缺少 request_id')
    started=time.time(); status_url=f'{base}/requests/{rid}/status'; result_url=f'{base}/requests/{rid}'
    while time.time()-started<args.poll_timeout:
        state=call(status_url,key)
        if str(state.get('status','')).upper()=='COMPLETED': break
        if str(state.get('status','')).upper() in ('FAILED','CANCELLED','ERROR'): raise RuntimeError('fal 任务失败: '+json.dumps(state,ensure_ascii=False)[:1000])
        time.sleep(max(0,args.poll_interval))
    else: raise TimeoutError('fal 任务轮询超时')
    result=call(result_url,key); outdir=Path(args.attachments_dir);outdir.mkdir(parents=True,exist_ok=True); saved=[]
    for i,url in enumerate(urls(result),1):
        p=outdir/f'{args.out_prefix}-{i}.png'
        raw, _ = fetch_image(url, timeout=300); p.write_bytes(raw)
        saved.append({'index':i,'path':str(p),'source':'fal','url':display_url(url)})
    response=Path(args.workspace_dir)/f'{args.out_prefix}-fal-response.json';response.write_text(json.dumps(redact(result),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'completed','provider':'fal','model':model,'request_id':rid,'actual_params':body,'saved_images':saved,'response_file':str(response)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
