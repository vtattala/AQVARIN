import { Position } from './beaches';
export type Place = Position & {id:string;label:string};
export async function findPlaces(query: string): Promise<Place[]> {
  if(query.trim().length<2)return [];
  const response=await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query.trim())}&count=15&language=en&format=json`,{signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw new Error('Place search unavailable. Try a beach name or state instead.');
  const payload=await response.json();
  if(!Array.isArray(payload.results))return [];
  return payload.results.filter((r:any)=>['US','PR','VI','GU','MP','AS'].includes(r.country_code)&&Number.isFinite(r.latitude)&&Number.isFinite(r.longitude)).slice(0,6).map((r:any)=>({id:String(r.id),latitude:r.latitude,longitude:r.longitude,label:[r.name,r.admin1??r.country].filter(Boolean).join(', ')}));
}
