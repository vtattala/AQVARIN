import {piCameraUrl} from './piCamera';
export const PI_PROFILE_KEY='aqvarin.pi-camera.v1';
export type PiProfile={version:1;address:string;token:string};
/** A saved camera is restored only as settings; opening Live never starts capture. */
export function parsePiProfile(raw:string|null):PiProfile|null {
  if(!raw)return null;
  try{
    const p=JSON.parse(raw);
    if(p?.version!==1||typeof p.address!=='string'||typeof p.token!=='string'||!p.token.trim()||p.token.length>1024)return null;
    return {version:1,address:piCameraUrl(p.address),token:p.token.trim()};
  }catch{return null;}
}
