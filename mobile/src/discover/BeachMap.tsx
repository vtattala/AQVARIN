import React, { useMemo } from 'react';
import { WebView } from 'react-native-webview';
import { mapDocument, mapSignature, MapProps } from './mapDocument';
export default function BeachMap(props: MapProps) {
  const signature=mapSignature(props);
  const html=useMemo(()=>mapDocument(props),[signature]);
  return <WebView source={{html,baseUrl:'https://aqvarin.local'}} originWhitelist={['https://*']} applicationNameForUserAgent="AQVARIN/0.2 (+https://github.com/vtattala/AQVARIN)" javaScriptEnabled
    onMessage={event=>{try{const m=JSON.parse(event.nativeEvent.data);if(m.type==='beach'&&props.beaches.some(b=>b.id===m.id))props.onSelect(m.id);}catch{}}}
    onShouldStartLoadWithRequest={request=>request.url==='about:blank'||request.url==='https://aqvarin.local/'}
    style={{height:350,width:'100%',borderRadius:20,backgroundColor:'#123541'}} scrollEnabled={false} />;
}
