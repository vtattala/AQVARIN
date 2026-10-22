export type Activity = 'all' | 'swimming' | 'surfing';
export type Position = { latitude: number; longitude: number };
export type Beach = Position & {
  id: string; name: string; area: string; activities: Activity[];
  description: string; amenities: string[]; source: string;
};
const county = 'https://www.sandiego.org/explore/things-to-do/beaches-bays';
export const BEACHES: Beach[] = [
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
export const COUNTY_URL = 'https://www.sdbeachinfo.com/';
export function distanceKm(a: Position, b: Position): number {
  const radians = (n: number) => n * Math.PI / 180;
  const dLat = radians(b.latitude-a.latitude), dLon = radians(b.longitude-a.longitude);
  const h = Math.sin(dLat/2)**2 + Math.cos(radians(a.latitude))*Math.cos(radians(b.latitude))*Math.sin(dLon/2)**2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1,h)));
}
