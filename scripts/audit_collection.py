"""Fail if AKS has overlapping DCR associations beyond this lab's two owners."""
import argparse
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--platform',required=True,type=Path)
args=parser.parse_args()
platform=json.loads(args.platform.read_text())
url='https://management.azure.com'+platform['cluster_id']+'/providers/Microsoft.Insights/dataCollectionRuleAssociations?api-version=2023-03-11'
items=json.loads(subprocess.check_output(['az','rest','--method','GET','--url',url,'-o','json'],text=True))['value']
associations=[x for x in items if x.get('properties',{}).get('dataCollectionRuleId')]
expected={'notekeeper-containers','notekeeper-prometheus'}
if {x['name'] for x in associations} != expected or len(associations)!=2:
 print(json.dumps([{'name':x['name'],'rule':x['properties'].get('dataCollectionRuleId')} for x in associations],indent=2))
 raise SystemExit('Unexpected/overlapping DCR associations. Review before generating drill traffic; no associations were deleted.')
print('PASS: exactly one container-log DCR and one Prometheus DCR associated with AKS.')
print('Also inspect scrape target count, SDK logging/metric filters and diagnostic/export settings as described in the runbook.')
