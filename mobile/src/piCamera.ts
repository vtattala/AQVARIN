/** Authenticated, bounded JPEG transport for the Raspberry Pi camera service. */
export function piCameraUrl(value:string):string {
  let url:URL;try{url=new URL(value.trim());}catch{throw Error('Enter the Pi camera address, for example http://aqvarin-pi.local:8001.');}
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname))throw Error('Use only the Pi camera HTTP or HTTPS address and port. Enter the camera token separately.');
  return url.origin;
}
export function frameBase64(bytes:Uint8Array):string {
  let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(text);
}
export async function piRequest(address:string,token:string,path:string,signal?:AbortSignal):Promise<Response>{
  const base=piCameraUrl(address);if(!token.trim())throw Error('Enter the camera token printed in the Pi terminal.');
  if(typeof location!=='undefined'&&location.protocol==='https:'&&base.startsWith('http:'))throw Error('This HTTPS page cannot read an HTTP Pi camera. Use the native app, localhost web preview, or HTTPS for the camera service.');
  const c=new AbortController(),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,8000);
  try{
    let response:Response;
    try{response=await fetch(`${base}${path}`,{headers:{Authorization:`Bearer ${token.trim()}`},signal:c.signal,cache:'no-store'});}catch{throw Error('Cannot reach the Pi camera. Check its address, Wi-Fi, camera service and browser local-network permission.');}
    if(!response.ok){const body=await response.json().catch(()=>null);throw Error(response.status===401?'Pi camera token was rejected. Copy the token printed by the Pi camera service.':body?.detail??`Pi camera returned ${response.status}.`);}
    const body=await response.arrayBuffer();if(body.byteLength>2000000)throw Error('Pi camera response is too large.');
    return new Response(body,{status:response.status,headers:response.headers});
  }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export async function piFrame(address:string,token:string,after:number,signal?:AbortSignal){
  const response=await piRequest(address,token,`/api/camera/frame?after=${after}`,signal);
  const sequence=Number(response.headers.get('X-Camera-Sequence')),age=Number(response.headers.get('X-Frame-Age-Ms'));
  if(response.headers.get('X-Camera-Sequence')===null||response.headers.get('X-Frame-Age-Ms')===null||!Number.isSafeInteger(sequence)||sequence<=after||!Number.isFinite(age)||age<0||age>2000)throw Error('Pi camera returned an old frame. Restart the camera service.');
  if(!(response.headers.get('Content-Type')??'').startsWith('image/jpeg')||Number(response.headers.get('Content-Length'))>2000000)throw Error('Pi camera returned an invalid image.');
  const bytes=new Uint8Array(await response.arrayBuffer());
  if(bytes.length<4||bytes.length>2000000||bytes[0]!==255||bytes[1]!==216||bytes[bytes.length-2]!==255||bytes[bytes.length-1]!==217)throw Error('Pi camera returned an invalid JPEG frame.');
  return {bytes,sequence,age};
}
