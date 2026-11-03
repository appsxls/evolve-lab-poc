#!/usr/bin/env python3
"""Local HTTP backend with an adapter boundary for cloud development agents."""
import json, os, pathlib, threading, time, uuid, mimetypes

from agents import Agent, CloudAgent
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT/'managed_app'
RUNTIME = ROOT/'runtime'
STATE = RUNTIME/'state.json'
HOST = '127.0.0.1'
PORT = int(os.getenv('PORT', '8765'))
LOCK = threading.RLock()
JOBS = {}
AGENT: Agent = CloudAgent()
STATE_DATA = {'tasks': [{'id':'t1','title':'Prepare project proposal','done':True}, {'id':'t2','title':'Review application design','done':False}, {'id':'t3','title':'Test new functionality','done':False}]}


def init():
    RUNTIME.mkdir(exist_ok=True)
    if STATE.exists():
        try: STATE_DATA.update(json.loads(STATE.read_text()))
        except (ValueError, OSError): pass


def save_state():
    STATE.write_text(json.dumps(STATE_DATA, indent=2))


def send_event(job, message, kind='info'):
    with LOCK:
        job['events'].append({'at':time.strftime('%H:%M:%S'), 'message':str(message)[:800], 'kind':kind})
        job['updated'] = time.time()


def safe_job(job):
    return {k:v for k,v in job.items() if k not in ('workspace','process')}


def run_job(job_id):
    job = JOBS[job_id]
    try:
        with LOCK:
            job['status'] = 'running'
        send_event(job, 'Submitting development request to cloud agent')
        AGENT.execute(job['request'])
        # Phase one defines no successful artifact/review contract yet.
        raise RuntimeError('Agent returned without a supported development result')
    except Exception as exc:
        with LOCK:
            job['status']='failed'
            job['error']=str(exc)
        send_event(job,str(exc),'error')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt%args))

    def reply(self, status, obj):
        data=json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length=int(self.headers.get('Content-Length',0))
        if length>100000: raise ValueError('Payload too large')
        return json.loads(self.rfile.read(length))

    def static(self, root, rel):
        path=(root/rel).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return self.send_error(404)
        content=path.read_bytes()
        ctype=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type',ctype+'; charset=utf-8' if ctype.startswith('text/') or ctype in ('application/javascript',) else ctype)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        route=unquote(urlparse(self.path).path)
        if route=='/api/status':
            self.reply(200, {'codexInstalled':False,'codexEnabled':False,'mode':'cloud agent prototype','revision':None,'agent':AGENT.status()})
        elif route=='/api/tasks':
            with LOCK: self.reply(200, STATE_DATA['tasks'])
        elif route=='/api/jobs':
            with LOCK: self.reply(200,[safe_job(j) for j in sorted(JOBS.values(),key=lambda x:-x['created'])])
        elif route.startswith('/api/jobs/'):
            key=route.split('/')[-1]
            with LOCK:
                if key not in JOBS: return self.reply(404,{'error':'Unknown job'})
                self.reply(200,safe_job(JOBS[key]))
        elif route.startswith('/preview/'):
            parts=route.strip('/').split('/',2)
            if len(parts)<2: return self.send_error(404)
            job=JOBS.get(parts[1])
            if not job or job['status'] not in ('review','approved') or not job.get('workspace'): return self.send_error(404)
            self.static(pathlib.Path(job['workspace']),parts[2] if len(parts)>2 else 'index.html')
        elif route.startswith('/app/'):
            self.static(APP,route[len('/app/'):])
        elif route=='/' or route=='/index.html':
            self.static(ROOT,'dashboard.html')
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            route=urlparse(self.path).path
            payload=self.body()
            if route=='/api/tasks':
                title=str(payload.get('title','')).strip()[:140]
                if not title: return self.reply(400,{'error':'Task title required'})
                t={'id':uuid.uuid4().hex[:12],'title':title,'done':False}
                with LOCK:
                    STATE_DATA['tasks'].append(t); save_state()
                return self.reply(201,t)
            if route=='/api/jobs':
                request=str(payload.get('request','')).strip()
                if len(request)<8 or len(request)>1500: return self.reply(400,{'error':'Request must contain 8–1500 characters'})
                with LOCK:
                    if any(x['status'] in ('queued', 'running') for x in JOBS.values()):
                        return self.reply(409,{'error':'Another development task is running'})
                    jid=uuid.uuid4().hex
                    job={'id':jid,'request':request,'created':time.time(),'updated':time.time(),'status':'queued','events':[],'diff':'','error':''}
                    JOBS[jid]=job
                threading.Thread(target=run_job,args=(jid,),daemon=True).start()
                return self.reply(202,safe_job(job))
            if route.startswith('/api/jobs/') and route.endswith('/approve'):
                jid=route.split('/')[-2]
                job=JOBS.get(jid)
                if not job or job['status']!='review': return self.reply(409,{'error':'Job is not ready for approval'})
                return self.reply(409,{'error':'Cloud agent approval is not configured'})
            return self.reply(404,{'error':'Not found'})
        except Exception as e:
            self.reply(400,{'error':str(e)})

    def do_PATCH(self):
        route=urlparse(self.path).path
        if not route.startswith('/api/tasks/'): return self.reply(404,{'error':'Not found'})
        try:
            payload=self.body()
            with LOCK:
                task=next((t for t in STATE_DATA['tasks'] if t['id']==route.rsplit('/',1)[-1]),None)
                if not task: return self.reply(404,{'error':'Unknown task'})
                if 'done' in payload: task['done']=bool(payload['done'])
                if 'title' in payload:
                    title=str(payload['title']).strip()[:140]
                    if not title: return self.reply(400,{'error':'Title required'})
                    task['title']=title
                save_state()
                self.reply(200,task)
        except Exception as e: self.reply(400,{'error':str(e)})

    def do_DELETE(self):
        route=urlparse(self.path).path
        if not route.startswith('/api/tasks/'): return self.reply(404,{'error':'Not found'})
        tid=route.rsplit('/',1)[-1]
        with LOCK:
            original=len(STATE_DATA['tasks'])
            STATE_DATA['tasks']=[t for t in STATE_DATA['tasks'] if t['id']!=tid]
            if len(STATE_DATA['tasks'])==original:return self.reply(404,{'error':'Unknown task'})
            save_state()
        self.reply(200,{'ok':True})

if __name__=='__main__':
    init()
    print(f'Open http://{HOST}:{PORT} (local development only)')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
