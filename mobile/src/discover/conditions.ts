import { Beach, Position, Activity, distanceKm } from './beaches';
export type BeachAlert = { id: string; event: string; headline: string; description: string; instruction: string; severity: string; sent: string; expires: string; url: string };
export type ForecastHour = { time: number; wave: number | null; period: number | null; seaLevel: number | null };
export type Conditions = {
  fetchedAt: number; marineTime: number | null; weatherTime: number | null;
  wave: number | null; period: number | null; water: number | null; wind: number | null; air: number | null;
  alertsScope?: string; marineScope?: string; hours: ForecastHour[]; alerts: BeachAlert[]; marineError?: string; weatherError?: string; alertsError?: string;
};
export const validNumber = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null;
export const isStale = (conditions: Conditions, now = Date.now()) => now-conditions.fetchedAt > 30*60*1000;
async function json(url: string, signal?: AbortSignal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort',abort,{once:true});
  if(signal?.aborted) controller.abort();
  const timer = setTimeout(abort,15000);
  try {
    const response = await fetch(url,{signal:controller.signal,headers:{Accept:'application/json'}});
    if(!response.ok) throw new Error(`Source returned ${response.status}`);
    return await response.json();
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export function parseAlerts(payload: any, now = Date.now()): BeachAlert[] {
  if(!Array.isArray(payload?.features)) throw new Error('Alert source returned an invalid response');
  return payload.features.flatMap((feature: any) => {
    const p=feature.properties;
    if(!p || p.status!=='Actual' || p.messageType==='Cancel' || !Number.isFinite(Date.parse(p.expires)) || Date.parse(p.expires)<=now) return [];
    const id=String(p.id??feature.id??'');
    if(!id) return [];
    return [{id,event:String(p.event??'Weather alert'),headline:String(p.headline??p.event??'Weather alert'),description:String(p.description??''),instruction:String(p.instruction??''),severity:String(p.severity??'Unknown'),sent:String(p.sent??''),expires:p.expires,url:`https://forecast.weather.gov/showsigwx.php?warnzone=${encodeURIComponent((p.geocode?.UGC??[])[0]??'')}`}];
  });
}
export const supportsAlerts=(beach: Position & {country?:string})=>!beach.country||['US','PR','VI','GU','MP','AS'].includes(beach.country);
export async function fetchAlerts(beach: Position & {country?:string}, signal?: AbortSignal): Promise<BeachAlert[]> {
  if(!supportsAlerts(beach))throw new Error('Official alert coverage is limited to the United States and its territories.');
  return parseAlerts(await json(`https://api.weather.gov/alerts/active?point=${beach.latitude},${beach.longitude}`,signal));
}
export async function fetchConditions(beach: Beach, signal?: AbortSignal): Promise<Conditions> {
  const coords=`latitude=${beach.latitude}&longitude=${beach.longitude}`;
  const marineSupported=beach.waterType!=='lake';
  const [marine,weather,alerts] = await Promise.allSettled([
    marineSupported?json(`https://marine-api.open-meteo.com/v1/marine?${coords}&current=wave_height,wave_period,sea_surface_temperature&hourly=wave_height,wave_period,sea_level_height_msl&forecast_days=2&timeformat=unixtime&cell_selection=sea`,signal):Promise.resolve(null),
    json(`https://api.open-meteo.com/v1/forecast?${coords}&current=temperature_2m,wind_speed_10m&timeformat=unixtime`,signal),
    supportsAlerts(beach)?fetchAlerts(beach,signal):Promise.resolve([]),
  ]);
  const candidate=marine.status==='fulfilled'?marine.value:null;
  const gridDistance=candidate&&Number.isFinite(candidate.latitude)&&Number.isFinite(candidate.longitude)?distanceKm(beach,{latitude:candidate.latitude,longitude:candidate.longitude}):null;
  const m=beach.waterType==='unknown'&&(gridDistance===null||gridDistance>20)?null:candidate;
  const w=weather.status==='fulfilled'?weather.value:null;
  const error=(r: PromiseSettledResult<unknown>)=>r.status==='rejected'?'Temporarily unavailable':undefined;
  const now=Date.now();
  return {fetchedAt:now,marineTime:validNumber(m?.current?.time),weatherTime:validNumber(w?.current?.time),
    wave:validNumber(m?.current?.wave_height),period:validNumber(m?.current?.wave_period),water:validNumber(m?.current?.sea_surface_temperature),
    wind:validNumber(w?.current?.wind_speed_10m),air:validNumber(w?.current?.temperature_2m),
    hours:(Array.isArray(m?.hourly?.time)?m.hourly.time:[]).map((time: number,i: number)=>({time,wave:validNumber(m.hourly.wave_height?.[i]),period:validNumber(m.hourly.wave_period?.[i]),seaLevel:validNumber(m.hourly.sea_level_height_msl?.[i])})).filter((h: ForecastHour)=>h.time*1000>=now-3600000).slice(0,24),
    alerts:alerts.status==='fulfilled'?alerts.value:[],alertsScope:supportsAlerts(beach)?undefined:'Official alert coverage is not available here. Check local weather and beach authorities; this app does not monitor their warnings.',marineScope:!marineSupported?'Ocean forecasts are not provided for known inland waters.':beach.waterType==='unknown'?(m?'Regional offshore model within 20 km. Water type and local activity suitability are unverified.':'Water type unverified; no nearby ocean model cell confirmed. Ocean fields are withheld.'):undefined,marineError:marineSupported&&!m?.current?'Marine forecast unavailable':undefined,weatherError:!w?.current?'Weather unavailable':error(weather),alertsError:error(alerts)};
}
export function activityFit(beach: Beach, activity: Activity, c?: Conditions): {score: number; reason: string} {
  if(beach.access==='private')return {score:-10000,reason:'Private access reported · verify permission'};
  if(activity==='all'&&beach.waterType==='unknown')return {score:0,reason:'Mapped beach · activities and access unverified'};
  if(activity==='all') return {score:0,reason:beach.activities.filter(a=>a!=='all').join(' · ')};
  if(!beach.activities.includes(activity)) return {score:-10000,reason:'Not listed for this activity'};
  if(beach.waterType==='lake')return {score:-500,reason:'Inland / unclassified water · local suitability unverified'};
  if(!c || isStale(c) || c.wave===null || c.wind===null || c.alertsError || !c.marineTime || Date.now()-c.marineTime*1000>3*3600000 || !c.weatherTime || Date.now()-c.weatherTime*1000>3*3600000) return {score:-500,reason:'Conditions incomplete · check details'};
  if(c.alerts.some(a=>['Severe','Extreme'].includes(a.severity))) return {score:-1000,reason:'Official warning active · review before visiting'};
  const penalty=c.alerts.length?100:0;
  if(activity==='swimming') return {score:100-c.wave*30-c.wind-penalty,reason:`${c.alertsScope?'Alerts not covered · ':''}${c.wave.toFixed(1)} m waves · ${c.wind.toFixed(0)} km/h wind`};
  if(c.period===null) return {score:-500,reason:'Wave period unavailable'};
  return {score:100-Math.abs(c.wave-1.2)*20+c.period-c.wind-penalty,reason:`${c.alertsScope?'Alerts not covered · ':''}${c.wave.toFixed(1)} m waves · ${c.period.toFixed(0)} s period`};
}
export function rankBeaches(beaches: Beach[], activity: Activity, conditions: Record<string,Conditions>, origin?: Position): Beach[] {
  return [...beaches].sort((a,b)=>{
    const fit=activityFit(b,activity,conditions[b.id]).score-activityFit(a,activity,conditions[a.id]).score;
    return fit || (origin?distanceKm(origin,a)-distanceKm(origin,b):0);
  });
}

/** Selected location plus one results page: nationwide browsing never fans out over the catalogue. */
export function forecastTargets(selected: Beach, candidates: Beach[], offset=0): Beach[] {
  return [...new Map([selected,...candidates.slice(offset,offset+12)].map(beach=>[beach.id,beach])).values()];
}
