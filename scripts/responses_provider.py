#!/usr/bin/env python3
"""Minimal OpenAI Responses image-generation adapter."""
import argparse, base64, json, mimetypes, os, time, urllib.error, urllib.request
from pathlib import Path


def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def data_url(path):
    if str(path).startswith('data:'): return path
    p=Path(path); mime=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}'
def endpoint_for(value):
    endpoint=(value.get('endpoint') or os.environ.get('GPT_IMAGE_ENDPOINT') or '').rstrip('/')
    if endpoint.endswith('/images/generations'): endpoint=endpoint[:-len('/images/generations')] + '/responses'
    elif not endpoint.endswith('/responses'): endpoint += '/responses'
    if not endpoint.startswith(('http://','https://')): raise ValueError('Responses endpoint 无效')
    return endpoint
def request(url,key,body,timeout):
    req=urllib.request.Request(url, data=json.dumps(body,ensure_ascii=False).encode(), method='POST', headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode())
def output_items(value):
    out=[]
    for item in value.get('output',[]) if isinstance(value,dict) else []:
        if item.get('type')=='image_generation_call': out.append(item)
        for c in item.get('content',[]) or []:
            if isinstance(c,dict) and c.get('type') in ('output_text','text'): pass
    return out
def save_outputs(value,outdir,prefix,fmt):
    saved=[]; items=output_items(value)
    for i,item in enumerate(items,1):
        b64=item.get('result') or item.get('b64_json')
        url=item.get('url') or item.get('image_url')
        p=outdir/f'{prefix}-{i}.{"jpg" if fmt in ("jpg","jpeg") else fmt}'
        if b64: p.write_bytes(base64.b64decode(b64))
        elif url:
            with urllib.request.urlopen(url,timeout=300) as r: p.write_bytes(r.read())
        else: continue
        saved.append({'index':i,'path':str(p),'source':'responses','revised_prompt':item.get('revised_prompt')})
    return saved
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--task',required=True); ap.add_argument('--out-prefix',default='gip-responses'); ap.add_argument('--attachments-dir',default='/var/minis/attachments/gpt-image-playground'); ap.add_argument('--workspace-dir',default='/var/minis/workspace/gpt-image-playground'); ap.add_argument('--dry-run',action='store_true'); ap.add_argument('--timeout',type=int,default=900); args=ap.parse_args()
    task=read_json(args.task); key=os.environ.get(task.get('api_key_env','GPT_IMAGE_API_KEY')) or os.environ.get('GPT_IMAGE_API_KEY')
    if not key and not args.dry_run: raise ValueError('缺少 Responses API Key')
    endpoint=endpoint_for(task); images=[data_url(x) for x in task.get('images',[])]; content=[{'type':'input_text','text':task['prompt']}]
    content += [{'type':'input_image','image_url':x} for x in images]
    body={'model':task.get('model','gpt-image-2'),'input':[{'role':'user','content':content}], 'tools':[{'type':'image_generation','size':task.get('size'),'quality':task.get('quality'),'background':task.get('background','auto'),'output_format':task.get('output_format','png'),'n':task.get('n',1)}]}
    request_path=Path(args.workspace_dir)/f'{args.out_prefix}-responses-request.json'; request_path.parent.mkdir(parents=True,exist_ok=True); request_path.write_text(json.dumps({**body,'api_key_source':task.get('api_key_env','GPT_IMAGE_API_KEY')},ensure_ascii=False,indent=2),encoding='utf-8')
    if args.dry_run: print(json.dumps({'status':'dry_run','endpoint':endpoint,'model':body['model'],'request_file':str(request_path)},ensure_ascii=False)); return
    result=request(endpoint,key,body,args.timeout); outdir=Path(args.attachments_dir); outdir.mkdir(parents=True,exist_ok=True); saved=save_outputs(result,outdir,args.out_prefix,task.get('output_format','png'))
    response_path=Path(args.workspace_dir)/f'{args.out_prefix}-responses.json'; response_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'completed','provider':'responses','endpoint':endpoint,'model':body['model'],'actual_params':body['tools'][0],'saved_images':saved,'response_file':str(response_path)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
