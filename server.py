#!/usr/bin/env python3
"""Local-only proof of concept. NOT a production-safe multi-tenant agent runtime."""
import json, os, pathlib, subprocess, threading, time, uuid, mimetypes, shutil, sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT/'managed_app'
RUNTIME = ROOT/'runtime'
WORKSPACES = RUNTIME/'workspaces'
STATE = RUNTIME/'state.json'
HOST = '127.0.0.1'
PORT = int(os.getenv('PORT', '8765'))
LOCK = threading.RLock()
JOBS = {}
STATE_DATA = {'tasks': [{'id':'t1','title':'Prepare project proposal','done':True}, {'id':'t2','title':'Review application design','done':False}, {'id':'t3','title':'Test new functionality','done':False}]}


def find_codex():
    # On Windows npm creates codex.cmd and codex.ps1 wrappers.
    # PowerShell resolves codex.ps1, but subprocess needs an executable
    # launcher; prefer the .cmd wrapper for subprocess on Windows.
    return shutil.which('codex.cmd') if os.name == 'nt' else shutil.which('codex')


def git(*args, cwd=APP, check=True):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=check)


def init():
    RUNTIME.mkdir(exist_ok=True)
    WORKSPACES.mkdir(exist_ok=True)
    if STATE.exists():
        try: STATE_DATA.update(json.loads(STATE.read_text()))
        except (ValueError, OSError): pass
    if not (APP/'.git').exists():
        git('init', '-b', 'main')
        git('config', 'user.name', 'Local Codex POC')
        git('config', 'user.email', 'poc@localhost.invalid')
        git('add', '.')
        git('commit', '-m', 'Initial task manager')
    else:
        git('config', 'user.name', 'Local Codex POC')
        git('config', 'user.email', 'poc@localhost.invalid')


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
    name = f"codex-{job_id[:8]}"
    workspace = WORKSPACES/name
    try:
        if os.getenv('POC_ALLOW_CODEX') != '1':
            raise RuntimeError('Real Codex execution is disabled. Set POC_ALLOW_CODEX=1 after reviewing the README.')
        if not find_codex():
            raise RuntimeError('Codex CLI is not installed or not in PATH. See README.md.')
        with LOCK:
            job['status'] = 'running'
        send_event(job, 'Creating isolated Git worktree')
        git('worktree','add','-b',name,str(workspace),'main')
        job['workspace'] = str(workspace)
        send_event(job, 'Starting Codex coding task')
        prompt = ('You are editing a small vanilla JS task manager prototype. '
                  'Implement the user request in this workspace. Only change files under the current project. '
                  'Preserve all existing functions; use no external dependencies. '
                  'The files index.html, app.js, styles.css are served directly. '
                  'Server-side task CRUD is outside this workspace; if a requested feature needs backend changes, '
                  'explain that limitation and implement only what can safely be done in this frontend. '
                  'Run node --check app.js and the Python test_app.py script before finishing. '
                  'Never remove existing tests. Do not access outside the project. Request: '+job['request'])
        cmd = [find_codex(),'exec','--json','--sandbox','workspace-write',prompt]
        process = subprocess.Popen(cmd,cwd=workspace,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        job['process']=process
        deadline=time.time()+300
        for line in process.stdout:
            if time.time()>deadline:
                process.kill()
                raise RuntimeError('Codex execution exceeded 5 minutes')
            try:
                ev=json.loads(line)
                typ=ev.get('type','event')
                if typ in ('item.completed','item.started'):
                    item=ev.get('item') or {}
                    desc=item.get('type','activity')
                    detail=item.get('text') or item.get('command') or ''
                    send_event(job, f'{desc}: {str(detail)[:150]}')
                elif 'failed' in typ:
                    send_event(job, typ, 'warning')
            except ValueError:
                pass
        result=process.wait(timeout=10)
        stderr=process.stderr.read()[-1500:]
        if result != 0:
            raise RuntimeError(f'Codex exited with code {result}. {stderr}')
        send_event(job, 'Running independent validation')
        checks=[['node','--check','app.js'],[sys.executable,'test_app.py']]
        for command in checks:
            cp=subprocess.run(command,cwd=workspace,capture_output=True,text=True,timeout=30)
            send_event(job, ' '.join(command)+': '+('PASS' if cp.returncode==0 else 'FAIL'))
            if cp.returncode:
                raise RuntimeError(f'Validation failed: {" ".join(command)}\n{(cp.stdout+cp.stderr)[-1500:]}')
        changes=git('status','--porcelain',cwd=workspace).stdout
        if not changes.strip():
            raise RuntimeError('Codex finished without any file changes.')
        git('add','.',cwd=workspace)
        git('commit','-m',f'Codex change: {job["request"][:60]}',cwd=workspace)
        with LOCK:
            job['diff'] = git('diff','main...HEAD','--stat',cwd=workspace).stdout
            job['status']='review'
        send_event(job, 'Tests passed. Preview ready for review.', 'success')
    except Exception as exc:
        with LOCK:
            job['status']='failed'
            job['error']=str(exc)
        send_event(job,str(exc),'error')
    finally:
        job.pop('process',None)


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
            self.reply(200, {'codexInstalled':bool(find_codex()),'codexEnabled':os.getenv('POC_ALLOW_CODEX')=='1','mode':'local prototype','revision':git('rev-parse','--short','HEAD').stdout.strip()})
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
                if any(x['status']=='running' for x in JOBS.values()): return self.reply(409,{'error':'Another Codex task is running'})
                jid=uuid.uuid4().hex
                job={'id':jid,'request':request,'created':time.time(),'updated':time.time(),'status':'queued','events':[],'diff':'','error':''}
                with LOCK: JOBS[jid]=job
                threading.Thread(target=run_job,args=(jid,),daemon=True).start()
                return self.reply(202,safe_job(job))
            if route.startswith('/api/jobs/') and route.endswith('/approve'):
                jid=route.split('/')[-2]
                job=JOBS.get(jid)
                if not job or job['status']!='review': return self.reply(409,{'error':'Job is not ready for approval'})
                if git('status','--porcelain').stdout.strip(): return self.reply(409,{'error':'Main workspace has uncommitted changes'})
                cp=git('merge','--ff-only',f'codex-{jid[:8]}',check=False)
                if cp.returncode: return self.reply(409,{'error':'Cannot fast-forward main: '+cp.stderr[-400:]})
                with LOCK: job['status']='approved'
                send_event(job,'Change merged into local main. Reload the application.', 'success')
                return self.reply(200,{'ok':True})
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
