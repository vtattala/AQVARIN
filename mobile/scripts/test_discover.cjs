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
 assert.ok(searchBeaches({query:'',activity:'surfing'}).every(b=>!b.waterType||b.waterType==='ocean'));
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
test('city lookup returns U.S. locations and rejects foreign matches',async()=>{
 const {findPlaces}=require('../src/discover/places.ts');const original=global.fetch;
 global.fetch=async()=>({ok:true,json:async()=>({results:[{id:1,name:'Miami',admin1:'Florida',country_code:'US',latitude:25.7,longitude:-80.2},{id:2,name:'Paris',country_code:'FR',latitude:48,longitude:2}]})});
 try{const places=await findPlaces('Miami');assert.equal(places.length,1);assert.equal(places[0].label,'Miami, Florida');}finally{global.fetch=original;}
});
test('forecast fan-out is bounded to a selected beach plus one page, even nationally',()=>{
 const {forecastTargets}=require('../src/discover/conditions.ts');
 const batch=forecastTargets(BEACHES[0],BEACHES,100);
 assert.equal(batch[0].id,BEACHES[0].id);assert.ok(batch.length<=13);
 assert.equal(new Set(batch.map(b=>b.id)).size,batch.length);
 assert.ok(batch.some(b=>b.id===BEACHES[100].id));
});
