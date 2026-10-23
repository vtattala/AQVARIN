/** Run the pure TypeScript domain tests without adding a second test framework. */
const fs=require('node:fs');
const assert=require('node:assert/strict');
const test=require('node:test');
const ts=require('../node_modules/typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {BEACHES,distanceKm,searchBeaches,waterQualitySource}=require('../src/discover/beaches.ts');
const {parseAlerts,fetchConditions,activityFit,rankBeaches,isStale}=require('../src/discover/conditions.ts');
const now=Date.now();
const current=(changes={})=>({fetchedAt:now,marineTime:now/1000,weatherTime:now/1000,wave:.5,period:10,water:20,wind:5,air:22,hours:[],alerts:[],...changes});
const alert=(changes={})=>({id:'https://api.weather.gov/alerts/one',properties:{status:'Actual',messageType:'Alert',event:'High Surf Advisory',headline:'High surf expected',severity:'Moderate',sent:new Date(now).toISOString(),expires:new Date(now+3600000).toISOString(),...changes}});
test('national catalogue has unique valid coordinates and official source links',()=>{assert.equal(new Set(BEACHES.map(b=>b.id)).size,BEACHES.length);for(const b of BEACHES){assert.ok(b.latitude> -90&&b.latitude<90);assert.ok(b.longitude>= -180&&b.longitude<=180);assert.ok(b.latitude!==0||b.longitude!==0);assert.ok(b.source.startsWith('https://'));}});
test('distance is symmetric, zero at origin, and measures actual proximity',()=>{const a=BEACHES[0],b=BEACHES[13];assert.equal(distanceKm(a,a),0);assert.ok(Math.abs(distanceKm(a,b)-distanceKm(b,a))<.0001);assert.ok(distanceKm(a,b)>60);});
test('expired, test and cancelled alerts never appear active',()=>{assert.equal(parseAlerts({features:[alert(),alert({status:'Test'}),alert({messageType:'Cancel'}),alert({expires:new Date(now-1000).toISOString()})]},now).length,1);assert.throws(()=>parseAlerts({}),/invalid/);});
test('swimming ranking prefers lower waves and demotes incomplete data',()=>{const [a,b,c]=[BEACHES[0],BEACHES[1],BEACHES[2]];const ranked=rankBeaches([a,b,c],'swimming',{[a.id]:current({wave:2}),[b.id]:current({wave:.3}),[c.id]:current({wave:null})});assert.deepEqual(ranked.map(b=>b.id),[b.id,a.id,c.id]);});
test('severe alerts outrank proximity in exclusion from recommendations',()=>{const b=BEACHES[0];assert.ok(activityFit(b,'swimming',current({alerts:[{severity:'Severe'}]})).score<activityFit(b,'swimming',current()).score);});
test('stale model times and failed advisory checks are never ranked as complete',()=>{const b=BEACHES[0];for(const c of [current({marineTime:(now-5*3600000)/1000}),current({alertsError:'offline'}),current({fetchedAt:now-3600000})])assert.equal(activityFit(b,'swimming',c).score,-500);assert.equal(isStale(current()),false);});
test('surfing comparison uses period and wind rather than just largest waves',()=>{const b=BEACHES[0];assert.ok(activityFit(b,'surfing',current({wave:1.2,period:12,wind:5})).score>activityFit(b,'surfing',current({wave:4,period:5,wind:25})).score);});
test('partial source failure preserves useful weather and unknown marine fields',async()=>{const original=global.fetch;global.fetch=async url=>{if(url.includes('marine-api'))throw Error('offline');return {ok:true,json:async()=>url.includes('weather.gov')?{features:[]}:{current:{time:now/1000,wind_speed_10m:0,temperature_2m:20}}};};try{const c=await fetchConditions(BEACHES[0]);assert.equal(c.wave,null);assert.equal(c.wind,0);assert.ok(c.marineError);assert.equal(c.alertsError,undefined);}finally{global.fetch=original;}});
test('failed NWS request remains unknown rather than no advisories',async()=>{const original=global.fetch;global.fetch=async url=>{if(url.includes('weather.gov'))throw Error('offline');return {ok:true,json:async()=>({current:{time:now/1000},hourly:{time:[]}})};};try{assert.ok((await fetchConditions(BEACHES[0])).alertsError);}finally{global.fetch=original;}});
test('favorite advisories persist, deduplicate updates, and stop after unsubscribe',async()=>{
 const Module=require('node:module');const originalLoad=Module._load,originalFetch=global.fetch;
 const store=new Map(),notifications=[];
 const storage={getItem:async key=>store.get(key)??null,multiSet:async pairs=>pairs.forEach(([k,v])=>store.set(k,v))};
 Module._load=function(request,parent,isMain){if(request==='@react-native-async-storage/async-storage')return {__esModule:true,default:storage};if(request==='./device'&&parent?.filename.endsWith('/alerts.ts'))return {notify:async(...args)=>notifications.push(args)};return originalLoad.apply(this,arguments);};
 let version=1;
 global.fetch=async()=>({ok:true,json:async()=>({features:[alert({sent:new Date(now+version*1000).toISOString()})]})});
 try {
  const service=require('../src/discover/alerts.ts');
  store.set(service.WATCH_KEY,JSON.stringify({favorites:['shores'],enabled:true}));
  await service.checkFavoriteAlerts();await service.checkFavoriteAlerts();
  assert.equal(notifications.length,1);assert.equal(JSON.parse(store.get(service.INBOX_KEY)).length,1);
  version=2;await service.checkFavoriteAlerts();assert.equal(notifications.length,2);
  store.set(service.WATCH_KEY,JSON.stringify({favorites:[],enabled:true}));version=3;
  await service.checkFavoriteAlerts();assert.equal(notifications.length,2);
  const hawaii=BEACHES.find(b=>b.state==='HI');
  store.set(service.WATCH_KEY,JSON.stringify({favorites:[hawaii.id],enabled:true}));version=4;
  await service.checkFavoriteAlerts();assert.equal(notifications.length,3);
  assert.equal(JSON.parse(store.get(service.INBOX_KEY))[0].beachId,hawaii.id);
 } finally{Module._load=originalLoad;global.fetch=originalFetch;}
});
test('national coverage includes Pacific, Atlantic, Gulf, Great Lakes, Alaska, Hawaii and territories',()=>{
 assert.ok(BEACHES.length>7000);
 for(const state of ['CA','NY','FL','TX','MI','AK','HI','PR','VI','GU','AS','MP'])assert.ok(searchBeaches({query:'',activity:'all',state}).length>0,state);
 assert.ok(searchBeaches({query:'Waikiki',activity:'all',state:'HI'}).length>0);
 assert.ok(searchBeaches({query:'Miami',activity:'all',state:'FL'}).length>0);
});
test('search combines state, multiword names, favorites and distance without mutating catalogue',()=>{
 const florida=searchBeaches({query:'',activity:'all',state:'FL'});assert.ok(florida.every(b=>b.state==='FL'));
 const origin=florida[0];const nearby=searchBeaches({query:'',activity:'all',origin,radius:10});assert.ok(nearby.length>0);assert.ok(nearby.every(b=>distanceKm(origin,b)<=10));
 for(let i=1;i<nearby.length;i++)assert.ok(distanceKm(origin,nearby[i])>=distanceKm(origin,nearby[i-1]));
 const favorite=florida[0].id;assert.deepEqual(searchBeaches({query:'',activity:'all',favorites:[favorite]}).map(b=>b.id),[favorite]);
 assert.equal(BEACHES[0].id,'oceanside');
});
test('private access is excluded from activity candidates and lake beaches are excluded from surfing',()=>{
 for(const activity of ['swimming','surfing'])assert.ok(searchBeaches({query:'',activity}).every(b=>b.access!=='private'));
 assert.ok(searchBeaches({query:'',activity:'surfing'}).every(b=>b.waterType!=='lake'));
});
test('inland records never request unrelated ocean forecasts',async()=>{
 const beach=BEACHES.find(b=>b.waterType==='lake');const original=global.fetch,urls=[];
 global.fetch=async url=>{urls.push(url);return {ok:true,json:async()=>url.includes('weather.gov')?{features:[]}:{current:{time:Date.now()/1000,temperature_2m:19,wind_speed_10m:10}}};};
 try {const c=await fetchConditions(beach);assert.ok(c.marineScope);assert.equal(c.wave,null);assert.equal(c.water,null);assert.equal(c.air,19);assert.ok(!urls.some(url=>url.includes('marine-api')));}finally{global.fetch=original;}
});
test('regional water-quality links do not send other states to San Diego',()=>{
 const hawaii=BEACHES.find(b=>b.state==='HI');assert.ok(!waterQualitySource(hawaii).url.includes('sdbeachinfo'));
 assert.ok(waterQualitySource(BEACHES.find(b=>b.id==='shores')).url.includes('sdbeachinfo'));
});
test('map uses geographic clustering and safely embeds government beach names',()=>{
 const {mapDocument}=require('../src/discover/mapDocument.ts');
 const html=mapDocument({beaches:[{...BEACHES[0],name:'</script><script>alert(1)</script>'}],selected:'oceanside',favorites:[],alerts:[],overview:true});
 assert.ok(!html.includes('</script><script>alert(1)'));
 assert.ok(html.includes('label.textContent=title'));
 assert.ok(html.includes('map.project'));
});
test('city lookup includes international places with country labels',async()=>{
 const {findPlaces}=require('../src/discover/places.ts');const original=global.fetch;
 global.fetch=async()=>({ok:true,json:async()=>({results:[{id:1,name:'Miami',admin1:'Florida',country_code:'US',latitude:25.7,longitude:-80.2},{id:2,name:'Paris',country_code:'FR',latitude:48,longitude:2}]})});
 try{const places=await findPlaces('Miami');assert.equal(places.length,2);assert.equal(places[0].label,'Miami, Florida, US');assert.equal(places[1].label,'Paris, FR');}finally{global.fetch=original;}
});
test('forecast fan-out is bounded to a selected beach plus one page, even nationally',()=>{
 const {forecastTargets}=require('../src/discover/conditions.ts');
 const batch=forecastTargets(BEACHES[0],BEACHES,100);
 assert.equal(batch[0].id,BEACHES[0].id);assert.ok(batch.length<=13);
 assert.equal(new Set(batch.map(b=>b.id)).size,batch.length);
 assert.ok(batch.some(b=>b.id===BEACHES[100].id));
});

test('worldwide coverage, country filters and non-Latin aliases work',()=>{
 const {AVAILABLE_COUNTRIES}=require('../src/discover/beaches.ts');
 assert.ok(BEACHES.length>22000);assert.ok(AVAILABLE_COUNTRIES.length>=170);
 for(const country of ['AU','BR','ZA','GB','JP','ID','NZ','FJ','FR','GR']){
  const found=searchBeaches({query:'',activity:'all',country});assert.ok(found.length,country);assert.ok(found.every(b=>b.country===country));
 }
 assert.ok(searchBeaches({query:'Bondi',activity:'all',country:'AU'}).some(b=>b.name==='Bondi Beach'));
 const japanese=BEACHES.find(b=>b.country==='JP'&&(b.aliases??[]).some(n=>/[\u3040-\u30ff\u3400-\u9fff]/.test(n)));
 assert.ok(japanese);const alias=japanese.aliases.find(n=>/[\u3040-\u30ff\u3400-\u9fff]/.test(n));
 assert.ok(searchBeaches({query:alias,activity:'all',country:'JP'}).some(b=>b.id===japanese.id));
});
test('international alert coverage stays explicitly unsupported and never calls NWS',async()=>{
 const {fetchAlerts}=require('../src/discover/conditions.ts');const b=BEACHES.find(b=>b.country==='AU');const original=global.fetch,urls=[];
 global.fetch=async url=>{urls.push(url);return {ok:true,json:async()=>({latitude:b.latitude,longitude:b.longitude,current:{time:now/1000,wave_height:1,wind_speed_10m:10},hourly:{time:[]}})};};
 try{const c=await fetchConditions(b);assert.ok(c.alertsScope);assert.equal(c.alertsError,undefined);assert.ok(!urls.some(u=>u.includes('weather.gov')));await assert.rejects(()=>fetchAlerts(b),/coverage/);assert.ok(!waterQualitySource(b).url.includes('epa.gov'));}finally{global.fetch=original;}
});
test('unclassified inland locations do not borrow distant ocean wave data',async()=>{
 const b={...BEACHES[0],waterType:'unknown',country:'CH',latitude:47,longitude:8};const original=global.fetch;
 global.fetch=async()=>({ok:true,json:async()=>({latitude:43,longitude:8,current:{time:now/1000,wave_height:2,temperature_2m:18},hourly:{time:[]}})});
 try{const c=await fetchConditions(b);assert.equal(c.wave,null);assert.ok(c.marineScope.includes('withheld'));assert.equal(c.air,18);}finally{global.fetch=original;}
});
test('date-line neighbors stay geographically near and map wraps around its center',()=>{
 assert.ok(distanceKm({latitude:-17,longitude:179.9},{latitude:-17,longitude:-179.9})<25);
 const {mapDocument}=require('../src/discover/mapDocument.ts');const html=mapDocument({beaches:BEACHES.filter(b=>b.country==='FJ'),selected:'',favorites:[],alerts:[]});
 assert.ok(html.includes('longitudes.forEach'));assert.ok(html.includes('map.getCenter().lng'));
});
test('worldwide forecast rules use timestamped thresholds, not country or missing values',()=>{
 const {forecastAlerts}=require('../src/discover/forecastAlerts.ts');const beach=BEACHES.find(b=>b.country==='AU');
 const future=Math.ceil(now/3600000)*3600;
 const weather={hourly:{time:[future],wind_speed_10m:[35],wind_gusts_10m:[50],weather_code:[95],uv_index:[8]}};
 const marine={hourly:{time:[future],wave_height:[2]}};
 const alerts=forecastAlerts(beach,marine,weather,now);assert.equal(alerts.length,5);assert.ok(alerts.every(a=>a.kind==='forecast'&&Date.parse(a.expires)>now));
 assert.equal(forecastAlerts(beach,null,{},now).length,0);
 assert.equal(forecastAlerts(beach,{hourly:{time:[future+48*3600],wave_height:[10]}},{},now).length,0);
 assert.deepEqual(forecastAlerts(beach,marine,weather,now+60000).map(a=>[a.id,a.sent]),alerts.map(a=>[a.id,a.sent]));
});
test('any international favorite can notify, deduplicate, unsubscribe, and report an outage',async()=>{
 const Module=require('node:module'),originalLoad=Module._load,originalFetch=global.fetch;
 const store=new Map(),notifications=[];const storage={getItem:async k=>store.get(k)??null,multiSet:async pairs=>pairs.forEach(([k,v])=>store.set(k,v))};
 Module._load=function(request,parent,isMain){if(request==='@react-native-async-storage/async-storage')return {__esModule:true,default:storage};if(request==='./device'&&parent?.filename.endsWith('/alerts.ts'))return {notify:async(...args)=>notifications.push(args)};return originalLoad.apply(this,arguments);};
 const file=require.resolve('../src/discover/alerts.ts');delete require.cache[file];
 const b=BEACHES.find(b=>b.country==='AU'),future=Math.ceil(Date.now()/3600000)*3600;
 global.fetch=async url=>{assert.ok(!url.includes('weather.gov'));return {ok:true,json:async()=>({latitude:b.latitude,longitude:b.longitude,current:{time:Date.now()/1000,temperature_2m:22,wind_speed_10m:40},hourly:{time:Array.from({length:24},(_,i)=>future+i*3600),wave_height:Array(24).fill(.5),wind_speed_10m:Array(24).fill(40),wind_gusts_10m:Array(24).fill(45),weather_code:Array(24).fill(0),uv_index:Array(24).fill(3)}})};};
 try{
  const service=require('../src/discover/alerts.ts');store.set(service.WATCH_KEY,JSON.stringify({favorites:[b.id],enabled:true}));
  assert.match(await service.checkFavoriteAlerts(),/Checked 1\/1/);await service.checkFavoriteAlerts();
  assert.equal(notifications.length,1);assert.equal(JSON.parse(store.get(service.INBOX_KEY))[0].alert.kind,'forecast');
  store.set(service.WATCH_KEY,JSON.stringify({favorites:[],enabled:true}));await service.checkFavoriteAlerts();assert.equal(notifications.length,1);
  store.set(service.WATCH_KEY,JSON.stringify({favorites:[b.id],enabled:true}));global.fetch=async()=>{throw Error('offline');};await assert.rejects(()=>service.checkFavoriteAlerts(),/unknown/);assert.equal(JSON.parse(store.get(service.INBOX_KEY)).length,1);
 }finally{Module._load=originalLoad;global.fetch=originalFetch;delete require.cache[file];}
});
test('travel matching requires beach names and coordinates rather than a nearby attraction',()=>{
 const {matchingArticle}=require('../src/discover/travel.ts'),beach=BEACHES.find(b=>b.id==='shores');
 const pages=[{title:'Birch Aquarium',coordinates:[{lat:beach.latitude,lon:beach.longitude}]},{title:'La Jolla Shores',coordinates:[{lat:0,lon:0}]},{title:'La Jolla Shores',coordinates:[{lat:32.857,lon:-117.2572}],pageid:3}];
 assert.equal(matchingArticle(beach,pages).pageid,3);assert.equal(matchingArticle(beach,pages.slice(0,2)),undefined);
 const japanese={...beach,name:'Sunahama',aliases:['砂浜']};assert.equal(matchingArticle(japanese,[{title:'砂浜',coordinates:[{lat:beach.latitude,lon:beach.longitude}],pageid:4}]).pageid,4);
});
test('beach photos require a supported image and a usable Commons license and credit',()=>{
 const {licensedPhoto}=require('../src/discover/travel.ts');
 const page={title:'File:La Jolla Shores.jpg',imageinfo:[{mime:'image/jpeg',thumburl:'https://upload.wikimedia.org/wikipedia/commons/beach.jpg',descriptionurl:'https://commons.wikimedia.org/wiki/File:Beach.jpg',extmetadata:{Artist:{value:'<a href="/wiki/User:Photographer">Photographer</a>'},LicenseShortName:{value:'CC BY-SA 4.0'},LicenseUrl:{value:'https://creativecommons.org/licenses/by-sa/4.0/'}}}]};
 assert.equal(licensedPhoto(page).credit,'Photographer');assert.equal(licensedPhoto({...page,title:'File:La Jolla Shores map.jpg'}),undefined);
 assert.equal(licensedPhoto({...page,imageinfo:[{...page.imageinfo[0],mime:'image/svg+xml'}]}),undefined);
 assert.equal(licensedPhoto({...page,imageinfo:[{...page.imageinfo[0],thumburl:'javascript:alert(1)'}]}),undefined);
 assert.equal(licensedPhoto({...page,imageinfo:[{...page.imageinfo[0],extmetadata:{}}]}),undefined);
});
test('travel listings handle nested links, filter distance and omit unlocated food claims',()=>{
 const {guideListings}=require('../src/discover/travel.ts'),beach=BEACHES.find(b=>b.id==='shores');
 const text='{{eat | name=Seaside Cafe | lat=32.858 | long=-117.257 | content=Coffee and [[breakfast|brunch]] with {{nowrap|ocean views}}. }} {{eat | name=Far Away | lat=40 | long=0 }} {{eat | name=Missing Coordinates | content=No position }} {{see | name=Nearby pier | lat=32.86 | long=-117.257 | content=Walk along the shore. }}';
 const found=guideListings(text,beach,'https://en.wikivoyage.org/wiki/Guide');assert.deepEqual(found.map(p=>p.name),['Seaside Cafe','Nearby pier']);assert.ok(found[0].description.includes('brunch'));assert.ok(!found[0].description.includes('{{'));assert.ok(found.every(p=>p.distance<3));
});
test('a photo-source outage preserves the sourced beach overview and travel listings',async()=>{
 const {fetchTravelBrief}=require('../src/discover/travel.ts'),beach=BEACHES.find(b=>b.id==='shores'),original=global.fetch;
 global.fetch=async url=>{
  if(url.includes('commons.wikimedia.org'))throw Error('photo source offline');
  const pages=url.includes('wikivoyage.org')?[{title:'San Diego/La Jolla',revisions:[{slots:{main:{content:'{{eat|name=Seaside Cafe|lat=32.858|long=-117.257|content=Coffee by the coast.}}'}}}]}]:[{title:'La Jolla Shores',extract:'A sandy beach in La Jolla.',pageimage:'Shore.jpg',coordinates:[{lat:32.857,lon:-117.2572}]}];
  return {ok:true,json:async()=>({query:{pages}})};
 };
 try{const brief=await fetchTravelBrief(beach);assert.equal(brief.photo,undefined);assert.equal(brief.description,'A sandy beach in La Jolla.');assert.equal(brief.food[0].name,'Seaside Cafe');assert.ok(brief.errors.length);}finally{global.fetch=original;}
});
test('Pi camera addresses require a separate token and a root HTTP URL',()=>{
 const {piCameraUrl}=require('../src/piCamera.ts');assert.equal(piCameraUrl(' http://aqvarin-pi.local:8001/ '),'http://aqvarin-pi.local:8001');
 for(const url of ['file:///camera','http://user:secret@pi.local','http://pi.local?token=secret','http://pi.local/path'])assert.throws(()=>piCameraUrl(url));
});
test('Pi transport authenticates JPEGs and rejects stale, repeated and invalid frames',async()=>{
 const {piFrame}=require('../src/piCamera.ts'),original=global.fetch;const jpg=new Uint8Array([255,216,1,2,255,217]);let sequence=2,age=20,body=jpg;
 global.fetch=async(url,options)=>{assert.ok(url.endsWith('/api/camera/frame?after=1'));assert.equal(options.headers.Authorization,'Bearer example-camera-token');return new Response(body,{headers:{'Content-Type':'image/jpeg','X-Camera-Sequence':String(sequence),'X-Frame-Age-Ms':String(age)}});};
 try{assert.deepEqual((await piFrame('http://pi.local:8001','example-camera-token',1)).bytes,jpg);age=3000;await assert.rejects(()=>piFrame('http://pi.local:8001','example-camera-token',1),/old frame/);age=10;sequence=1;await assert.rejects(()=>piFrame('http://pi.local:8001','example-camera-token',1),/old frame/);sequence=2;body=new Uint8Array([1,2,3,4]);await assert.rejects(()=>piFrame('http://pi.local:8001','example-camera-token',1),/JPEG/);}finally{global.fetch=original;}
});
test('Pi camera denied tokens and missing tokens produce useful errors',async()=>{
 const {piRequest}=require('../src/piCamera.ts'),original=global.fetch;
 try{await assert.rejects(()=>piRequest('http://pi.local:8001','','/api/camera/health'),/token/);global.fetch=async()=>new Response('{"detail":"unauthorized"}',{status:401});await assert.rejects(()=>piRequest('http://pi.local:8001','wrong','/api/camera/health'),/rejected/);}finally{global.fetch=original;}
});

const {parsePiProfile}=require('../src/piCameraProfile.ts');
test('saved Pi survives reload with normalized address and separate token',()=>{
  const token='test-only-camera-token-for-profile';
  assert.deepEqual(parsePiProfile(JSON.stringify({version:1,address:'http://127.0.0.1:8766/',token:` ${token} `})),{version:1,address:'http://127.0.0.1:8766',token});
});
test('corrupt, unsupported, and credential-bearing saved Pi settings are ignored',()=>{
  for(const raw of [null,'{','null','{}',JSON.stringify({version:2,address:'http://localhost',token:'x'}),JSON.stringify({version:1,address:'http://user:secret@localhost',token:'x'}),JSON.stringify({version:1,address:'javascript:alert(1)',token:'x'}),JSON.stringify({version:1,address:'http://localhost',token:''})]) assert.equal(parsePiProfile(raw),null);
});
