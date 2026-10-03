"""Reconcile versioned Grafana data sources and dashboards using operator Entra auth."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--observability",required=True,type=Path)
args=parser.parse_args()
obs=json.loads(args.observability.read_text())
base=["--name",obs["grafana_name"],"--resource-group",obs["resource_group"]]
sources=[{"name":"NoteKeeper Prometheus","uid":"nk-prometheus","type":"grafana-azureprometheus-datasource","access":"proxy",
 "url":obs["prometheus_query_endpoint"],"jsonData":{"httpMethod":"POST","timeInterval":"30s","azureCredentials":{"authType":"msi"}}},
 {"name":"NoteKeeper Azure Monitor","uid":"nk-azure","type":"grafana-azure-monitor-datasource","access":"proxy",
 "jsonData":{"azureAuthType":"msi","subscriptionId":obs["subscription_id"]}}]
existing=json.loads(subprocess.check_output(["az","grafana","data-source","list",*base,"-o","json"],text=True))
with tempfile.TemporaryDirectory() as directory:
 for source in sources:
  path=Path(directory)/(source['uid']+'.json');path.write_text(json.dumps(source))
  present=any(x.get('uid')==source['uid'] for x in existing)
  command=["az","grafana","data-source","update" if present else "create",*base,"--definition",str(path),"-o","none"]
  if present:command.extend(["--data-source",source['uid']])
  subprocess.run(command,check=True)
 for original in sorted(Path('observability').glob('dashboard-*.json')):
  dashboard=json.loads(original.read_text())
  # Log Analytics workspace ID is a query resource, not a credential.
  for panel in dashboard.get('panels',[]):
   for target in panel.get('targets',[]):
    if 'azureLogAnalytics' in target:
     target['azureLogAnalytics']['resources']=[obs['law_id']]
  path=Path(directory)/original.name;path.write_text(json.dumps(dashboard))
  subprocess.run(["az","grafana","dashboard","import",*base,"--definition",str(path),"-o","none"],check=True)
print('Grafana data sources and dashboards reconciled; verify live query results before drills.')
