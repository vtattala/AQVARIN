import AsyncStorage from '@react-native-async-storage/async-storage';
import { BEACHES } from './beaches';
import { BeachAlert, fetchConditions, supportsAlerts } from './conditions';
import { notify } from './device';
export const WATCH_KEY='aqvarin.discover.watch.v1';
const SEEN_KEY='aqvarin.discover.seen.v1';
export const INBOX_KEY='aqvarin.discover.inbox.v1';
export type Watch = {favorites:string[];enabled:boolean};
export type Notice = {key:string;beachId:string;beachName:string;alert:BeachAlert;receivedAt:number};
let checking: Promise<string> | null=null;
export async function checkFavoriteAlerts(): Promise<string> {
  if(checking)return checking;
  checking=check().finally(()=>{checking=null;});return checking;
}
async function check() {
  const watch: Watch=JSON.parse(await AsyncStorage.getItem(WATCH_KEY)??'{"favorites":[],"enabled":false}');
  if(!watch.enabled||!watch.favorites.length)return 'Add a favorite beach and enable alerts to start monitoring.';
  const previous: string[]=JSON.parse(await AsyncStorage.getItem(SEEN_KEY)??'[]');
  const seen=new Set(previous);
  const inbox: Notice[]=JSON.parse(await AsyncStorage.getItem(INBOX_KEY)??'[]');
  const beaches=BEACHES.filter(b=>watch.favorites.includes(b.id));
  let successes=0,failures=0,partial=0;
  for(const beach of beaches) {
    try {
      const conditions=await fetchConditions(beach);
      if(conditions.forecastError)partial++;
      const alerts=[...conditions.alerts,...(conditions.forecastAlerts??[])];
      if(conditions.forecastError&&(!supportsAlerts(beach)||conditions.alertsError)&&!alerts.length){failures++;continue;}
      successes++;
      for(const alert of alerts) {
        const key=`${beach.id}/${alert.id}/${alert.sent}`;
        if(seen.has(key))continue;
        // Recheck subscriptions after the request: unfavoriting/disabling takes effect immediately.
        const latest: Watch=JSON.parse(await AsyncStorage.getItem(WATCH_KEY)??'{"favorites":[],"enabled":false}');
        if(!latest.enabled||!latest.favorites.includes(beach.id))continue;
        inbox.unshift({key,beachId:beach.id,beachName:beach.name,alert,receivedAt:Date.now()});seen.add(key);
        await notify(`${beach.name}: ${alert.event}`,alert.headline).catch(()=>{});
      }
    } catch {failures++; /* Failed sources never imply an all-clear. */ }
  }
  if(!successes)throw new Error('Could not complete favorite-beach alert checks. Forecast status is unknown; try again when connected.');
  await AsyncStorage.multiSet([[SEEN_KEY,JSON.stringify([...seen].slice(-1000))],[INBOX_KEY,JSON.stringify(inbox.slice(0,50))]]);
  return `Checked ${successes}/${beaches.length} favorite beaches at ${new Date().toLocaleTimeString()}. Worldwide forecast alerts + official warnings where supported.${failures?` ${failures} beach check(s) unavailable.`:''}${partial?` ${partial} forecast check(s) incomplete.`:''}`;
}
