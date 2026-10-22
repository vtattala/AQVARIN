import React, { useEffect, useMemo, useRef } from 'react';
import { mapDocument, mapSignature, MapProps } from './mapDocument';
export default function BeachMap(props: MapProps) {
  const frame=useRef<HTMLIFrameElement>(null);
  const signature=mapSignature(props);
  const html=useMemo(()=>mapDocument(props),[signature]);
  useEffect(()=>{const receive=(event: MessageEvent)=>{
    if(event.source!==frame.current?.contentWindow || typeof event.data!=='string')return;
    try{const m=JSON.parse(event.data);if(m.type==='beach'&&props.beaches.some(b=>b.id===m.id))props.onSelect(m.id);}catch{}
  };window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);},[props.beaches,props.onSelect]);
  return <iframe key={signature} ref={frame} title="United States beach explorer" srcDoc={html} sandbox="allow-scripts allow-same-origin allow-popups" style={{width:'100%',height:350,border:0,borderRadius:20,background:'#123541'}} />;
}
