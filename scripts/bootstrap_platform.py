"""Operator installs cluster-wide controllers and the single custom scrape job."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from platform_charts import download

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--observability",required=True,type=Path)
parser.add_argument("--render-only",action="store_true")
parser.add_argument("--helm",default="helm")
args=parser.parse_args()
obs=json.loads(args.observability.read_text())

def run(*args,**kwargs):
    return subprocess.run(list(args),check=True,**kwargs)

with tempfile.TemporaryDirectory() as directory:
    charts=download(directory)
    cm={"crds":{"enabled":True},"serviceAccount":{"name":"cert-manager","annotations":{"azure.workload.identity/client-id":obs["cert_manager_client_id"]}},
        "podLabels":{"azure.workload.identity/use":"true"},"extraArgs":["--cluster-issuer-ambient-credentials=true"],
        "resources":{"requests":{"cpu":"50m","memory":"128Mi"},"limits":{"cpu":"250m","memory":"256Mi"}},
        "webhook":{"resources":{"requests":{"cpu":"50m","memory":"64Mi"},"limits":{"cpu":"250m","memory":"128Mi"}}},
        "cainjector":{"resources":{"requests":{"cpu":"50m","memory":"128Mi"},"limits":{"cpu":"250m","memory":"256Mi"}}}}
    traefik={"deployment":{"replicas":1},"providers":{"kubernetesIngress":{"enabled":True,"namespaces":["notekeeper-dev"]},"kubernetesCRD":{"enabled":False}},
        "ingressClass":{"enabled":True,"isDefaultClass":False,"name":"traefik"},"accessLog":{"enabled":False},
        "service":{"type":"LoadBalancer","annotations":{"service.beta.kubernetes.io/azure-load-balancer-internal":"true",
            "service.beta.kubernetes.io/azure-load-balancer-internal-subnet":"ingress-private-link","service.beta.kubernetes.io/azure-load-balancer-ipv4":"10.20.19.10"}},
        "resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"500m","memory":"256Mi"}},
        "ports":{"websecure":{"port":8443,"exposedPort":443}},"ingressRoute":{"dashboard":{"enabled":False}}}
    for name,namespace,config in [("cert-manager","cert-manager",cm),("traefik","ingress-system",traefik)]:
        path=Path(directory)/(name+".json");path.write_text(json.dumps(config))
        if args.render_only:
            run(args.helm,"lint",str(charts[name]),"-f",str(path),"--strict")
            rendered=subprocess.check_output([args.helm,"template",name,str(charts[name]),"--namespace",namespace,"-f",str(path)],text=True)
            if "kind: Deployment" not in rendered: raise ValueError("Missing controller Deployment")
        else:
            run(args.helm,"upgrade","--install",name,str(charts[name]),"--namespace",namespace,"--create-namespace","-f",str(path),"--wait","--timeout","8m")
    issuer={"apiVersion":"cert-manager.io/v1","kind":"ClusterIssuer","metadata":{"name":"letsencrypt-azure"},"spec":{"acme":{
        "server":"https://acme-v02.api.letsencrypt.org/directory","email":obs["acme_email"],"privateKeySecretRef":{"name":"letsencrypt-account-key"},
        "solvers":[{"dns01":{"azureDNS":{"subscriptionID":obs["subscription_id"],"resourceGroupName":obs["resource_group"],
            "hostedZoneName":obs["dev_dns_zone"],"environment":"AzurePublicCloud","managedIdentity":{"clientID":obs["cert_manager_client_id"]}}}}]}}}
    if args.render_only:
        print("PASS: checksum-pinned platform charts lint and render with deployment values.")
        raise SystemExit(0)
    run("kubectl","apply","-f","-",input=json.dumps(issuer),text=True)
    run("kubectl","apply","-f","observability/prometheus-config.yaml")
    namespace={"apiVersion":"v1","kind":"Namespace","metadata":{"name":"lab-scenarios","labels":{"pod-security.kubernetes.io/enforce":"restricted"}}}
    run("kubectl","apply","-f","-",input=json.dumps(namespace),text=True)
print("PLATFORM_CONTROLLERS_READY; delegate Dev DNS and deploy the app before waiting for its origin certificate.")
