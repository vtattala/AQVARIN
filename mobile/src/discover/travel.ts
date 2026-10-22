import { Beach, distanceKm } from './beaches';
export type BeachPhoto={url:string;page:string;title:string;credit:string;license:string;licenseUrl:string};
export type TravelPlace={name:string;description:string;distance:number;url:string;kind:'eat'|'see'|'do'};
export type TravelBrief={beachId:string;fetchedAt:number;photo?:BeachPhoto;description?:string;article?:{title:string;url:string;language:string};food:TravelPlace[];nearby:TravelPlace[];guides:{title:string;url:string}[];errors:string[]};
export function plainText(value:unknown):string {
  return String(value??'').replace(/<[^>]*>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;|&apos;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&#(x[0-9a-f]+|\d+);/gi,(_,n)=>{const code=n[0].toLowerCase()==='x'?parseInt(n.slice(1),16):Number(n);return code>0&&code<=0x10ffff?String.fromCodePoint(code):'';}).replace(/\s+/g,' ').trim();
}
export function excerpt(text:string,limit=520):string {if(text.length<=limit)return text;const cut=text.slice(0,limit);let sentence=Math.max(cut.lastIndexOf('. '),cut.lastIndexOf('! '),cut.lastIndexOf('? '));while(sentence>0&&/\b(?:no|mr|mrs|dr|st|vs|etc)\.$/i.test(cut.slice(0,sentence+1))){const before=cut.slice(0,sentence);sentence=Math.max(before.lastIndexOf('. '),before.lastIndexOf('! '),before.lastIndexOf('? '));}if(sentence>Math.min(limit*.55,70))return cut.slice(0,sentence+1);return cut.slice(0,Math.max(cut.lastIndexOf(' '),Math.floor(limit*.7))).replace(/[ ,;:]$/,'')+'…';}
const normalized=(s:string)=>s.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
/** Name and coordinate agreement is required; a nearby aquarium/hotel is not the beach. */
export function matchingArticle(beach:Beach,pages:any[]):any|undefined {
  const names=[beach.name,...(beach.aliases??[])].map(normalized).filter(Boolean);
  return pages.filter(p=>Array.isArray(p.coordinates)&&p.coordinates.some((c:any)=>Number.isFinite(c.lat)&&Number.isFinite(c.lon)&&distanceKm(beach,{latitude:c.lat,longitude:c.lon})<=5)).map(p=>{
    const title=normalized(p.title??'').replace(/ beach$/,'');
    const score=Math.max(...names.map(n=>{n=n.replace(/ beach$/,'');if(n===title)return 1;const words=n.split(' '),other=title.split(' ');return words.filter(w=>other.includes(w)).length/Math.max(words.length,other.length);}));return {page:p,score};
  }).filter(p=>p.score>=.8).sort((a,b)=>b.score-a.score)[0]?.page;
}
async function query(host:string,params:Record<string,string>,signal?:AbortSignal) {
  const controller=new AbortController(),abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();const timer=setTimeout(abort,12000);
  try {const response=await fetch(`https://${host}/w/api.php?${new URLSearchParams({action:'query',format:'json',formatversion:'2',origin:'*',...params})}`,{signal:controller.signal});if(!response.ok)throw Error('Source unavailable');const result=await response.json();if(result.error)throw Error('Source unavailable');return result.query?.pages??[];}
  finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export function licensedPhoto(page:any):BeachPhoto|undefined {
  const info=page?.imageinfo?.[0],m=info?.extmetadata;const license=plainText(m?.LicenseShortName?.value),licenseUrl=String(m?.LicenseUrl?.value??'');
  if(!info||!['image/jpeg','image/png','image/webp'].includes(info.mime)||!/^(CC BY(?:-SA)? [234](?:\.0)?|CC0|Public domain)/i.test(license)||/map|diagram|logo|flag|chart|coat of arms/i.test(page.title??''))return;
  const url=String(info.thumburl??info.url??'');if(!/^https:\/\/(?:upload|thumb)\.wikimedia\.org\//.test(url)||!/^https:\/\/commons\.wikimedia\.org\//.test(info.descriptionurl??''))return;
  if(!/^https?:\/\/creativecommons\.org\//.test(licenseUrl)&&!/^Public domain/i.test(license))return;
  const credit=plainText(m.Attribution?.value||m.Artist?.value);if(/^CC BY/i.test(license)&&!credit)return;
  return {url,page:info.descriptionurl,title:plainText(page.title).replace(/^File:/,''),credit:credit||'Wikimedia Commons contributors',license,licenseUrl:licenseUrl||'https://commons.wikimedia.org/wiki/Help:Public_domain'};
}
const imageParams={prop:'imageinfo',iiprop:'url|extmetadata|mime',iiurlwidth:'960',iiextmetadatafilter:'Artist|Attribution|LicenseShortName|LicenseUrl|ImageDescription'};
const languages:Record<string,string>={JP:'ja',CN:'zh',TW:'zh',KR:'ko',BR:'pt',PT:'pt',FR:'fr',RE:'fr',ES:'es',MX:'es',AR:'es',CL:'es',PE:'es',CO:'es',IT:'it',GR:'el',DE:'de',AT:'de',NL:'nl',ID:'id',TH:'th',VN:'vi',TR:'tr',RU:'ru',SE:'sv',NO:'no',FI:'fi',DK:'da',PL:'pl',HR:'hr',IL:'he',UA:'uk'};
async function encyclopedia(beach:Beach,signal?:AbortSignal) {
  let article:any,language='en';const params={generator:'geosearch',ggscoord:`${beach.latitude}|${beach.longitude}`,ggsradius:'5000',ggslimit:'30',prop:'extracts|pageimages|coordinates|info',exintro:'1',explaintext:'1',exchars:'900',exlimit:'max',colimit:'max',piprop:'name',inprop:'url'};
  for(const lang of [...new Set(['en',languages[beach.country??'']].filter(Boolean))]){
    const pages=await query(`${lang}.wikipedia.org`,params,signal);article=matchingArticle(beach,pages);if(article){language=lang;break;}
  }
  let photo:BeachPhoto|undefined;let photoError='';
  try {
  if(article?.pageimage){photo=licensedPhoto((await query('commons.wikimedia.org',{...imageParams,titles:`File:${article.pageimage}`},signal))[0]);}
  if(!photo){
    // A named, geotagged photo only; never substitute a generic stock shoreline.
    const safeName=beach.name.replace(/["\\]/g,' ');
    const pages=await query('commons.wikimedia.org',{...imageParams,generator:'search',gsrsearch:`"${safeName}" nearcoord:1km,${beach.latitude},${beach.longitude} filetype:bitmap`,gsrnamespace:'6',gsrlimit:'5'},signal);
    photo=pages.map(licensedPhoto).find(Boolean);
  }
  }catch{if(signal?.aborted)throw Error('Aborted');photoError='Photo source is temporarily unavailable.';}
  return {photo,photoError,description:article?.extract?excerpt(plainText(article.extract)):undefined,article:article?{title:String(article.title),url:`https://${language}.wikipedia.org/wiki/${encodeURIComponent(String(article.title).replace(/ /g,'_'))}`,language}:undefined};
}
function wikiText(value:string):string {
  return plainText(value.replace(/\[\[(?:[^\]|]+\|)?([^\]]+)\]\]/g,'$1').replace(/\[https?:\/\/\S+\s+([^\]]+)\]/g,'$1').replace(/\{\{[^{}]*\}\}/g,'').replace(/'{2,}/g,''));
}
/** Parse balanced listing templates; nested templates and link pipes stay within their field. */
export function guideListings(content:string,beach:Beach,url:string):TravelPlace[] {
  const found:TravelPlace[]=[];const pattern=/\{\{(eat|see|do)\s*(?=\|)/gi;let match:RegExpExecArray|null;
  while((match=pattern.exec(content))){
    const kind=match[1].toLowerCase() as TravelPlace['kind'];let depth=1,links=0,start=pattern.lastIndex,parts:string[]=[],closed=false;
    for(let i=start;i<content.length-1;i++){
      const pair=content.slice(i,i+2);
      if(pair==='{{'){depth++;i++;continue;}if(pair==='}}'){depth--;if(!depth){parts.push(content.slice(start,i));pattern.lastIndex=i+2;closed=true;break;}i++;continue;}
      if(pair==='[['){links++;i++;continue;}if(pair===']]'){links=Math.max(0,links-1);i++;continue;}
      if(content[i]==='|'&&depth===1&&!links){parts.push(content.slice(start,i));start=i+1;}
    }
    if(!closed)break;const fields:Record<string,string>={};for(const part of parts){const at=part.indexOf('=');if(at>0)fields[part.slice(0,at).trim().toLowerCase()]=part.slice(at+1).trim();}
    const lat=Number(fields.lat),lon=Number(fields.long);if(!fields.name||!fields.lat||!fields.long||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180)continue;
    const distance=distanceKm(beach,{latitude:lat,longitude:lon});if(distance>3)continue;
    // Only the first short description; opening hours and prices are not represented as live facts.
    const description=excerpt(wikiText(fields.content??''),kind==='eat'?220:180);
    found.push({name:wikiText(fields.name),description,distance,url,kind});
  }
  return found;
}
async function travelGuide(beach:Beach,signal?:AbortSignal){
  const pages=await query('en.wikivoyage.org',{generator:'geosearch',ggscoord:`${beach.latitude}|${beach.longitude}`,ggsradius:'10000',ggslimit:'8',prop:'revisions',rvprop:'content',rvslots:'main'},signal);
  const guides=pages.map((p:any)=>({title:String(p.title),url:`https://en.wikivoyage.org/wiki/${encodeURIComponent(String(p.title).replace(/ /g,'_'))}`}));
  const listings:TravelPlace[]=pages.flatMap((p:any,i:number)=>guideListings(p.revisions?.[0]?.slots?.main?.content??'',beach,guides[i].url));
  const unique=[...new Map(listings.sort((a,b)=>a.distance-b.distance).map(p=>[normalized(p.name),p])).values()];
  return {food:unique.filter(p=>p.kind==='eat').slice(0,3),nearby:unique.filter(p=>p.kind!=='eat'&&normalized(p.name)!==normalized(beach.name)).slice(0,3),guides:guides.slice(0,2)};
}
export async function fetchTravelBrief(beach:Beach,signal?:AbortSignal):Promise<TravelBrief>{
  const [wiki,guide]=await Promise.allSettled([encyclopedia(beach,signal),travelGuide(beach,signal)]);
  return {beachId:beach.id,fetchedAt:Date.now(),...(wiki.status==='fulfilled'?wiki.value:{}),...(guide.status==='fulfilled'?guide.value:{food:[],nearby:[],guides:[]}),errors:[...(wiki.status==='fulfilled'&&wiki.value.photoError?[wiki.value.photoError]:[]),...(wiki.status==='rejected'?['Photo / beach overview source is unavailable.']:[]),...(guide.status==='rejected'?['Nearby travel guide is unavailable.']:[])]};
}
