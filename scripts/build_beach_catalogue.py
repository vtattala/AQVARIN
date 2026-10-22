"""Build the bundled US beach catalogue from public EPA and USGS records.

Run: python scripts/build_beach_catalogue.py --cache /path/to/scratch
Downloads are cached outside source; no runtime catalogue service is required.
"""
import argparse,csv,hashlib,io,json,math,subprocess,zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parent.parent
EPA='https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/WQP_Beaches/FeatureServer/1/query'
GNIS='https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/DomesticNames_National_Text.zip'
STATE_CODES=dict(zip('Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|Puerto Rico|Virgin Islands|Guam|Northern Mariana Islands|American Samoa'.split('|'),'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR VI GU MP AS'.split()))
NAMES={v:k for k,v in STATE_CODES.items()}
def download(url,path):
    if not path.exists():subprocess.run(['curl','--fail','--location','--silent','--show-error','--max-time','120','--retry','2',url,'-o',str(path)],check=True)
    return path

def distance(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,[a['latitude'],a['longitude'],b['latitude'],b['longitude']])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin((lat1-lat2)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon1-lon2)/2)**2)))
def normalize(name):return ''.join(c for c in name.lower() if c.isalnum()).replace('state','').replace('county','').replace('city','')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache',type=Path,required=True);args=parser.parse_args();args.cache.mkdir(parents=True,exist_ok=True)
    beaches={};source_files=[];offset=0
    while True:
        params=dict(where="is_historical = 'N' AND is_dormant = 'N'",outFields='beach_id,beach_name,state_code,county_name,is_beach_access_private',returnGeometry='true',outSR='4326',geometryPrecision=5,orderByFields='OBJECTID',resultOffset=offset,resultRecordCount=1000,f='json')
        path=download(EPA+'?'+urlencode(params),args.cache/f'epa-{offset}.json');source_files.append(path)
        payload=json.loads(path.read_text());assert 'error' not in payload,payload
        for f in payload.get('features',[]):
            a=f['attributes'];points=[p for line in f.get('geometry',{}).get('paths',[]) for p in line]
            if not points or a['state_code'] not in NAMES:continue
            lon=math.degrees(math.atan2(sum(math.sin(math.radians(p[0])) for p in points),sum(math.cos(math.radians(p[0])) for p in points)));lat=sum(p[1] for p in points)/len(points)
            if not (-90<lat<90 and -180<=lon<=180):continue
            state=a['state_code'];lake=state in {'MI','WI','IL','IN','OH','PA','MN'} or (state=='NY' and lat>42.5 and lon< -75)
            key='epa-'+a['beach_id']
            beaches.setdefault(key,dict(id=key,name=a['beach_name'].strip(),state=state,county=(a['county_name'] or '').title(),latitude=round(lat,5),longitude=round(lon,5),waterType='lake' if lake else 'ocean',access='private' if a['is_beach_access_private']=='Y' else 'unknown',sourceType='EPA',sourceId=a['beach_id']))
        if not payload.get('exceededTransferLimit'):break
        offset+=1000
    epa_count=len(beaches)
    archive=download(GNIS,args.cache/'gnis-national.zip');source_files.append(archive)
    with zipfile.ZipFile(archive) as z:
        name=next(n for n in z.namelist() if n.endswith('.txt'))
        reader=csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig'),delimiter='|')
        for r in reader:
            if r['feature_class']!='Beach' or '(historical)' in r['feature_name'].lower():continue
            state=STATE_CODES.get(r['state_name'])
            if not state:continue
            lat,lon=float(r['prim_lat_dec']),float(r['prim_long_dec'])
            if not (-90<lat<90 and -180<=lon<=180) or (lat==0 and lon==0):continue
            b=dict(id='gnis-'+r['feature_id'],name=r['feature_name'],state=state,county=r['county_name'],latitude=round(lat,5),longitude=round(lon,5),waterType='unknown',access='unknown',sourceType='USGS',sourceId=r['feature_id'])
            nearby=[p for p in beaches.values() if p['state']==state and abs(p['latitude']-lat)<.03 and abs(p['longitude']-lon)<.04]
            norm=normalize(b['name'])
            if any(distance(b,p)<.8 and (norm in normalize(p['name']) or normalize(p['name']) in norm) for p in nearby):continue
            # Infer ocean association only near an EPA ocean record; unknown inland waters stay unknown.
            if any(p['waterType']=='ocean' and distance(b,p)<2 for p in nearby):b['waterType']='ocean'
            beaches[b['id']]=b
    output=ROOT/'mobile/src/discover/data/us-beaches.json'
    data=sorted(beaches.values(),key=lambda b:(b['state'],b['name'].casefold(),b['id']))
    output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    metadata={'generatedAt':datetime.now(timezone.utc).isoformat(),'epaRecords':epa_count,'totalRecords':len(data),'states':dict(sorted(Counter(b['state'] for b in data).items())),'sources':[{'url':EPA,'description':'EPA BEACON beach lines; active nonhistorical locations, not live closure status'},{'url':GNIS,'description':'USGS GNIS current Beach-class names; unknown access and activity suitability'}],'sourceSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},'coverage':'Official named and reported beaches; not an exhaustive inventory of every shoreline access point. Includes inland waters and US territories where records exist.'}
    (output.parent/'provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'beaches':len(data),'epa':epa_count,'jurisdictions':len(metadata['states']),'bytes':output.stat().st_size}))
if __name__=='__main__':main()
