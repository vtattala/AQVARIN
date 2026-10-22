import nationalRecords from './data/us-beaches.json';
import worldRecords from './data/world-beaches.json';
import countryNames from './data/countries.json';
export type Activity = 'all' | 'swimming' | 'surfing';
export type Position = { latitude: number; longitude: number };
export type Beach = Position & {
  id: string; name: string; area: string; activities: Activity[];
  description: string; amenities: string[]; source: string;
  country?: string; countryName?: string; aliases?: string[]; region?: string; state?: string; stateName?: string; county?: string; waterType?: 'ocean'|'lake'|'unknown'; access?: 'private'|'unknown'; sourceType?: string; sourceId?: string;
};
const county = 'https://www.sandiego.org/explore/things-to-do/beaches-bays';
const CURATED_BEACHES: Beach[] = [
  {id:'oceanside',name:'Oceanside City Beach',area:'Oceanside',latitude:33.1909,longitude:-117.3856,activities:['swimming','surfing'],description:'An open-ocean beach beside the pier. Conditions vary along the shore.',amenities:['Restrooms','Pier'],source:county},
  {id:'carlsbad',name:'Carlsbad State Beach',area:'Carlsbad',latitude:33.1497,longitude:-117.3470,activities:['swimming','surfing'],description:'A long sandy shoreline below the coastal bluffs.',amenities:['Restrooms','Parking'],source:'https://www.parks.ca.gov/?page_id=653'},
  {id:'moonlight',name:'Moonlight State Beach',area:'Encinitas',latitude:33.0470,longitude:-117.2987,activities:['swimming','surfing'],description:'A broad sandy beach near downtown Encinitas.',amenities:['Restrooms','Picnic areas','Parking'],source:'https://www.parks.ca.gov/?page_id=659'},
  {id:'swamis',name:'Swami’s Beach',area:'Encinitas',latitude:33.0347,longitude:-117.2920,activities:['surfing'],description:'A reef surf break with stair access. Better suited to experienced surfers.',amenities:['Restrooms','Parking','Stair access'],source:county},
  {id:'delmar',name:'Del Mar City Beach',area:'Del Mar',latitude:32.9664,longitude:-117.2687,activities:['swimming','surfing'],description:'An open sandy shoreline near the village and coastal parks.',amenities:['Restrooms','Picnic areas'],source:county},
  {id:'torrey',name:'Torrey Pines State Beach',area:'San Diego',latitude:32.9325,longitude:-117.2608,activities:['swimming','surfing'],description:'Open coast beneath sandstone bluffs. Observe posted bluff and beach restrictions.',amenities:['Restrooms','Parking'],source:'https://www.parks.ca.gov/?page_id=658'},
  {id:'shores',name:'La Jolla Shores',area:'La Jolla',latitude:32.8570,longitude:-117.2572,activities:['swimming','surfing'],description:'A sandy bay with separate activity areas. Follow the posted swimming and surfing zones.',amenities:['Restrooms','Picnic areas','Parking'],source:county},
  {id:'cove',name:'La Jolla Cove',area:'La Jolla',latitude:32.8508,longitude:-117.2726,activities:['swimming'],description:'A small rocky cove popular for ocean swimming. Respect wildlife closures and local signs.',amenities:['Restrooms','Stair access'],source:county},
  {id:'pacific',name:'Pacific Beach',area:'San Diego',latitude:32.7975,longitude:-117.2570,activities:['swimming','surfing'],description:'A lively ocean beach beside the boardwalk and Crystal Pier.',amenities:['Restrooms','Boardwalk'],source:county},
  {id:'mission',name:'Mission Beach',area:'San Diego',latitude:32.7707,longitude:-117.2520,activities:['swimming','surfing'],description:'A wide ocean beach with boardwalk access. Follow local activity zones.',amenities:['Restrooms','Boardwalk','Parking'],source:county},
  {id:'ocean',name:'Ocean Beach',area:'San Diego',latitude:32.7495,longitude:-117.2528,activities:['swimming','surfing'],description:'An exposed beach near the San Diego River. Check county water-quality notices.',amenities:['Restrooms','Parking'],source:county},
  {id:'coronado',name:'Coronado Central Beach',area:'Coronado',latitude:32.6806,longitude:-117.1797,activities:['swimming','surfing'],description:'A broad sandy beach on Coronado. Check current county advisories before water contact.',amenities:['Restrooms','Parking'],source:county},
  {id:'silver',name:'Silver Strand State Beach',area:'Coronado',latitude:32.6359,longitude:-117.1414,activities:['swimming','surfing'],description:'Open Pacific shoreline on the Silver Strand. Check water-quality notices before visiting.',amenities:['Restrooms','Parking','Picnic areas'],source:'https://www.parks.ca.gov/?page_id=654'},
  {id:'imperial',name:'Imperial Beach',area:'Imperial Beach',latitude:32.5793,longitude:-117.1320,activities:['swimming','surfing'],description:'The county’s southern oceanfront. Water-contact restrictions can apply; check the county notice.',amenities:['Restrooms','Pier','Parking'],source:county},
];
export const STATE_NAMES: Record<string,string> = {
  AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',DC:'District of Columbia',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming',PR:'Puerto Rico',VI:'U.S. Virgin Islands',GU:'Guam',MP:'Northern Mariana Islands',AS:'American Samoa',
};
const normalize = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g,'').replace(/state|county|city/g,'');
const curated = CURATED_BEACHES.map(b=>({...b,state:'CA',stateName:'California',county:'San Diego',country:'US',countryName:'United States',waterType:'ocean' as const}));
const national: Beach[] = nationalRecords.filter(r=>!curated.some(b=>{
  if(r.state!=='CA'||Math.abs(b.latitude-r.latitude)>.01)return false;
  const a=normalize(b.name),name=normalize(r.name);
  return (a.includes(name)||name.includes(a))&&distanceKm(b,r)<.8;
})).map(r=>({
  ...r,country:['PR','VI','GU','MP','AS'].includes(r.state)?r.state:'US',countryName:['PR','VI','GU','MP','AS'].includes(r.state)?STATE_NAMES[r.state]:'United States',waterType:r.waterType as Beach['waterType'],access:r.access as Beach['access'],
  stateName:STATE_NAMES[r.state]??r.state,area:`${r.county ? r.county+', ' : ''}${STATE_NAMES[r.state]??r.state}`,
  activities:r.waterType==='ocean'?['swimming','surfing']:['swimming'],
  description:r.access==='private'?'Private access reported by EPA. Verify permission before visiting.':r.sourceType==='EPA'?'A beach reported to EPA’s coastal and Great Lakes programme. Verify local access, posted activity zones and current water-quality notices.':'A named beach in USGS geographic records. Public access, swimming suitability and facilities have not been verified.',
  amenities:[],source:r.sourceType==='EPA'?'https://beacon.epa.gov/ords/beacon2/r/beacon_apex/beacon2/map-page':'https://www.usgs.gov/us-board-on-geographic-names/download-gnis-data',
}));
export const COUNTRY_NAMES: Record<string,string>={...countryNames,ZZ:'Unassigned region'};
const us=[...curated,...national];
const cells=new Map<string,Beach[]>();
for(const b of us){const key=`${Math.floor(b.latitude*100)},${Math.floor(b.longitude*100)}`;cells.set(key,[...(cells.get(key)??[]),b]);}
const global: Beach[]=worldRecords.filter(r=>{
  for(let y=-1;y<=1;y++)for(let x=-1;x<=1;x++){
    const group=cells.get(`${Math.floor(r.latitude*100)+y},${Math.floor(r.longitude*100)+x}`)??[];
    if(group.some(b=>normalize(b.name)===normalize(r.name)&&distanceKm(b,r)<.8))return false;
  }return true;
}).map(r=>({...r,countryName:COUNTRY_NAMES[r.country]??r.country,area:[r.region,COUNTRY_NAMES[r.country]??r.country].filter(Boolean).join(', '),
  waterType:r.waterType as Beach['waterType'],access:('access' in r?r.access:'unknown') as Beach['access'],
  activities:r.waterType==='lake'?['swimming']:['swimming','surfing'],amenities:[],
  description:('access' in r&&r.access==='private')?'Restricted access mapped. Verify permission before visiting.':'A mapped beach. Public access, swimming and surfing suitability, lifeguards and facilities have not been verified. Check local signs and authorities.',
  source:r.sourceType==='GeoNames'?`https://www.geonames.org/${r.sourceId}`:`https://www.openstreetmap.org/${r.sourceId}`,
}));
export const BEACHES: Beach[] = [...us,...global];
export const AVAILABLE_COUNTRIES=Object.entries(COUNTRY_NAMES).map(([code,name])=>({code,name,count:BEACHES.filter(b=>b.country===code).length})).filter(c=>c.count).sort((a,b)=>a.name.localeCompare(b.name));
export const BEACH_BY_ID = new Map(BEACHES.map(b=>[b.id,b]));
export const AVAILABLE_STATES = Object.keys(STATE_NAMES).filter(code=>BEACHES.some(b=>b.state===code)).sort((a,b)=>STATE_NAMES[a].localeCompare(STATE_NAMES[b]));
export const EPA_BEACH_URL='https://www.epa.gov/beaches/find-information-about-particular-us-beach';
export function waterQualitySource(beach: Beach): {label:string;url:string} {
  if(beach.country&&beach.country!=='US'&&!['PR','VI','GU','MP','AS'].includes(beach.country))return {label:'Beach geographic source · consult the local authority for water quality',url:beach.source};
  return beach.state==='CA'&&beach.county==='San Diego'?{label:'San Diego County Beach & Bay notices',url:COUNTY_URL}:{label:`Official beach programmes · ${beach.stateName??beach.state??'United States'}`,url:EPA_BEACH_URL};
}
export type BeachSearch = {query:string;activity:Activity;country?:string;state?:string;origin?:Position;radius?:number;favorites?:string[]};
export function searchBeaches(options: BeachSearch): Beach[] {
  const searchable=(text:string)=>text.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[’‘ʻ']/g,'').replace(/[^\p{L}\p{N}]+/gu,' ');
  const words=searchable(options.query).trim().split(/\s+/).filter(Boolean);
  const found=BEACHES.filter(b=>{
    const text=searchable(`${b.name} ${b.area} ${b.state??''} ${b.country??''} ${(b.aliases??[]).join(' ')}`);
    return words.every(word=>text.includes(word))&&(!options.country||b.country===options.country)&&(!options.state||b.state===options.state)&&
      (options.activity==='all'||(b.access!=='private'&&b.activities.includes(options.activity)))&&
      (!options.favorites||options.favorites.includes(b.id))&&
      (!options.origin||distanceKm(options.origin,b)<=(options.radius??50));
  });
  return options.origin?found.sort((a,b)=>distanceKm(options.origin!,a)-distanceKm(options.origin!,b)):found;
}
export const COUNTY_URL = 'https://www.sdbeachinfo.com/';
export function distanceKm(a: Position, b: Position): number {
  const radians = (n: number) => n * Math.PI / 180;
  const dLat = radians(b.latitude-a.latitude), dLon = radians(b.longitude-a.longitude);
  const h = Math.sin(dLat/2)**2 + Math.cos(radians(a.latitude))*Math.cos(radians(b.latitude))*Math.sin(dLon/2)**2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1,h)));
}
