"""Retrieve only coarse public count aggregates, then reconcile independent queries."""
import argparse,csv,gzip,hashlib,io,json,urllib.parse,urllib.request
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

BASE='https://data.cityofnewyork.us/'
def fetch(url):
    with urllib.request.urlopen(url,timeout=90) as r:return r.read()
def ingest(private_dir,root='.'):
    root=Path(root);private=Path(private_dir);private.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((root/'protocol.json').read_text(encoding='utf-8'));dataset=cfg['dataset'];before_raw=fetch(BASE+'api/views/'+dataset+'.json');before=json.loads(before_raw)
    (private/'metadata-before.json').write_bytes(before_raw)
    where="tpep_pickup_datetime >= '2024-01-01T00:00:00' AND tpep_pickup_datetime < '2025-01-01T00:00:00' AND pulocationid in (132,138)"
    definitions={
      'hourly':{'$select':'date_trunc_ymd(tpep_pickup_datetime) as day,date_extract_hh(tpep_pickup_datetime) as hour,pulocationid as zone,count(*) as n','$where':where,'$group':'date_trunc_ymd(tpep_pickup_datetime),date_extract_hh(tpep_pickup_datetime),pulocationid','$order':'day,hour,zone','$limit':'50000'},
      'daily':{'$select':'date_trunc_ymd(tpep_pickup_datetime) as day,pulocationid as zone,count(*) as n','$where':where,'$group':'date_trunc_ymd(tpep_pickup_datetime),pulocationid','$order':'day,zone','$limit':'2000'},
      'monthly':{'$select':'date_extract_m(tpep_pickup_datetime) as month,pulocationid as zone,count(*) as n','$where':where,'$group':'date_extract_m(tpep_pickup_datetime),pulocationid','$order':'month,zone','$limit':'100'},
      'quality':{'$select':'count(*) as records,count(tpep_pickup_datetime) as dated_records,count(pulocationid) as zoned_records,min(tpep_pickup_datetime) as earliest,max(tpep_pickup_datetime) as latest'},
      'outside_year':{'$select':'count(*) as n','$where':"tpep_pickup_datetime < '2024-01-01T00:00:00' OR tpep_pickup_datetime >= '2025-01-01T00:00:00'"}}
    responses={};requests=[]
    for name,query in definitions.items():
        url=BASE+'resource/'+dataset+'.json?'+urllib.parse.urlencode(query);raw=fetch(url);(private/(name+'.json')).write_bytes(raw);responses[name]=json.loads(raw)
        requests.append(dict(name=name,url=url,parameters=query,received_utc=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(raw).hexdigest(),rows=len(responses[name])))
    after_raw=fetch(BASE+'api/views/'+dataset+'.json');(private/'metadata-after.json').write_bytes(after_raw);after=json.loads(after_raw)
    for field in ['id','rowsUpdatedAt','viewLastModified']:assert before.get(field)==after.get(field),field
    counts={};daily={};monthly={};checks=0
    for r in responses['hourly']:
        key=(r['day'][:10],int(r['hour']),int(r['zone']));n=int(r['n'])
        assert key not in counts and 0<=key[1]<=23 and key[2] in [132,138] and n>0 and str(n)==r['n'];counts[key]=n;checks+=5
    for r in responses['daily']:
        key=(r['day'][:10],int(r['zone']));assert key not in daily;daily[key]=int(r['n'])
    for r in responses['monthly']:
        key=(int(r['month']),int(r['zone']));assert key not in monthly;monthly[key]=int(r['n'])
    for (day,zone),n in daily.items():assert sum(v for (d,h,z),v in counts.items() if (d,z)==(day,zone))==n;checks+=1
    for (month,zone),n in monthly.items():assert sum(v for (d,h,z),v in counts.items() if (int(d[5:7]),z)==(month,zone))==n;checks+=1
    assert set((d,z) for d,h,z in counts)==set(daily);assert len(monthly)==24
    records=[];d=date(2024,1,1);end=date(2025,1,1)
    while d<end:
        ds=d.isoformat()
        for zone in [132,138]:
            for h in range(24):records.append([ds,h,zone,counts.get((ds,h,zone),0),'EXCLUDED_DST_DATE' if ds in cfg['excluded_civil_dates'] else 'IN_SCOPE'])
        d+=timedelta(days=1)
    assert len(records)==17568
    out=root/'data/source';out.mkdir(parents=True,exist_ok=True)
    for name in ['hourly','daily','monthly','quality','outside_year']:(out/(name+'.json')).write_bytes((json.dumps(responses[name],sort_keys=True,separators=(',',':'))+'\n').encode())
    buf=io.StringIO(newline='');w=csv.writer(buf,lineterminator='\n');w.writerow(['date','hour','zone','published_records','scope']);w.writerows(records);packed=gzip.compress(buf.getvalue().encode(),mtime=0);(out/'hourly_counts.csv.gz').write_bytes(packed)
    manifest=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),dataset=dataset,metadata=dict(rowsUpdatedAt=before['rowsUpdatedAt'],viewLastModified=before['viewLastModified'],matched_before_after=True),requests=requests,grid_rows=len(records),observed_groups=len(counts),zero_filled_groups=len(records)-len(counts),airport_records=sum(counts.values()),excluded_dst_records=sum(n for (d,h,z),n in counts.items() if d in cfg['excluded_civil_dates']),selected_sha256=hashlib.sha256(packed).hexdigest(),source_reconciliation_checks=checks,original_trip_records_retrieved=False,scope='Counts of source records only. Raw trip records, IDs, fares, passenger/dropoff fields and exact trip timestamps were not requested. No historical real-time availability or completeness claim.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['grid_rows','observed_groups','zero_filled_groups','airport_records','excluded_dst_records','source_reconciliation_checks','metadata']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('private_dir');p.add_argument('--root',default='.');a=p.parse_args();ingest(a.private_dir,a.root)
