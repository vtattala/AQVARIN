import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Svg, { Polyline } from 'react-native-svg';
import { BEACHES, BEACH_BY_ID, AVAILABLE_STATES, STATE_NAMES, AVAILABLE_COUNTRIES, COUNTRY_NAMES, Beach, Position, Activity, searchBeaches, waterQualitySource, distanceKm } from './beaches';
import { Conditions, activityFit, fetchConditions, isStale, rankBeaches, forecastTargets } from './conditions';
import BeachMap from './BeachMap';
import { FORECAST_RULES } from './forecastAlerts';
import { findPlaces, Place } from './places';
import { locate, enableNotifications } from './device';
import { checkFavoriteAlerts, INBOX_KEY, Notice, WATCH_KEY } from './alerts';
import { registerAlertChecks } from './background';
import { Icon } from '../ui';
const CACHE_KEY='aqvarin.discover.conditions.v2';
const value=(n: number|null|undefined,unit: string)=>n==null?'Unavailable':`${n.toFixed(1)}${unit}`;
const time=(n: number)=>new Date(n).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
function Action({label,onPress,selected=false,disabled=false}:{label:string;onPress:()=>void;selected?:boolean;disabled?:boolean}) {
  return <Pressable accessibilityRole="button" accessibilityState={{selected,disabled}} disabled={disabled} onPress={onPress} style={[s.action,selected&&s.actionSelected,disabled&&{opacity:.5}]}><Text style={[s.actionText,selected&&{color:'#062c35'}]}>{label}</Text></Pressable>;
}
function Metric({label,amount}:{label:string;amount:string}) {return <View style={s.metric}><Text style={s.metricValue}>{amount}</Text><Text style={s.small}>{label}</Text></View>;}
function Source({label,url}:{label:string;url:string}) {return <Pressable accessibilityRole="link" onPress={()=>void Linking.openURL(url)}><Text style={s.link}>{label} ↗</Text></Pressable>;}
export default function DiscoverScreen({onMonitor,onFocusBeach}:{onMonitor:()=>void;onFocusBeach:(offset:number)=>void}) {
  const [query,setQuery]=useState(''),[activity,setActivity]=useState<Activity>('all');
  const [countryCode,setCountryCode]=useState(''),[showCountries,setShowCountries]=useState(false),[countryQuery,setCountryQuery]=useState('');
  const [stateCode,setStateCode]=useState(''),[showStates,setShowStates]=useState(false),[pageOffset,setPageOffset]=useState(0);
  const [places,setPlaces]=useState<Place[]>([]),[findingPlace,setFindingPlace]=useState(false),[originLabel,setOriginLabel]=useState('Your location');
  const [origin,setOrigin]=useState<Position>(),[radius,setRadius]=useState(50),[locating,setLocating]=useState(false);
  const [favorites,setFavorites]=useState<string[]>([]),[onlyFavorites,setOnlyFavorites]=useState(false),[alertsEnabled,setAlertsEnabled]=useState(false);
  const [selected,setSelected]=useState('shores'),[conditions,setConditions]=useState<Record<string,Conditions>>({});
  const [loading,setLoading]=useState(false),[loaded,setLoaded]=useState(false),[error,setError]=useState(''),[alertStatus,setAlertStatus]=useState('');
  const [inbox,setInbox]=useState<Notice[]>([]),[showInbox,setShowInbox]=useState(false),[checkingAlerts,setCheckingAlerts]=useState(false);
  const [forecastIndex,setForecastIndex]=useState(0);
  const detailOffset=useRef(0),placeRequest=useRef(0);
  function updateQuery(value:string){placeRequest.current++;setFindingPlace(false);setQuery(value);setPlaces([]);}
  const refreshing=useRef(false),saveQueue=useRef(Promise.resolve()),controller=useRef<AbortController|null>(null);
  const conditionsRef=useRef(conditions);conditionsRef.current=conditions;
  const targets=useRef<Beach[]>([]);
  const refresh=useCallback(async(force=false)=>{
    if(refreshing.current)return;
    refreshing.current=true;setLoading(true);
    const c=new AbortController();controller.current=c;
    const next={...conditionsRef.current};let index=0;
    const batch=[...targets.current];const batchKey=batch.map(b=>b.id).join(',');
    try {
      await Promise.all(Array.from({length:3},async()=>{
        while(index<batch.length&&!c.signal.aborted) {
          const beach=batch[index++];
          if(!force&&next[beach.id]&&Date.now()-next[beach.id].fetchedAt<5*60000)continue;
          const result=await fetchConditions(beach,c.signal);
          if(c.signal.aborted)return;
          if(batchKey!==targets.current.map(b=>b.id).join(','))return;
          // Preserve the last complete response on a total outage, with its original timestamp.
          if((result.marineError||result.marineScope)&&result.weatherError&&result.alertsError&&next[beach.id])continue;
          next[beach.id]=result;setConditions({...next});
        }
      }));
      if(!c.signal.aborted){const bounded=Object.fromEntries(Object.entries(next).sort((a,b)=>b[1].fetchedAt-a[1].fetchedAt).slice(0,150));await AsyncStorage.setItem(CACHE_KEY,JSON.stringify(bounded));}
    } catch {if(!c.signal.aborted)setError('Could not save refreshed conditions. Your last saved data is still available.');}
    finally {refreshing.current=false;if(!c.signal.aborted){setLoading(false);if(batchKey!==targets.current.map(b=>b.id).join(','))void refresh();}}
  },[]);
  useEffect(()=>{
    let mounted=true;
    void AsyncStorage.multiGet([WATCH_KEY,CACHE_KEY,INBOX_KEY]).then(entries=>{
      if(!mounted)return;
      const watch=JSON.parse(entries[0][1]??'{"favorites":[],"enabled":false}');
      setFavorites(Array.isArray(watch.favorites)?watch.favorites.filter((id: string)=>BEACHES.some(b=>b.id===id)):[]);
      setAlertsEnabled(watch.enabled===true);const cached=JSON.parse(entries[1][1]??'{}');conditionsRef.current=cached;setConditions(cached);setInbox(JSON.parse(entries[2][1]??'[]'));
    }).catch(()=>{if(mounted)setError('Saved preferences could not be restored.');}).finally(()=>{if(mounted){setLoaded(true);void refresh();}});
    return()=>{mounted=false;controller.current?.abort();};
  },[refresh]);
  useEffect(()=>{
    if(!loaded)return;
    // Serialize preference writes so rapid favorite changes cannot restore an older selection.
    saveQueue.current=saveQueue.current.catch(()=>{}).then(()=>AsyncStorage.setItem(WATCH_KEY,JSON.stringify({favorites,enabled:alertsEnabled})));
    void saveQueue.current.then(()=>registerAlertChecks(alertsEnabled)).then(setAlertStatus).catch(()=>setAlertStatus('Background checks unavailable. Keep AQVARIN open to refresh alerts.'));
  },[loaded,favorites,alertsEnabled]);
  const checkAlerts=useCallback(async()=>{
    if(!loaded)return;setCheckingAlerts(true);
    try {await saveQueue.current;const status=await checkFavoriteAlerts();setAlertStatus(status);setInbox(JSON.parse(await AsyncStorage.getItem(INBOX_KEY)??'[]'));}
    catch(e){setAlertStatus(e instanceof Error?e.message:'Advisory check failed');}
    finally {setCheckingAlerts(false);}
  },[loaded]);
  useEffect(()=>{
    if(!loaded)return;
    if(alertsEnabled)void checkAlerts();
    const timer=setInterval(()=>{if(AppState.currentState==='active'){void refresh();if(alertsEnabled)void checkAlerts();}},5*60000);
    const listener=AppState.addEventListener('change',state=>{if(state==='active'){void refresh();if(alertsEnabled)void checkAlerts();}});
    return()=>{clearInterval(timer);listener.remove();};
  },[loaded,alertsEnabled,favorites,refresh,checkAlerts]);
  const candidates=useMemo(()=>searchBeaches({query,activity,country:countryCode,state:stateCode,origin,radius,favorites:onlyFavorites?favorites:undefined}),[query,activity,countryCode,stateCode,onlyFavorites,favorites,origin,radius]);
  useEffect(()=>{setPageOffset(0);},[query,activity,countryCode,stateCode,onlyFavorites,origin,radius]);
  // Compare and request only a bounded shortlist. Never fetch forecasts for the whole catalogue.
  const shortlist=candidates.slice(pageOffset,pageOffset+12);
  const beaches=useMemo(()=>rankBeaches(shortlist,activity,conditions,origin),[candidates,pageOffset,activity,conditions,origin]);
  useEffect(()=>{if(candidates.length&&!candidates.some(b=>b.id===selected)){setSelected(candidates[0].id);setForecastIndex(0);}},[candidates,selected]);
  const beach=BEACH_BY_ID.get(selected)??BEACHES[0];
  const conditionTargets=forecastTargets(beach,candidates,pageOffset);
  targets.current=conditionTargets;
  const targetKey=conditionTargets.map(b=>b.id).join(',');
  useEffect(()=>{if(!loaded)return;const timer=setTimeout(()=>void refresh(),450);return()=>clearTimeout(timer);},[loaded,targetKey,refresh]);
  const qualitySource=waterQualitySource(beach);
  const current=conditions[beach.id];const old=!!current&&(isStale(current)||(beach.waterType==='ocean'&&(!current.marineTime||Date.now()-current.marineTime*1000>3*3600000))||(!current.weatherTime||Date.now()-current.weatherTime*1000>3*3600000));
  const mapAlerts=useMemo(()=>Object.keys(conditions).filter(id=>conditions[id].alerts.length+(conditions[id].forecastAlerts?.length??0)>0),[conditions]);
  const choose=useCallback((id: string)=>{const chosen=BEACH_BY_ID.get(id);if(!chosen)return;
    if(!candidates.some(b=>b.id===id)){updateQuery('');setCountryCode(chosen.country??'');setStateCode(chosen.state??'');setOnlyFavorites(false);setActivity('all');setOrigin(undefined);}
    setSelected(id);setForecastIndex(0);onFocusBeach(detailOffset.current);},[onFocusBeach,candidates]);
  function toggleFavorite(id: string) {setFavorites(items=>items.includes(id)?items.filter(x=>x!==id):[...items,id]);}
  async function useLocation() {
    setLocating(true);setError('');
    try {const p=await locate();setOrigin({latitude:p.latitude,longitude:p.longitude});setOriginLabel('Your location');updateQuery('');setCountryCode('');setStateCode('');}
    catch(e){setError(e instanceof Error?e.message:'Location unavailable');}finally{setLocating(false);}
  }
  async function searchArea() {
    const request=++placeRequest.current;setFindingPlace(true);setError('');
    try{const found=await findPlaces(query);if(request!==placeRequest.current)return;setPlaces(found);if(!found.length)setError('No places found. Try a city name or use the country filter.');}
    catch(e){if(request===placeRequest.current)setError(e instanceof Error?e.message:'Place search unavailable');}finally{if(request===placeRequest.current)setFindingPlace(false);}
  }
  async function toggleAlerts() {
    if(alertsEnabled){setAlertsEnabled(false);return;}
    try {const granted=await enableNotifications();setAlertsEnabled(true);if(!granted)setError('Device notifications are unavailable or declined. Favorite-beach alerts will still appear in the app.');}
    catch{setAlertsEnabled(true);setError('Device notifications unavailable. You can still read alerts in the app.');}
  }
  const activeInbox=inbox.filter(n=>Date.parse(n.alert.expires)>Date.now());
  return <>
    <View style={s.hero}><View style={s.row}><Text style={s.eyebrow}>DISCOVER YOUR BEACH</Text><Text style={s.region}>AROUND THE WORLD</Text></View><Text style={s.title}>Your next{ '\n' }beach day.</Text><Text style={s.subtitle}>Explore the shoreline. Follow the conditions. Keep your favorite beaches close.</Text><View style={s.row}><Text style={s.heroStat}>{BEACHES.length.toLocaleString()} beach records · {AVAILABLE_COUNTRIES.filter(c=>c.code!=='ZZ').length} countries & territories</Text><Text style={s.small}>Global weather · Regional ocean forecasts</Text></View></View>
    <View style={s.search}><Icon name="search" color="#18E0D1" /><TextInput accessibilityLabel="Search beaches, regions or countries" placeholder="Beach, country, or city" placeholderTextColor="#839ca9" value={query} onChangeText={value=>{updateQuery(value);setPlaces([]);}} onSubmitEditing={()=>void searchArea()} style={s.input} /><Pressable accessibilityRole="button" accessibilityLabel="Clear search" onPress={()=>{updateQuery('');setPlaces([]);}}><Text style={s.link}>Clear</Text></Pressable></View>
    <View style={s.row}><Action label={countryCode?`${COUNTRY_NAMES[countryCode]} ▾`:'All countries ▾'} onPress={()=>setShowCountries(true)}/>{(!countryCode||countryCode==='US')&&<Action label={stateCode?`${STATE_NAMES[stateCode]} ▾`:'All states & territories ▾'} onPress={()=>setShowStates(true)} />}<Action label={findingPlace?'Finding places…':'Find city / place'} disabled={findingPlace||query.trim().length<2} onPress={()=>void searchArea()} /></View>
    {!!places.length&&<View style={s.card}><Text style={s.section}>Choose a search area</Text><Text style={s.small}>Place search: Open-Meteo / GeoNames</Text>{places.map(place=><Action key={place.id} label={place.label} onPress={()=>{setOrigin(place);setOriginLabel(place.label);updateQuery('');setCountryCode('');setStateCode('');setPlaces([]);}}/>)}</View>}
    <Modal visible={showCountries} transparent animationType="slide" onRequestClose={()=>setShowCountries(false)}><View style={{flex:1,backgroundColor:'#0009',justifyContent:'center',padding:24}}><View style={[s.card,{maxHeight:'85%'}]}><Text style={s.section}>Choose a country or territory</Text><TextInput accessibilityLabel="Find a country" placeholder="Search countries" placeholderTextColor="#839ca9" value={countryQuery} onChangeText={setCountryQuery} style={s.input}/><Action label="Worldwide" onPress={()=>{setCountryCode('');setStateCode('');setOrigin(undefined);updateQuery('');setShowCountries(false);}}/><ScrollView contentContainerStyle={{gap:10}}>{AVAILABLE_COUNTRIES.filter(c=>`${c.name} ${c.code}`.toLowerCase().includes(countryQuery.toLowerCase())).map(c=><Action key={c.code} label={`${c.name} (${c.count.toLocaleString()})`} selected={c.code===countryCode} onPress={()=>{setCountryCode(c.code);setStateCode('');updateQuery('');setOrigin(undefined);setShowCountries(false);}}/>)}</ScrollView><Action label="Close" onPress={()=>setShowCountries(false)}/></View></View></Modal>
    <Modal visible={showStates} transparent animationType="slide" onRequestClose={()=>setShowStates(false)}><View style={{flex:1,backgroundColor:'#0009',justifyContent:'center',padding:24}}><View style={[s.card,{maxHeight:'80%'}]}><Text style={s.section}>Choose a state or territory</Text><Action label="All states & territories" onPress={()=>{setStateCode('');setOrigin(undefined);setShowStates(false);}}/><ScrollView contentContainerStyle={{gap:10}}>{AVAILABLE_STATES.map(code=><Action key={code} label={`${STATE_NAMES[code]} (${BEACHES.filter(b=>b.state===code).length})`} selected={code===stateCode} onPress={()=>{setCountryCode(['PR','VI','GU','MP','AS'].includes(code)?code:'US');setStateCode(code);updateQuery('');setOrigin(undefined);setShowStates(false);}}/>)}</ScrollView><Action label="Close" onPress={()=>setShowStates(false)}/></View></View></Modal>
    <View style={s.row}><Action label="Explore all" selected={activity==='all'} onPress={()=>setActivity('all')} /><Action label="Swimming" selected={activity==='swimming'} onPress={()=>setActivity('swimming')} /><Action label="Surfing" selected={activity==='surfing'} onPress={()=>setActivity('surfing')} /><Action label={`★ Favorites (${favorites.length})`} selected={onlyFavorites} onPress={()=>setOnlyFavorites(!onlyFavorites)} /></View>
    <View style={s.row}><Action label={locating?'Finding you…':origin?'Update location':'◎ Near me'} disabled={locating} onPress={()=>void useLocation()} />{origin&&<><Text style={s.small}>{originLabel}</Text><Action label={`Within ${radius} km`} onPress={()=>setRadius(radius===50?100:radius===100?200:50)} /><Action label="Clear distance filter" onPress={()=>setOrigin(undefined)} /></>}<Action label={loading?'Refreshing…':'↻ Refresh'} disabled={loading} onPress={()=>void refresh(true)} /></View>
    {!!error&&<Text accessibilityRole="alert" style={s.warning}>{error}</Text>}
    <View style={s.mapCard}><BeachMap beaches={candidates} overview={!countryCode&&!stateCode&&!query&&!origin&&!onlyFavorites} selected={selected} favorites={favorites} alerts={mapAlerts} origin={origin} onSelect={choose} /><View style={[s.row,{padding:14}]}><Text style={s.small}>● Beach</Text><Text style={s.warning}>● Alert / forecast threshold</Text><Text style={s.small}>★ Favorite · Tap a cluster to zoom · Tap a beach to explore</Text></View></View>
    {!!beaches.length&&<View style={s.detail} onLayout={e=>{detailOffset.current=e.nativeEvent.layout.y;}}>
      <View style={s.rowBetween}><View style={{flex:1,gap:5}}><Text style={s.eyebrow}>YOUR BEACH BRIEF</Text><Text style={s.beachTitle}>{beach.name}</Text><Text style={s.small}>{beach.area}{origin?` · ${distanceKm(origin,beach).toFixed(1)} km away`:''}</Text></View><Pressable accessibilityRole="button" accessibilityLabel={`${favorites.includes(beach.id)?'Unfavorite':'Favorite'} ${beach.name}`} accessibilityState={{selected:favorites.includes(beach.id)}} disabled={!loaded} onPress={()=>toggleFavorite(beach.id)} style={s.star}><Text style={{fontSize:27,color:'#18E0D1'}}>{favorites.includes(beach.id)?'★':'☆'}</Text></Pressable></View>
      <Text style={s.body}>{beach.description}</Text>{beach.sourceType&&<Text style={s.small}>{beach.sourceType} record {beach.sourceId} · {beach.waterType==='ocean'?'Coastal':beach.waterType==='lake'?'Inland water':'Water type unclassified'} · Access and activity suitability need local verification.</Text>}
      {!current?<View style={s.row}><ActivityIndicator color="#18E0D1"/><Text style={s.small}>Loading conditions…</Text></View>:<>
        <Text style={old?s.warning:s.updated}>{old?'SAVED / OUTDATED CONDITIONS': 'LATEST MODEL FORECAST'} · Retrieved {new Date(current.fetchedAt).toLocaleDateString()} {time(current.fetchedAt)}</Text>
        {current.marineTime&&<Text style={s.small}>Marine valid {new Date(current.marineTime*1000).toLocaleString()}</Text>}
        <View style={s.metrics}><Metric label="Wave height" amount={value(current.wave,' m')} /><Metric label="Wave period" amount={value(current.period,' s')} /><Metric label="Water temp" amount={value(current.water,'°C')} /><Metric label="Wind" amount={value(current.wind,' km/h')} /></View>
        <Text style={s.small}>Air {value(current.air,'°C')}{current.weatherTime?` · Weather valid ${time(current.weatherTime*1000)}`:''}. Regional model estimates; local surf and shore conditions can differ.</Text>
        {!!current.marineScope&&<Text style={s.small}>{current.marineScope}</Text>}
        {(current.marineError||current.weatherError)&&<Text style={s.warning}>{[current.marineError,current.weatherError].filter(Boolean).join(' · ')}</Text>}
        {!!current.hours.length&&<><View style={s.rowBetween}><Text style={s.section}>Next 24 hours</Text><Text style={s.small}>Wave height</Text></View><WaveChart hours={current.hours} /><View style={s.row}>{current.hours.filter((_,i)=>i%3===0).map(h=><Action key={h.time} label={time(h.time*1000)} selected={current.hours[forecastIndex]?.time===h.time} onPress={()=>setForecastIndex(current.hours.indexOf(h))} />)}</View><Text style={s.body}>{time(current.hours[forecastIndex]?.time*1000)} · Waves {value(current.hours[forecastIndex]?.wave,' m')} · Period {value(current.hours[forecastIndex]?.period,' s')}</Text><Text style={s.small}>Modeled sea level including tides: {value(current.hours[forecastIndex]?.seaLevel,' m')} relative to mean sea level. Not a local tide-gauge reading.</Text></>}
        <View style={s.notice}><Text style={s.section}>Worldwide forecast alerts</Text><Text style={s.small}>{FORECAST_RULES}</Text>{current.forecastError&&<Text style={s.warning}>{current.forecastError}</Text>}{current.forecastAlerts?.length?current.forecastAlerts.map(a=><View key={a.id} style={{gap:8}}><Text style={s.warning}>{a.event}</Text><Text style={s.body}>{a.headline}</Text><Text style={s.small}>{a.description}</Text><Text style={s.small}>{a.instruction}</Text><Source label="Forecast data source" url={a.url}/></View>):<Text style={s.body}>{current.forecastError?'Forecast alert status is incomplete.':'No configured thresholds triggered in the returned forecast data. This does not establish water safety.'}</Text>}<Text style={s.small}>{current.marineScope||current.marineError?'Wave checks unavailable or limited; see marine coverage above.':'Ocean wave checks use a regional model, not a local surf observation.'}</Text></View>
        <View style={s.notice}><Text style={s.section}>Official weather advisories</Text>{current.alertsScope?<Text style={s.body}>{current.alertsScope}</Text>:current.alertsError?<Text style={s.warning}>Alert feed unavailable. Advisory status is unknown.</Text>:current.alerts.length?current.alerts.map(a=><View key={a.id} style={{gap:8}}><Text style={s.warning}>{a.event} · {a.severity}</Text><Text style={s.body}>{a.headline}</Text><Text style={s.small}>{a.instruction||a.description}</Text><Text style={s.small}>Expires {new Date(a.expires).toLocaleString()}</Text><Source label="Read NWS notice" url={a.url}/></View>):<Text style={s.body}>No active NWS alerts returned at the last check. This does not establish water safety.</Text>}</View>
      </>}
      <View style={s.waterQuality}><Text style={s.section}>Water quality & beach closures</Text><Text style={s.body}>Check the local beach programme before water contact. Water-quality status is not automatically monitored here.</Text><Source label={qualitySource.label} url={qualitySource.url}/></View>
      <View style={s.row}>{beach.amenities.map(a=><Text style={s.amenity} key={a}>{a}</Text>)}</View><Source label="Beach visitor information" url={beach.source}/>
      <View style={s.row}><Action label="Open directions ↗" onPress={()=>void Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${beach.latitude},${beach.longitude}`)} /><Action label="Analyze your footage →" selected onPress={onMonitor}/></View>
      <View style={s.row}><Source label="Open-Meteo / DWD marine & weather" url="https://open-meteo.com/"/>{(!beach.country||['US','PR','VI','GU','MP','AS'].includes(beach.country))&&<Source label="National Weather Service" url={`https://forecast.weather.gov/MapClick.php?lat=${beach.latitude}&lon=${beach.longitude}`}/>}</View>
    </View>}
    <View style={s.card}><View style={s.rowBetween}><View style={{flex:1,gap:5}}><Text style={s.section}>Your coast, on your radar.</Text><Text style={s.small}>Forecast alerts for every favorite beach worldwide. Official warnings are added where supported.</Text></View><Icon name="bell" color="#18E0D1" size={25}/></View><View style={s.row}><Action label={alertsEnabled?'Alerts on · Pause':'Enable beach alerts'} selected={alertsEnabled} disabled={!loaded} onPress={()=>void toggleAlerts()}/><Action label={`Inbox (${activeInbox.length})`} selected={showInbox} onPress={()=>setShowInbox(!showInbox)}/>{alertsEnabled&&<Action label={checkingAlerts?'Checking…':'Check now'} disabled={checkingAlerts} onPress={()=>void checkAlerts()}/>}</View><Text style={s.small}>{alertStatus||'Favorite any beach, then enable worldwide forecast alerts.'}</Text>{alertsEnabled&&!favorites.length&&<Text style={s.warning}>Add a favorite beach to start following its alerts.</Text>}<Text style={s.small}>{Platform.OS==='web'?'Checks run while this app is open.':'Checks run when the app opens and periodically in the background when the phone allows it.'} Alerts may be delayed. Forecast checks depend on available model data; water-quality and closure changes are not included.</Text>{showInbox&&(activeInbox.length?activeInbox.map(n=><Pressable key={n.key} accessibilityRole="button" onPress={()=>choose(n.beachId)} style={s.inbox}><Text style={s.warning}>{n.beachName} · {n.alert.event}</Text><Text style={s.body}>{n.alert.headline}</Text><Text style={s.small}>Received {new Date(n.receivedAt).toLocaleString()} · Tap to view beach</Text></Pressable>):<Text style={s.body}>No current alerts in your inbox. Expired notices are hidden.</Text>)}</View>
    <View style={s.rowBetween}><Text style={s.section}>{activity==='all'?'Explore beaches worldwide':activity==='swimming'?'Find your swimming spot':'Find your surf spot'}</Text><Text style={s.small}>{candidates.length.toLocaleString()} matches{loading?' · Updating…':''}</Text></View>
    {activity!=='all'&&<Text style={s.small}>{activity==='swimming'?'Comparing loaded coastal forecasts by lower waves and wind, then distance.':'Comparing loaded coastal forecasts by moderate waves, longer periods and lower wind, then distance.'} Only the displayed shortlist is compared. Other locations are not assessed. Official alerts lower ranking. These comparisons do not assess swimming safety or your skill level.</Text>}
    {!beaches.length&&<View style={s.card}><Text style={s.section}>No beaches match yet.</Text><Text style={s.body}>{onlyFavorites?'Try saving a beach or turning off Favorites.':'Try a different name, activity, or a wider distance.'} Try the city / place search for nearby beach records. Coverage varies by country and may omit unnamed beaches.</Text><Action label="Reset filters" onPress={()=>{updateQuery('');setOnlyFavorites(false);setActivity('all');setOrigin(undefined);setCountryCode('');setStateCode('');}}/></View>}
    {beaches.map(b=><BeachCard key={b.id} beach={b} conditions={conditions[b.id]} favorite={favorites.includes(b.id)} selected={b.id===selected} origin={origin} activity={activity} onSelect={()=>choose(b.id)} onFavorite={()=>toggleFavorite(b.id)} ready={loaded}/>)}
    <View style={s.row}>{pageOffset>0&&<Action label="← Previous" onPress={()=>setPageOffset(n=>Math.max(0,n-12))}/>}<Text style={s.small}>Showing {Math.min(pageOffset+1,candidates.length)}–{Math.min(pageOffset+12,candidates.length)} of {candidates.length.toLocaleString()}</Text>{pageOffset+12<candidates.length&&<Action label="Next 12 →" onPress={()=>setPageOffset(n=>n+12)}/>}</View>
    <View style={s.row}><Source label="GeoNames · CC BY 4.0 · adapted catalogue" url="https://www.geonames.org/"/><Source label="EPA / USGS U.S. records" url="https://www.epa.gov/beaches"/></View>
    <Text style={s.small}>GeoNames worldwide + EPA / USGS U.S. catalogue · Coverage varies; this is not every beach. Public access and activity suitability are unverified. Forecast alerts support every catalogued beach; wave coverage varies. Official warnings currently cover the U.S. and territories. Forecasts load for the displayed shortlist only. Forecasts update every 5 minutes while active. Location is used only on request, stays on this device, and is not stored. Favorites and alerts are stored on this device.</Text>
  </>;
}
function BeachCard({beach,conditions,favorite,selected,origin,activity,onSelect,onFavorite,ready}:{beach:Beach;conditions?:Conditions;favorite:boolean;selected:boolean;origin?:Position;activity:Activity;onSelect:()=>void;onFavorite:()=>void;ready:boolean}) {
  const alertText=conditions?[(conditions.alerts.length?`${conditions.alerts.length} official weather alert(s)`:''),(conditions.forecastAlerts?.length?`${conditions.forecastAlerts.length} forecast alert(s)`:''),((conditions.alertsError||conditions.forecastError)?'Some alert checks unavailable':'')].filter(Boolean).join(' · ')||'View conditions & advisories':'Select to load conditions';
  return <View style={[s.beachCard,selected&&{borderColor:'#18E0D1'}]}><Pressable accessibilityRole="button" accessibilityLabel={`View ${beach.name}`} onPress={onSelect} style={{flex:1,gap:8}}><Text style={s.section}>{beach.name}</Text><Text style={s.small}>{beach.area}{origin?` · ${distanceKm(origin,beach).toFixed(1)} km`:''}</Text><Text style={s.body}>{activityFit(beach,activity,conditions).reason}</Text><Text style={conditions&&(conditions.alerts.length+(conditions.forecastAlerts?.length??0))?s.warning:s.small}>{alertText}{conditions&&isStale(conditions)?' · Saved data':''}</Text></Pressable><Pressable accessibilityRole="button" accessibilityLabel={`${favorite?'Unfavorite':'Favorite'} ${beach.name}`} accessibilityState={{selected:favorite}} disabled={!ready} onPress={onFavorite} style={s.star}><Text style={{fontSize:25,color:'#18E0D1'}}>{favorite?'★':'☆'}</Text></Pressable></View>;
}
function WaveChart({hours}:{hours:Conditions['hours']}) {
  const maximum=Math.max(1,...hours.map(h=>h.wave??0));
  // A missing sample splits the line; never interpolate a missing forecast as zero.
  const segments:string[][]=[[]];hours.forEach((h,i)=>{if(h.wave===null){if(segments[segments.length-1].length)segments.push([]);}else segments[segments.length-1].push(`${10+i/(Math.max(1,hours.length-1))*580},${80-h.wave/maximum*65}`);});
  return <View accessible accessibilityLabel={`24 hour wave forecast, maximum ${maximum.toFixed(1)} meters`} style={s.chart}><Svg width="100%" height={90} viewBox="0 0 600 90">{segments.filter(p=>p.length>1).map((p,i)=><Polyline key={i} points={p.join(' ')} fill="none" stroke="#18E0D1" strokeWidth={3}/>)}</Svg><Text style={s.small}>{time(hours[0].time*1000)} — {time(hours[hours.length-1].time*1000)} · Upper scale {maximum.toFixed(1)} m</Text></View>;
}
const s=StyleSheet.create({
  hero:{padding:20,borderRadius:24,backgroundColor:'#113442',gap:12,borderWidth:1,borderColor:'#236273'},eyebrow:{fontFamily:'PoppinsSemiBold',fontSize:10,letterSpacing:1.8,color:'#69e5d7'},region:{fontFamily:'PoppinsMedium',fontSize:9,letterSpacing:.8,color:'#adc7cf'},title:{fontFamily:'MontserratBold',fontSize:32,lineHeight:37,color:'#f0f9f9',letterSpacing:-1.5},subtitle:{fontFamily:'PoppinsRegular',fontSize:12,lineHeight:20,color:'#bbd2d9'},heroStat:{fontFamily:'PoppinsSemiBold',color:'#e2f6f7',fontSize:12},
  row:{flexDirection:'row',flexWrap:'wrap',alignItems:'center',gap:9},rowBetween:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:12},search:{flexDirection:'row',alignItems:'center',gap:12,paddingHorizontal:16,minHeight:54,borderWidth:1,borderColor:'#344b59',borderRadius:15,backgroundColor:'#101f2a'},input:{flex:1,fontFamily:'PoppinsRegular',fontSize:13,color:'#e2f4f6',minHeight:48},action:{minHeight:42,paddingHorizontal:13,paddingVertical:10,borderRadius:24,borderWidth:1,borderColor:'#36505d',backgroundColor:'#132632',justifyContent:'center'},actionSelected:{backgroundColor:'#42e0cc',borderColor:'#42e0cc'},actionText:{fontFamily:'PoppinsSemiBold',fontSize:11,color:'#cbdee4'},mapCard:{borderRadius:22,overflow:'hidden',backgroundColor:'#112531',borderWidth:1,borderColor:'#2c4553'},detail:{padding:22,gap:18,borderRadius:24,backgroundColor:'#122733',borderWidth:1,borderColor:'#315865'},beachTitle:{fontFamily:'MontserratSemiBold',fontSize:25,lineHeight:32,color:'#f1f8f9'},star:{minWidth:48,minHeight:48,alignItems:'center',justifyContent:'center',borderRadius:16,backgroundColor:'#1c3945'},body:{fontFamily:'PoppinsRegular',fontSize:13,lineHeight:21,color:'#c6dce3'},small:{fontFamily:'PoppinsRegular',fontSize:11,lineHeight:18,color:'#9db8c4'},warning:{fontFamily:'PoppinsMedium',fontSize:11,lineHeight:18,color:'#ffd28a'},updated:{fontFamily:'PoppinsMedium',fontSize:10,letterSpacing:.6,color:'#6ce2d1'},metrics:{flexDirection:'row',flexWrap:'wrap',gap:10},metric:{flexGrow:1,flexBasis:'43%',backgroundColor:'#0b1e2b',borderRadius:15,padding:16,gap:7},metricValue:{fontFamily:'MontserratSemiBold',fontSize:22,color:'#e4f9fa'},section:{fontFamily:'PoppinsSemiBold',fontSize:15,color:'#e0f1f4'},link:{fontFamily:'PoppinsMedium',fontSize:11,lineHeight:20,color:'#66e2d6'},notice:{padding:16,borderRadius:16,borderWidth:1,borderColor:'#455462',backgroundColor:'#182c37',gap:12},waterQuality:{padding:16,borderRadius:16,backgroundColor:'#263139',gap:10},amenity:{fontFamily:'PoppinsRegular',fontSize:10,color:'#b9d6de',backgroundColor:'#1e3b48',borderRadius:9,paddingHorizontal:10,paddingVertical:6},card:{padding:20,gap:15,borderRadius:22,backgroundColor:'#10232f',borderWidth:1,borderColor:'#2a4352'},inbox:{gap:8,borderTopWidth:1,borderColor:'#34505d',paddingTop:14},beachCard:{flexDirection:'row',alignItems:'center',gap:12,padding:18,borderRadius:18,backgroundColor:'#11232f',borderWidth:1,borderColor:'#2b4351'},chart:{backgroundColor:'#0b1e2b',padding:12,borderRadius:15},
});
