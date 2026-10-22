import { Beach, Position } from './beaches';
export type MapProps = { beaches: Beach[]; selected: string; favorites: string[]; alerts: string[]; origin?: Position; overview?:boolean; onSelect: (id: string) => void };
export function mapSignature(props: Omit<MapProps,'onSelect'>): string {
  return JSON.stringify({beaches:props.beaches.map(b=>({id:b.id,name:b.name,latitude:b.latitude,longitude:b.longitude,state:b.state})),selected:props.selected,favorites:props.favorites,alerts:props.alerts,origin:props.origin,overview:props.overview});
}
export function mapDocument(props: Omit<MapProps,'onSelect'>): string {
  const data=mapSignature(props).replace(/</g,'\\u003c');
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>html,body,#map{height:100%;margin:0;background:#123541;font:13px system-ui}.pin{display:grid;place-items:center;border:2px solid #fff;border-radius:50%;background:#1b7c85;color:#fff;box-shadow:0 2px 10px #001b2b80;font-weight:800}.selected{background:#032e44;border:3px solid #20e0cb}.alert{background:#b96530}.cluster{background:#123d50;border-color:#61d9cb}.leaflet-control-attribution{font-size:9px}.leaflet-tooltip{font-weight:600}#fallback{position:absolute;z-index:1000;top:12px;left:12px;background:#fff;padding:10px;border-radius:10px}</style></head><body><div id="map" role="application" aria-label="Interactive United States beach map"></div><div id="fallback">Loading beach map…</div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
const data=${data};
function send(id){const message=JSON.stringify({type:'beach',id});if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(message);else window.parent.postMessage(message,'*');}
if(window.L){
  document.getElementById('fallback').remove();
  const map=L.map('map',{scrollWheelZoom:false,worldCopyJump:true}).setView([38,-98],3);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'}).addTo(map);
  const points=data.beaches.map(b=>({...b,lon:b.state==='AK'&&b.longitude>0?b.longitude-360:b.longitude}));
  const layer=L.layerGroup().addTo(map),favorites=new Set(data.favorites),alerts=new Set(data.alerts);
  function draw(){
    layer.clearLayers();const groups=new Map();const bounds=map.getBounds().pad(.15);
    points.forEach(b=>{if(!bounds.contains([b.latitude,b.lon]))return;const p=map.project([b.latitude,b.lon],map.getZoom());const key=map.getZoom()>=16?b.id:Math.floor(p.x/48)+','+Math.floor(p.y/48);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(b);});
    groups.forEach(group=>{
      const b=group[0],cluster=group.length>1;
      const lat=cluster?group.reduce((s,p)=>s+p.latitude,0)/group.length:b.latitude;
      const lon=cluster?group.reduce((s,p)=>s+p.lon,0)/group.length:b.lon;
      const chosen=group.some(p=>p.id===data.selected),warning=group.some(p=>alerts.has(p.id));
      const size=cluster?38:28;
      const icon=L.divIcon({className:'',html:'<div class="pin '+(cluster?'cluster ':'')+(chosen?'selected ':'')+(warning?'alert':'')+'" style="width:'+size+'px;height:'+size+'px">'+(cluster?group.length:favorites.has(b.id)?'★':'•')+'</div>',iconSize:[size+4,size+4],iconAnchor:[size/2,size/2]});
      const title=cluster?group.length+' beaches · zoom to explore':b.name;
      const label=document.createElement('span');label.textContent=title;
      const marker=L.marker([lat,lon],{icon,title,alt:title,keyboard:true}).addTo(layer).bindTooltip(label);
      marker.on('click',()=>cluster?map.fitBounds(group.map(p=>[p.latitude,p.lon]),{padding:[35,35],maxZoom:Math.min(18,map.getZoom()+3)}):send(b.id));
      if(chosen&&!cluster)marker.openTooltip();
    });
  }
  if(data.origin){L.circleMarker([data.origin.latitude,data.origin.longitude],{radius:7,color:'#fff',fillColor:'#3287ff',fillOpacity:1}).addTo(map).bindTooltip('Search location');}
  if(data.overview)map.fitBounds([[24,-125],[50,-66]],{padding:[20,20]});
  if(points.length&&!data.overview)map.fitBounds(points.map(b=>[b.latitude,b.lon]),{padding:[35,35],maxZoom:13});
  map.on('moveend zoomend',draw);draw();setTimeout(()=>{map.invalidateSize();draw();},100);
}else document.getElementById('fallback').textContent='Map unavailable. Use the beach list below.';
</script></body></html>`;
}
