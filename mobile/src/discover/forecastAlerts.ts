import type { Beach } from './beaches';
import type { BeachAlert } from './conditions';
export const FORECAST_RULES='Next 12 hours: waves ≥ 2 m, wind ≥ 35 km/h or gusts ≥ 50 km/h, thunderstorm forecast, UV ≥ 8. AQVARIN thresholds are not official warnings or a safety assessment.';
/** Evaluate timestamped model samples only. Missing values never become zero or an all-clear. */
export function forecastAlerts(beach: Beach, marine: any, weather: any, now=Date.now()): BeachAlert[] {
  const samples=(payload:any,field:string)=>{
    const result:{time:number;value:number}[]=[];
    const add=(time:unknown,value:unknown)=>{if(typeof time==='number'&&Number.isFinite(time)&&typeof value==='number'&&Number.isFinite(value)&&time*1000>=now-3600000&&time*1000<=now+12*3600000)result.push({time,value});};
    add(payload?.current?.time,payload?.current?.[field]);
    if(Array.isArray(payload?.hourly?.time))payload.hourly.time.forEach((time:unknown,i:number)=>add(time,payload.hourly[field]?.[i]));
    return result;
  };
  const day=new Date(now).toISOString().slice(0,10);
  const alerts:BeachAlert[]=[];
  const rule=(key:string,event:string,values:{time:number;value:number}[],test:(value:number)=>boolean,unit:string)=>{
    const hits=values.filter(s=>test(s.value));if(!hits.length)return;
    const first=Math.min(...hits.map(s=>s.time)),last=Math.max(...hits.map(s=>s.time));
    const detail=key==='storm'?'Thunderstorms appear in the model forecast':`Peak ${Math.max(...hits.map(s=>s.value)).toFixed(1)}${unit} in returned model samples`;
    alerts.push({id:`aqvarin-forecast:${beach.id}:${key}:${day}`,kind:'forecast',event:`Forecast · ${event}`,headline:`${event} forecast near ${beach.name}`,description:`${detail}. Forecast window ${new Date(first*1000).toLocaleString()}–${new Date((last+3600)*1000).toLocaleString()}. AQVARIN model estimate; not an official warning.`,instruction:'Check local weather and beach authorities before visiting. Forecasts may miss local hazards; no alert does not mean conditions are safe.',severity:'Forecast',sent:`${day}T00:00:00.000Z`,expires:new Date((last+3600)*1000).toISOString(),url:key==='wave'?'https://open-meteo.com/en/docs/marine-weather-api':'https://open-meteo.com/en/docs'});
  };
  rule('wave','Large waves',samples(marine,'wave_height'),v=>v>=2,' m');
  rule('wind','Strong wind',samples(weather,'wind_speed_10m'),v=>v>=35,' km/h');
  rule('gust','Strong gusts',samples(weather,'wind_gusts_10m'),v=>v>=50,' km/h');
  rule('storm','Thunderstorms',samples(weather,'weather_code'),v=>[95,96,99].includes(v),'');
  rule('uv','High UV',samples(weather,'uv_index'),v=>v>=8,' UV index');
  return alerts;
}
