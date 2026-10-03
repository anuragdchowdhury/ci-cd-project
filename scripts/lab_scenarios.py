"""Bounded Dev drills with cleanup. Run on the VM with the documented operator session."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid


def run(*args,**kwargs):
    return subprocess.run(list(args),check=True,**kwargs)


def traffic(base,duration,rate,workers):
    end=time.monotonic()+duration
    lock=threading.Lock();next_slot=[time.monotonic()]
    statuses=Counter();latencies=[];traces=[]
    def worker():
        while time.monotonic()<end:
            with lock:
                slot=max(time.monotonic(),next_slot[0]);next_slot[0]=slot+1/rate
            remaining=slot-time.monotonic()
            if remaining>0:time.sleep(remaining)
            if time.monotonic()>=end:return
            started=time.monotonic()
            try:
                with urllib.request.urlopen(base.rstrip('/')+'/api/notes',timeout=30) as response:
                    status=response.status;headers=response.headers;response.read()
            except urllib.error.HTTPError as error:
                status=error.code;headers=error.headers;error.read()
            except (urllib.error.URLError,TimeoutError):
                status='network-error';headers={}
            with lock:
                statuses[str(status)]+=1;latencies.append(time.monotonic()-started)
                if headers.get('X-Trace-Id') and len(traces)<10:traces.append({'traceId':headers['X-Trace-Id'],'requestId':headers.get('X-Request-Id')})
    with ThreadPoolExecutor(workers) as executor:
        futures=[executor.submit(worker) for _ in range(workers)]
        for future in futures:future.result()
    summary={'statuses':dict(statuses),'requests':len(latencies),'p95_seconds':sorted(latencies)[int((len(latencies)-1)*0.95)] if latencies else None,'correlation':traces}
    Path('reports').mkdir(exist_ok=True)
    Path('reports/scenario-'+str(uuid.uuid4())+'.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',required=True,choices=['baseline','error','latency','cpu','crashloop','oom','pending','db-auth','db-latency','readiness','api-down','origin-down','drift'])
    parser.add_argument('--url',default='http://127.0.0.1:8080')
    parser.add_argument('--seconds',type=int,default=180)
    parser.add_argument('--rate',type=int,default=5)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--platform',type=Path)
    args=parser.parse_args()
    if not 1<=args.seconds<=300 or not 1<=args.rate<=20 or not 1<=args.workers<=8:
        parser.error('Bounds: 1–300 seconds, 1–20 requests/second, 1–8 workers')
    if args.scenario=='drift':
        if not args.platform:parser.error('--platform is required for drift')
        platform=json.loads(args.platform.read_text())
        run('az','group','update','--name',platform['resource_group'],'--set','tags.lab_drift=simulated','-o','none')
        print('Added only tags.lab_drift to the Dev resource group. Review a Terraform plan with all three var files, then apply the saved plan to reconcile it. No resource size/count was changed.')
        return
    if args.scenario in {'readiness','api-down','origin-down'}:
        namespace='ingress-system' if args.scenario=='origin-down' else 'notekeeper-dev'
        name='traefik' if args.scenario=='origin-down' else 'notekeeper-api'
        original=json.loads(subprocess.check_output(['kubectl','-n',namespace,'get','deployment',name,'-o','json'],text=True))
        if args.scenario=='readiness':
            container=original['spec']['template']['spec']['containers'][0]
            saved=container['readinessProbe']
            changed=json.loads(json.dumps(saved));changed['httpGet']['path']='/actuator/health/not-found'
            def patch(probe):
                run('kubectl','-n',namespace,'patch','deployment',name,'--type=strategic','-p',json.dumps({'spec':{'template':{'spec':{'containers':[{'name':container['name'],'readinessProbe':probe}]}}}}))
            try:
                patch(changed)
                print('Readiness fault applied. Old healthy replica may continue serving during rollout; inspect not-ready new pods.')
                time.sleep(args.seconds)
            finally:patch(saved)
        else:
            try:
                run('kubectl','-n',namespace,'scale','deployment/'+name,'--replicas=0')
                print('Controlled Dev outage active; inspect availability/origin metrics and alerts.')
                time.sleep(args.seconds)
            finally:
                run('kubectl','-n',namespace,'scale','deployment/'+name,'--replicas='+str(original['spec']['replicas']))
        run('kubectl','-n',namespace,'rollout','status','deployment/'+name,'--timeout=180s')
        print('Original readiness/replica configuration restored.')
        return
    if args.scenario=='db-latency':
        if not args.platform:parser.error('--platform is required for database latency')
        platform=json.loads(args.platform.read_text())
        import os
        token=subprocess.check_output(['az','account','get-access-token','--resource','https://ossrdbms-aad.database.windows.net','--query','accessToken','-o','tsv'],text=True).strip()
        env=dict(os.environ,PGPASSWORD=token,PGSSLMODE='verify-full',PGSSLROOTCERT='/etc/ssl/certs/ca-certificates.crt',PGCONNECT_TIMEOUT='10')
        command=['psql','-X','-At','-v','ON_ERROR_STOP=1','-h',platform['postgres_fqdn'],'-U',platform['postgres_admin'],'-d','notekeeper_dev']
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        try:
            process.stdin.write("SET statement_timeout='20s'; BEGIN; LOCK TABLE public.notes IN ACCESS EXCLUSIVE MODE; SELECT 'LOCK_ACQUIRED'; SELECT pg_sleep(15); COMMIT;\n")
            process.stdin.close()
            for line in process.stdout:
                if line.strip()=='LOCK_ACQUIRED':break
            else:raise RuntimeError('Could not acquire bounded database lock')
            traffic(args.url,15,min(args.rate,5),args.workers)
            if process.wait(timeout=25)!=0:raise RuntimeError('Bounded database lock session failed')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
        print('Database lock released. Dependency spans show SQL waiting, unlike the application-only latency drill.')
        return
    if args.scenario in {'baseline' ,'error','latency','cpu'}:
        deployment=json.loads(subprocess.check_output(['kubectl','-n','notekeeper-dev','get','deployment','notekeeper-api','-o','json'],text=True))
        original={x['name']:x.get('value','') for x in deployment['spec']['template']['spec']['containers'][0].get('env',[])}
        fault=original.get('LAB_FAULT_MODE','none');sampling=original.get('APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE','10')
        try:
            run('kubectl','-n','notekeeper-dev','set','env','deployment/notekeeper-api','LAB_FAULT_MODE='+('none' if args.scenario=='baseline' else args.scenario),'APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE=100')
            run('kubectl','-n','notekeeper-dev','rollout','status','deployment/notekeeper-api','--timeout=180s')
            traffic(args.url,args.seconds,args.rate,args.workers)
        finally:
            run('kubectl','-n','notekeeper-dev','set','env','deployment/notekeeper-api','LAB_FAULT_MODE='+fault,'APPLICATIONINSIGHTS_SAMPLING_PERCENTAGE='+sampling)
            run('kubectl','-n','notekeeper-dev','rollout','status','deployment/notekeeper-api','--timeout=180s')
        return
    deployment=json.loads(subprocess.check_output(['kubectl','-n','notekeeper-dev','get','deployment','notekeeper-api','-o','json'],text=True))
    container=json.loads(json.dumps(deployment['spec']['template']['spec']['containers'][0]))
    namespace='notekeeper-dev' if args.scenario=='db-auth' else 'lab-scenarios'
    name='lab-'+args.scenario
    spec={'automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[{'name':'scenario','image':container['image'],'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                       'resources':{'requests':{'cpu':'50m','memory':'32Mi'},'limits':{'cpu':'250m','memory':'64Mi'}},'command':['/bin/sh','-ec','exit 1']}]}
    labels={'app.kubernetes.io/name':name,'notekeeper.lab/scenario':args.scenario}
    if args.scenario=='oom':spec['containers'][0]['command']=['/bin/sh','-ec','awk \'BEGIN { x="xxxxxxxx"; while(1) x=x x; }\'']
    if args.scenario=='pending':
        spec['nodeSelector']={'notekeeper.lab/nonexistent':'true'}
        spec['containers'][0]['command']=['/bin/sh','-ec','sleep 3600']
    if args.scenario=='db-auth':
        labels['azure.workload.identity/use']='true'
        spec['serviceAccountName']='notekeeper-api'
        container['env']=[x for x in container['env'] if x['name'] not in {'DB_USERNAME','APPLICATIONINSIGHTS_CONNECTION_STRING'}]
        container['env'].append({'name':'DB_USERNAME','value':'not-registered-lab-user'})
        container.pop('volumeMounts',None)
        container['volumeMounts']=[{'name':'tmp','mountPath':'/tmp'}]
        spec['volumes']=[{'name':'tmp','emptyDir':{'sizeLimit':'256Mi'}}]
        spec['containers']=[container]
    fixture={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':name,'namespace':namespace},'spec':{'replicas':1,'selector':{'matchLabels':{'app.kubernetes.io/name':name}},'template':{'metadata':{'labels':labels},'spec':spec}}}
    try:
        run('kubectl','apply','-f','-',input=json.dumps(fixture),text=True)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            run('kubectl','-n',namespace,'get','pods','-l','app.kubernetes.io/name='+name)
            time.sleep(min(15,max(0,deadline-time.monotonic())))
    finally:
        run('kubectl','-n',namespace,'delete','deployment',name,'--ignore-not-found=true')
    print('Scenario fixture deleted; inspect Grafana/events/logs for the recorded time window.')


if __name__=='__main__':main()
