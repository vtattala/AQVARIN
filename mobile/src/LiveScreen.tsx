import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Image, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import CameraInput from './CameraInput';
import PiCameraInput from './PiCameraInput';
import {piCameraUrl,piRequest} from './piCamera';
import { CameraHandle, LiveResult } from './liveTypes';
import { CLASS_COLORS } from './ui';
import { LABELS } from './results';

export default function LiveScreen({server}:{server:string}) {
  const camera = useRef<CameraHandle>(null);
  const generation = useRef(0);
  const session = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const running = useRef(false);
  const [active,setActive] = useState(false);
  const [state,setState] = useState('Ready when you are');
  const [error,setError] = useState('');
  const [scene,setScene] = useState<'auto'|'swimmers_only'>('auto');
  const [analysisEnabled,setAnalysisEnabled]=useState(true);
  const [source,setSource]=useState<'device'|'pi'>('device');
  const [piAddress,setPiAddress]=useState('http://aqvarin-pi.local:8001'),[piToken,setPiToken]=useState(''),[piStatus,setPiStatus]=useState(''),[testingPi,setTestingPi]=useState(false);
  const [facing,setFacing] = useState<'front'|'back'>('back');
  const [devices,setDevices] = useState<{id:string;label:string}[]>([]);
  const [deviceId,setDeviceId] = useState<string>();
  const [result,setResult] = useState<LiveResult | null>(null);
  const [elapsed,setElapsed] = useState(0);
  const [latency,setLatency] = useState(0);
  const [captureTime,setCaptureTime] = useState(0);
  const [rate,setRate] = useState(0);
  const receivedAt = useRef(0);
  const base = server.trim().replace(/\/$/,'');

  function stop(note='Camera stopped') {
    generation.current++;
    running.current=false;
    controller.current?.abort();
    controller.current=null;
    const id=session.current;session.current=null;
    if(id) void fetch(`${base}/api/live/sessions/${id}`,{method:'DELETE',signal:AbortSignal.timeout(8000)}).catch(() => {});
    setActive(false);setState(note);
  }
  const stopRef=useRef(stop);stopRef.current=stop;
  useEffect(() => {
    if(!active || !['Opening camera…','Connecting to Pi camera…'].includes(state)) return;
    const timeout=setTimeout(() => {setError(source==='pi'?'Pi camera connection timed out. Check the Pi address, token and camera service.':'Camera access is still pending. Allow the camera prompt, then start again. If this embedded browser does not show a prompt, open http://localhost:8081/ in Chrome or Edge.');stopRef.current('Camera permission timed out');},30000);
    return () => clearTimeout(timeout);
  },[active,state,source]);
  useEffect(() => {
    const sub=AppState.addEventListener('change',s => {if(s!=='active') stopRef.current('Paused because the app left the foreground');});
    const hidden=() => {if(document.hidden) stopRef.current('Paused because this page is hidden');};
    if(Platform.OS==='web') document.addEventListener('visibilitychange',hidden);
    return () => {sub.remove();if(Platform.OS==='web') document.removeEventListener('visibilitychange',hidden);stopRef.current();};
  }, []);
  useEffect(() => {const t=setInterval(() => setElapsed(receivedAt.current ? (performance.now()-receivedAt.current)/1000 : 0),500);return () => clearInterval(t);},[]);

  async function request(path:string,options:RequestInit,timeout=30000) {
    const c=new AbortController();controller.current=c;
    const timer=setTimeout(() => c.abort(),timeout);
    try {
      const response=await fetch(`${base}${path}`,{...options,signal:c.signal,cache:'no-store'});
      if(!response.ok) {
        const body=await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Analysis server returned ${response.status}`);
      }
      return await response.json();
    } finally {clearTimeout(timer);if(controller.current===c) controller.current=null;}
  }
  async function run() {
    if(running.current) return;
    running.current=true;
    const token=generation.current;
    try {
      setState('Loading live models…');
      const created=await request('/api/live/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_type:scene})},90000);
      if(token!==generation.current) {void fetch(`${base}/api/live/sessions/${created.session_id}`,{method:'DELETE'}).catch(() => {});return;}
      session.current=created.session_id;
      const started=performance.now();let sequence=0;
      setState('Live analysis');
      while(token===generation.current) {
        const before=performance.now();
        const bytes=await camera.current!.capture();
        const captureMs=performance.now()-before;
        if(token!==generation.current) return;
        const captured=(before-started)/1000;
        const reply:LiveResult=await request(`/api/live/sessions/${created.session_id}/frame`,{method:'POST',headers:{'Content-Type':'image/jpeg','X-Frame-Sequence':String(sequence),'X-Captured-At':String(captured)},body:bytes as unknown as BodyInit});
        if(token!==generation.current) return;
        const now=performance.now();
        setLatency((now-before)/1000);setRate(1000/(now-before));setCaptureTime(captureMs/1000);
        receivedAt.current=now;setElapsed(0);setResult(reply);sequence++;
        // No queued frames: capture the camera's current image on the next iteration.
        await new Promise(resolve => setTimeout(resolve,Math.max(0,100-(now-before))));
      }
    } catch(e) {
      if(token!==generation.current) return;
      const detail=e instanceof Error ? e.message : String(e);
      setError(detail.includes('fetch') ? 'Connection to the analysis server was lost. Check Settings and start again.' : detail.includes('abort') ? 'The analysis server took too long to respond. Start again when it is available.' : detail);
      stop('Live analysis stopped');
    }
  }
  function begin(analyze=true) {
    if(analyze){try{const url=new URL(base);if(!['http:','https:'].includes(url.protocol))throw Error();}catch{setError('Set a valid HTTP or HTTPS analysis server URL in Settings.');return;}}
    if(source==='pi'){try{piCameraUrl(piAddress);if(!piToken.trim())throw Error('Enter the Pi camera token.');}catch(e){setError(e instanceof Error?e.message:'Invalid Pi camera settings.');return;}}
    generation.current++;setAnalysisEnabled(analyze);setResult(null);receivedAt.current=0;setError('');setState(source==='pi'?'Connecting to Pi camera…':'Opening camera…');setActive(true);
  }
  const fresh=active && !!result && elapsed<3;
  return <>
    <View style={{gap:9}}><Text style={s.eyebrow}>LIVE CAMERA</Text><Text style={s.title}>A watch in real time.</Text><Text style={s.text}>Swimmers, vessels, drowning indicators, and visual rip-current candidates from your camera.</Text></View>
    <View style={s.card}>
      <View style={s.row}><Text style={s.heading}>Camera feed</Text><Text style={s.accent}>{active ? state==='Live analysis' ? '● LIVE' : state==='Pi camera preview'?'PREVIEW':'CONNECTING' : 'OFF'}</Text></View>
      {active ? source==='pi'?<PiCameraInput ref={camera} address={piAddress} token={piToken} onReady={()=>{if(analysisEnabled)void run();else setState('Pi camera preview');}} onError={e=>{setError(e);setPiStatus('');stop('Pi camera unavailable');}}/>:<CameraInput ref={camera} deviceId={deviceId} facing={facing} onReady={()=>void run()} onDevices={setDevices} onError={e=>{setError(e);stop('Camera unavailable');}}/>:<View style={s.placeholder}><Text style={s.heading}>{source==='pi'?'Connect your Pi camera.':'Your camera, connected.'}</Text><Text style={[s.text,{textAlign:'center'}]}>{source==='pi'?'Connect Camera Module 3 through the Pi camera service.':'Start to enable the camera and continuous analysis.'}</Text></View>}
      {!active && <>
        <Text style={s.label}>CAMERA SOURCE</Text>
        <View style={s.wrap}>{(['device','pi'] as const).map(value=><Pressable key={value} accessibilityRole="button" accessibilityState={{selected:source===value}} onPress={()=>{setSource(value);setError('');}} style={[s.pill,source===value&&s.selected]}><Text style={s.small}>{value==='pi'?'Raspberry Pi camera':'This device'}</Text></Pressable>)}</View>
        {source==='pi'?<View style={{gap:10}}><Text style={s.label}>PI CAMERA ADDRESS</Text><TextInput accessibilityLabel="Pi camera address" value={piAddress} editable={!testingPi} onChangeText={v=>{setPiAddress(v);setPiStatus('');}} autoCapitalize="none" autoCorrect={false} keyboardType="url" style={[s.text,{borderWidth:1,borderColor:'#2a3b48',borderRadius:12,padding:12}]}/><Text style={s.label}>CAMERA TOKEN</Text><TextInput accessibilityLabel="Pi camera token" value={piToken} editable={!testingPi} onChangeText={v=>{setPiToken(v);setPiStatus('');}} placeholder="Token printed in the Pi terminal" placeholderTextColor="#98b5c6" autoCapitalize="none" autoCorrect={false} secureTextEntry style={[s.text,{borderWidth:1,borderColor:'#2a3b48',borderRadius:12,padding:12}]}/><Pressable accessibilityRole="button" disabled={testingPi} onPress={()=>{setTestingPi(true);setPiStatus('');void piRequest(piAddress,piToken,'/api/camera/health').then(r=>r.json()).then(h=>setPiStatus(`Pi camera ready · ${h.width} × ${h.height} · ${h.capture_fps} capture FPS`)).catch(e=>setPiStatus(e instanceof Error?e.message:'Pi connection failed.')).finally(()=>setTestingPi(false));}} style={s.pill}><Text style={s.small}>{testingPi?'Checking Pi…':'Test Pi connection'}</Text></Pressable>{!!piStatus&&<Text style={s.small}>{piStatus}</Text>}<Text style={s.small}>Pi → AQVARIN app → analysis server. The Pi provides video; detection runs at {base}, configured in Settings. Keep both devices on the same network. The token stays in this screen and is not saved.</Text></View>:<><Text style={s.label}>CAMERA</Text><View style={s.wrap}>{Platform.OS==='web' && devices.length ? devices.map(d=><Pressable key={d.id} accessibilityRole="button" onPress={()=>setDeviceId(d.id)} style={[s.pill,deviceId===d.id&&s.selected]}><Text style={s.small}>{d.label}</Text></Pressable>):(['back','front'] as const).map(f=><Pressable accessibilityRole="button" key={f} onPress={()=>setFacing(f)} style={[s.pill,facing===f&&s.selected]}><Text style={s.small}>{f==='back'?Platform.OS==='web'?'Default camera':'Rear camera':'Front camera'}</Text></Pressable>)}</View></>}
        <Text style={s.label}>SCENE</Text>
        <View style={s.wrap}>{(['auto','swimmers_only'] as const).map(value => <Pressable accessibilityRole="button" key={value} onPress={() => setScene(value)} style={[s.pill,scene===value && s.selected]}><Text style={s.small}>{value==='auto'?'All objects':'Swimmers only'}</Text></Pressable>)}</View>
      </>}
      <Pressable accessibilityRole="button" accessibilityLabel={active?'Stop live camera':'Start live camera'} onPress={() => {if(active)stop();else begin();}} style={[s.button,active && {backgroundColor:'#263f4a'}]}><Text style={[s.buttonText,active && {color:'#D7F8FF'}]}>{active?'Stop live camera':'Start live camera'}</Text></Pressable>
      {!active&&source==='pi'&&<Pressable accessibilityRole="button" onPress={()=>begin(false)} style={s.pill}><Text style={s.small}>Preview Pi camera without analysis</Text></Pressable>}
      <Text style={s.small}>{state}</Text>
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      {active && !['Live analysis','Pi camera preview'].includes(state) && <ActivityIndicator color="#18E0D1" />}
      <Text style={s.small}>{analysisEnabled?'Camera frames are sent to your analysis server while this page is active. No audio is captured and live frames are not saved.':'Preview only: frames are displayed in this app. Detection is off. No audio is captured.'}</Text>
    </View>
    {!!result && <>
      <View style={s.card}>
        <View style={s.row}><Text style={s.heading}>Analyzed frame</Text><Text style={fresh?s.accent:s.warning}>{fresh?'UPDATING':active?'DELAYED':'STOPPED'}</Text></View>
        <Image accessibilityLabel="Latest analyzed camera frame with detection boxes" source={{uri:`data:image/jpeg;base64,${result.image_base64}`}} style={{width:'100%',aspectRatio:result.width_px/result.height_px,borderRadius:12}} resizeMode="contain" />
        <View style={s.wrap}><Text style={s.small}>Frame {result.sequence+1}</Text><Text style={s.small}>{rate.toFixed(1)} analyzed FPS</Text><Text style={s.small}>{latency.toFixed(2)}s capture-to-result</Text><Text style={s.small}>{captureTime.toFixed(2)}s camera · {(result.processing_ms/1000).toFixed(2)}s models</Text><Text style={s.small}>Updated {elapsed.toFixed(1)}s ago</Text></View>
        {(latency>.75 || result.performance?.coverage_limited) && <Text style={s.warning}>Limited sampling: brief actions may be missed. Keep the swimmer clearly visible and check the connection.</Text>}
        {Object.entries(result.models).map(([name,model]) => <View style={s.row} key={name}><Text style={s.text}>{name.replace(/_/g,' ')}</Text><Text style={model.state==='ready'?s.accent:s.error}>{model.state==='ready'?`Active${model.device?.startsWith('cuda')?' · GPU':''}`:`Unavailable: ${model.message}`}</Text></View>)}
      </View>
      <View style={s.card}><Text style={s.heading}>Objects · {result.tracking.objects.length}</Text>
        {result.tracking.objects.map(o => <View key={o.track_id} style={s.object}><View style={s.row}><Text style={[s.text,{color:CLASS_COLORS[o.class]??'#D7F8FF'}]}>{LABELS[o.class]??o.class} #{o.track_id}</Text><Text style={s.small}>{(o.confidence*100).toFixed(1)}%</Text></View>{o.distress_action && <Text style={o.distress_action.requires_review?s.warning:s.small}>{o.distress_action.label} · Score {o.distress_action.score.toFixed(2)}</Text>}</View>)}
        {!result.tracking.objects.length && <Text style={s.text}>No objects detected in this frame.</Text>}
        {result.tracking.unobserved_swimmers?.map(o => <Text key={o.track_id} style={s.warning}>Visual contact lost · Swimmer #{o.track_id} · {o.missing_seconds.toFixed(1)}s since last seen</Text>)}
      </View>
      <View style={s.card}><Text style={s.heading}>Review warnings</Text>
        {result.distress_events.map((e,i) => <View key={`d/${e.track_id}/${i}`} style={s.alert}><Text style={s.warning}>Possible drowning · Swimmer #{e.track_id}</Text><Text style={s.small}>{e.timestamp_s.toFixed(1)}s into session · Score {e.action_score?.toFixed(2)??'—'}</Text></View>)}
        {result.rip_events.map((e,i) => <View key={`r/${e.region_id}/${i}`} style={s.alert}><Text style={s.warning}>Possible rip current · Region #{e.region_id}</Text><Text style={s.small}>{e.timestamp_s.toFixed(1)}s into session · Score {e.model_score.toFixed(2)}</Text></View>)}
        {!result.distress_events.length && !result.rip_events.length && <Text style={s.text}>No persistent warnings in this session yet.</Text>}
        {!!result.distress_candidates?.length && <Text style={s.heading}>Indicators needing review</Text>}
        {result.distress_candidates?.map(c => <View key={`${c.track_id}/${c.label}`} style={s.object}>
          <Text style={s.warning}>{c.label} · Swimmer #{c.track_id}</Text>
          <Text style={s.small}>Unconfirmed · {c.distinct_predictions} model {c.distinct_predictions===1?'observation':'observations'} · Last score {c.action_score.toFixed(2)}</Text>
          <Text style={s.small}>Last seen {c.last_seen_s.toFixed(1)}s into session. Evidence has not met the persistent warning criteria.</Text>
        </View>)}
        {!!result.rip_candidates?.length && <Text style={s.heading}>Rip indicators needing review</Text>}
        {result.rip_candidates?.map(c => <View key={`rc/${c.region_id}`} style={s.object}>
          <Text style={s.warning}>Rip candidate · Region #{c.region_id}</Text>
          <Text style={s.small}>Unconfirmed · {c.distinct_predictions} model {c.distinct_predictions===1?'observation':'observations'} · Score {c.model_score.toFixed(2)}</Text>
          <Text style={s.small}>Evidence spans {c.evidence_span_s.toFixed(1)}s. A warning needs 3 matching observations spanning 1s.</Text>
        </View>)}
        <Text style={s.small}>Live warnings combine distinct predictions within six seconds; gaps over 2.5 seconds reset evidence. Warnings require review. Scores are not probabilities of drowning or rip currents. Rip detection covers visible sediment-plume patterns. No warnings does not establish safety.</Text>
      </View>
    </>}
  </>;
}

const s=StyleSheet.create({
  title:{fontFamily:'MontserratSemiBold',fontSize:29,color:'#D7F8FF',letterSpacing:-1},eyebrow:{fontFamily:'PoppinsSemiBold',fontSize:10,color:'#18E0D1',letterSpacing:1.2},
  card:{backgroundColor:'#101c27',borderRadius:22,padding:20,gap:16,borderWidth:1,borderColor:'#28323b'},heading:{fontFamily:'MontserratSemiBold',fontSize:17,color:'#D7F8FF'},
  text:{fontFamily:'PoppinsRegular',fontSize:13,lineHeight:21,color:'#c6dbe5'},small:{fontFamily:'PoppinsRegular',fontSize:11,lineHeight:18,color:'#98b5c6'},label:{fontFamily:'PoppinsSemiBold',fontSize:10,color:'#98b5c6',letterSpacing:1},
  row:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10,flexWrap:'wrap'},wrap:{flexDirection:'row',gap:10,flexWrap:'wrap'},pill:{padding:11,borderRadius:14,borderWidth:1,borderColor:'#2a3b48'},selected:{borderColor:'#18E0D1',backgroundColor:'#0F4E5F'},
  placeholder:{aspectRatio:16/10,backgroundColor:'#080f18',borderRadius:14,justifyContent:'center',alignItems:'center',padding:20,gap:12},button:{minHeight:48,borderRadius:13,backgroundColor:'#18E0D1',alignItems:'center',justifyContent:'center',padding:12},buttonText:{fontFamily:'PoppinsSemiBold',fontSize:13,color:'#05243b'},
  accent:{fontFamily:'PoppinsSemiBold',fontSize:11,color:'#18E0D1'},error:{fontFamily:'PoppinsRegular',fontSize:13,lineHeight:20,color:'#ff9c98'},warning:{fontFamily:'PoppinsRegular',fontSize:12,lineHeight:20,color:'#ffd28a'},object:{borderTopWidth:1,borderColor:'#28323b',paddingTop:12,gap:6},alert:{backgroundColor:'#29251d',borderRadius:12,padding:14,gap:7},
});
