#!/usr/bin/env python3
"""OpenAI Responses image-generation adapter with optional SSE support."""
import argparse, base64, json, mimetypes, os, urllib.error, urllib.request
from pathlib import Path

try:
    from security import fetch_image, redact
except ImportError:
    from scripts.security import fetch_image, redact


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
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:2000]
        raise RuntimeError(f'Responses API HTTP {exc.code}: {detail or exc.reason}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f'Responses API 网络请求失败: {exc}') from exc


def _partial_value(event):
    for key in ('partial_image_b64', 'b64_json', 'result'):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def apply_stream_event(state, event, partial_dir=None, prefix='responses', output_format='png'):
    """Merge one Responses SSE event into a serializable state."""
    event_type = str(event.get('type', ''))
    state.setdefault('events', []).append(event)
    if event_type == 'response.output_text.delta' and event.get('delta'):
        state['text'] = state.get('text', '') + str(event['delta'])
    if event_type == 'response.output_item.done' and isinstance(event.get('item'), dict):
        state.setdefault('output', []).append(event['item'])
    if event_type == 'response.completed' and isinstance(event.get('response'), dict):
        response = event['response']
        state.update({key: value for key, value in response.items() if key != 'output'})
        state['output'] = response.get('output', state.get('output', []))
    partial = _partial_value(event)
    if partial and 'partial' in event_type:
        if partial_dir is not None:
            partial_dir.mkdir(parents=True, exist_ok=True)
            extension = 'jpg' if output_format in ('jpg', 'jpeg') else output_format
            index = event.get('partial_image_index', len(state.get('partial_images', [])))
            target = partial_dir / f'{prefix}-partial-{index}.{extension}'
            target.write_bytes(base64.b64decode(partial))
            state.setdefault('partial_images', []).append(str(target))
    return state


def request_stream(url, key, body, timeout, events_path, partial_dir, prefix, output_format):
    req=urllib.request.Request(url, data=json.dumps(body,ensure_ascii=False).encode(), method='POST', headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'text/event-stream'})
    state = {'output': [], 'events': [], 'text': ''}
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as response, events_path.open('w', encoding='utf-8') as stream:
        for raw in response:
            line = raw.decode('utf-8', errors='replace').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            apply_stream_event(state, event, partial_dir, prefix, output_format)
            stream.write(json.dumps(redact(event), ensure_ascii=False) + '\n')
            stream.flush()
    state.pop('events', None)
    return state


def output_items(value):
    out=[]
    for item in value.get('output',[]) if isinstance(value,dict) else []:
        if item.get('type')=='image_generation_call': out.append(item)
        elif item.get('type') == 'response.output_item.done' and isinstance(item.get('item'), dict):
            nested = item['item']
            if nested.get('type') == 'image_generation_call': out.append(nested)
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
            raw, _ = fetch_image(url, timeout=300); p.write_bytes(raw)
        else: continue
        saved.append({'index':i,'path':str(p),'source':'responses','revised_prompt':item.get('revised_prompt')})
    return saved
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--task',required=True); ap.add_argument('--out-prefix',default='gip-responses'); ap.add_argument('--attachments-dir',default='/var/minis/attachments/gpt-image-playground'); ap.add_argument('--workspace-dir',default='/var/minis/workspace/gpt-image-playground'); ap.add_argument('--dry-run',action='store_true'); ap.add_argument('--timeout',type=int,default=900); args=ap.parse_args()
    task=read_json(args.task); key=os.environ.get(task.get('api_key_env','GPT_IMAGE_API_KEY')) or os.environ.get('GPT_IMAGE_API_KEY')
    if not key and not args.dry_run: raise ValueError('缺少 Responses API Key')
    endpoint = (task.get('endpoint') or os.environ.get('GPT_IMAGE_ENDPOINT') or 'dry-run://responses') if args.dry_run else endpoint_for(task)
    if args.dry_run and endpoint != 'dry-run://responses':
        endpoint = endpoint_for({'endpoint': endpoint})
    images=[data_url(x) for x in task.get('images',[])]; content=[{'type':'input_text','text':task['prompt']}]
    content += [{'type':'input_image','image_url':x} for x in images]
    tool={'type':'image_generation','size':task.get('size'),'quality':task.get('quality'),'background':task.get('background','auto'),'output_format':task.get('output_format','png'),'n':task.get('n',1)}
    for key in ('moderation', 'output_compression', 'partial_images'):
        if task.get(key) is not None: tool[key] = task[key]
    body={'model':task.get('model','gpt-image-2'),'input':[{'role':'user','content':content}], 'tools':[tool]}
    if task.get('reasoning_effort'):
        body['reasoning']={'effort': task['reasoning_effort']}
    if task.get('tool_choice'):
        body['tool_choice'] = task['tool_choice']
    streaming = bool(task.get('stream'))
    if streaming:
        body['stream'] = True
    request_path=Path(args.workspace_dir)/f'{args.out_prefix}-responses-request.json'; request_path.parent.mkdir(parents=True,exist_ok=True); request_path.write_text(json.dumps({**redact(body),'api_key_source':task.get('api_key_env','GPT_IMAGE_API_KEY')},ensure_ascii=False,indent=2),encoding='utf-8')
    if args.dry_run: print(json.dumps({'status':'dry_run','endpoint':endpoint,'model':body['model'],'request_file':str(request_path)},ensure_ascii=False)); return
    outdir=Path(args.attachments_dir); outdir.mkdir(parents=True,exist_ok=True)
    workspace=Path(args.workspace_dir)
    events_path=workspace/f'{args.out_prefix}-responses-events.jsonl'
    partial_dir=outdir/f'{args.out_prefix}-partial'
    result=request_stream(endpoint,key,body,args.timeout,events_path,partial_dir,args.out_prefix,task.get('output_format','png')) if streaming else request(endpoint,key,body,args.timeout)
    saved=save_outputs(result,outdir,args.out_prefix,task.get('output_format','png'))
    response_path=Path(args.workspace_dir)/f'{args.out_prefix}-responses.json'; response_path.write_text(json.dumps(redact(result),ensure_ascii=False,indent=2),encoding='utf-8')
    output={'status':'completed','provider':'responses','endpoint':endpoint,'model':body['model'],'actual_params':body['tools'][0],'saved_images':saved,'response_file':str(response_path)}
    if streaming:
        output.update({'stream': True, 'events_file': str(events_path), 'partial_images': result.get('partial_images', []), 'text': result.get('text', '')})
    print(json.dumps(output,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
