/** Run the pure TypeScript domain tests without adding a second test framework. */
const fs=require('node:fs');
const assert=require('node:assert/strict');
const test=require('node:test');
const ts=require('../node_modules/typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {BEACHES,distanceKm}=require('../src/discover/beaches.ts');
const {parseAlerts,fetchConditions,activityFit,rankBeaches,isStale}=require('../src/discover/conditions.ts');
const now=Date.now();
const current=(changes={})=>({fetchedAt:now,marineTime:now/1000,weatherTime:now/1000,wave:.5,period:10,water:20,wind:5,air:22,hours:[],alerts:[],...changes});
const alert=(changes={})=>({id:'https://api.weather.gov/alerts/one',properties:{status:'Actual',messageType:'Alert',event:'High Surf Advisory',headline:'High surf expected',severity:'Moderate',sent:new Date(now).toISOString(),expires:new Date(now+3600000).toISOString(),...changes}});
test('catalogue has unique valid coordinates and official source links',()=>{assert.equal(new Set(BEACHES.map(b=>b.id)).size,BEACHES.length);for(const b of BEACHES){assert.ok(b.latitude>32&&b.latitude<34);assert.ok(b.longitude< -117&&b.longitude> -118);assert.ok(b.source.startsWith('https://'));}});
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
 } finally{Module._load=originalLoad;global.fetch=originalFetch;}
});
