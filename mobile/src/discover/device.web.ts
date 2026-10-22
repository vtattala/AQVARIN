import { Position } from './beaches';
export async function locate(): Promise<Position> {
  if(!navigator.geolocation)throw new Error('Location is unavailable. Search for a beach instead.');
  return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(p=>resolve(p.coords),()=>reject(new Error('Location unavailable or declined. Search for a beach instead.')),{timeout:12000,maximumAge:300000}));
}
export async function enableNotifications(): Promise<boolean> {
  if(!('Notification' in window))return false;
  return await Notification.requestPermission()==='granted';
}
export async function notify(title: string,body: string): Promise<void> {
  if('Notification' in window&&Notification.permission==='granted')new Notification(title,{body});
}
