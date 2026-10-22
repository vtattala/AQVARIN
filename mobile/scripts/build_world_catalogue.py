"""Build the bundled global beach catalogue from cached, attributed source extracts.
Run after downloading the URLs in world-provenance.json; cache is never committed.
Usage: PYTHONPATH=.../world-python python3 scripts/build_world_catalogue.py --cache ...
"""
import argparse, collections, datetime, hashlib, json, math, pathlib, unicodedata, zipfile
p=argparse.ArgumentParser();p.add_argument('--cache',type=pathlib.Path,required=True);a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1]/'src/discover/data';cache=a.cache
countries={};iso3={}
for line in (cache/'countryInfo.txt').read_text().splitlines():
 if line.startswith('#'):continue
 v=line.split('\t')
 if len(v)>4:countries[v[0]]=v[4];iso3[v[1]]=v[0]
admins={v[0]:v[1] for line in (cache/'admin1CodesASCII.txt').read_text().splitlines() if len(v:=line.split('\t'))>1}
records=[];cells=collections.defaultdict(list)
def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s).lower() if c.isalnum())
def add(r):
 lat,lon=r['latitude'],r['longitude'];key=(int(lat*200),int(lon*200))
 # Suppress near-identical names within ~500m while retaining distinct named access points.
 n=norm(r['name'])
 for dy in (-1,0,1):
  for dx in (-1,0,1):
   for old in cells[(key[0]+dy,key[1]+dx)]:
    if norm(old['name'])==n and abs(old['latitude']-lat)<.004 and abs(old['longitude']-lon)*math.cos(math.radians(lat))<.004:return
 records.append(r);cells[key].append(r)
with zipfile.ZipFile(cache/'allCountries.zip') as archive:
 with archive.open('allCountries.txt') as stream:
  for line in stream:
   v=line.decode('utf8').rstrip('\n').split('\t')
   if len(v)<19 or v[6]!='T' or v[7] not in ('BCH','BCHS'):continue
   aliases=list(dict.fromkeys([v[2],*v[3].split(',')]))
   add(dict(id='geo-'+v[0],name=v[1],latitude=round(float(v[4]),6),longitude=round(float(v[5]),6),country=v[8] or 'ZZ',region=admins.get(v[8]+'.'+v[10],''),aliases=[n for n in aliases if n and n!=v[1]][:12],sourceType='GeoNames',sourceId=v[0],waterType='unknown'))
geo_count=len(records)
records.sort(key=lambda r:(countries.get(r['country'],r['country']),r['name']))
(root/'world-beaches.json').write_text(json.dumps(records,ensure_ascii=False,separators=(',',':'))+'\n')
(root/'countries.json').write_text(json.dumps(countries,ensure_ascii=False,separators=(',',':'))+'\n')
provenance={'generatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':len(records),'geoNamesRecords':geo_count,'countriesAndTerritories':len({r['country'] for r in records if r['country']!='ZZ'}),'sources':[{'url':'https://download.geonames.org/export/dump/allCountries.zip','license':'CC BY 4.0','selection':'T.BCH and T.BCHS; names, aliases and coordinates; near-identical records deduplicated'},{'url':'https://download.geonames.org/export/dump/countryInfo.txt','license':'CC BY 4.0'},{'url':'https://download.geonames.org/export/dump/admin1CodesASCII.txt','license':'CC BY 4.0'}], 'inputs':{name:hashlib.sha256((cache/name).read_bytes()).hexdigest() for name in ('allCountries.zip','countryInfo.txt','admin1CodesASCII.txt')}}
(root/'world-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print(json.dumps({k:v for k,v in provenance.items() if k not in ('sources','inputs')}))
