"""Prove the error drill is observed by RED metrics while probes stay healthy."""
import http.client
import subprocess
import time
import urllib.error
import urllib.request

name='notekeeper-fault-test'
try:
 subprocess.run(['docker','compose','run','--name',name,'--no-deps','-d',
  '-p','127.0.0.1:18080:8080','-p','127.0.0.1:18090:9090','-e','LAB_FAULT_MODE=error','backend'],check=True)
 for attempt in range(90):
  try:
   with urllib.request.urlopen('http://127.0.0.1:18090/actuator/health/readiness',timeout=3) as r:
    if r.status==200:break
  except (OSError,http.client.HTTPException):
   if attempt==89:raise
   time.sleep(1)
 try:
  urllib.request.urlopen('http://127.0.0.1:18080/api/notes',timeout=5)
  raise AssertionError('Error drill did not return HTTP 500')
 except urllib.error.HTTPError as error:
  assert error.code==500
 with urllib.request.urlopen('http://127.0.0.1:18090/actuator/health/liveness',timeout=5) as r:assert r.status==200
 with urllib.request.urlopen('http://127.0.0.1:18090/actuator/prometheus',timeout=5) as r:metrics=r.read().decode()
 assert 'status="500"' in metrics
 print('PASS: controlled HTTP 500 appears in Prometheus RED metrics; health probes remain healthy.')
except BaseException:
 subprocess.run(["docker","logs","--tail=60",name],check=False)
 raise
finally:
 subprocess.run(['docker','rm','-f',name],check=False)
