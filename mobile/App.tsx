import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as DocumentPicker from 'expo-document-picker';
import { useEvent } from 'expo';
import { useFonts } from 'expo-font';
import { useVideoPlayer, VideoView } from 'expo-video';
import { AegisCoastClient } from './src/api';
import { CLASSES, LABELS, classCounts, frameAtTime } from './src/results';
import type { AnalysisJob, DistressReport, TrackingFrame, RipCurrentReport } from './src/schema';
import Svg, { Rect as SvgRect, Text as SvgText } from 'react-native-svg';
import { CLASS_COLORS, Icon, IconName, OceanArt, AqvarinMark, ObservationFill } from './src/ui';
import LiveScreen from './src/LiveScreen';

type Recent = { id: string; name: string; server: string };
type Selected = { uri: string; name: string; mimeType?: string; file?: File };
const DEFAULT_SERVER = process.env.EXPO_PUBLIC_API_URL ?? (Platform.OS === 'web' && typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:8000` : 'http://10.0.0.2:8000');
const restoredServer = (value: string) => Platform.OS === 'web' && value === 'http://10.0.0.2:8000' ? DEFAULT_SERVER : value;
const message = (e: unknown) => e instanceof Error ? e.message : String(e);

function Button({ title, onPress, disabled = false, secondary = false, icon }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean; icon?: IconName }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={title} disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, secondary && styles.secondary, disabled && { opacity: .4 }, pressed && { opacity: .7 }]}>
    <Text style={[styles.buttonText, secondary && { color: '#c7e1eb' }]}>{title}</Text>
    {icon && <Icon name={icon} size={18} color={secondary ? '#c7e1eb' : '#05243b'} />}
  </Pressable>;
}

function Results({ job, frames, client, visible }: { job: AnalysisJob; frames: TrackingFrame[]; client: AegisCoastClient; visible: boolean }) {
  const uri = client.videoUrl(job)!;
  const player = useVideoPlayer(uri, p => { p.timeUpdateEventInterval = .1; });
  useEffect(() => { if (!visible) player.pause(); }, [visible, player]);
  const [currentTime, setCurrentTime] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(player.currentTime), 100);
    return () => clearInterval(timer);
  }, [player]);
  const statusEvent = useEvent(player, 'statusChange', { status: player.status });
  const status = statusEvent?.status ?? player.status;
  const videoError = statusEvent?.error;
  const [filter, setFilter] = useState('all');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [distress, setDistress] = useState<DistressReport | null>(null);
  const [distressError, setDistressError] = useState('');
  const [rip, setRip] = useState<RipCurrentReport | null>(null);
  const [ripError, setRipError] = useState('');
  useEffect(() => {
    let active = true;
    setRip(null); setRipError('');
    void client.getRipCurrent(job).then(report => { if (active) setRip(report); })
      .catch(e => { if (active) setRipError(message(e)); });
    return () => { active = false; };
  }, [client, job.job_id, job.rip_current_url]);
  const ripSample = rip?.status === 'complete' ? [...rip.samples].reverse().find(s => s.timestamp_s <= currentTime && currentTime-s.timestamp_s <= .6) : undefined;
  const [showCapabilities, setShowCapabilities] = useState(false);
  const reviewEnabled = distress?.status === 'complete' && (distress.classifier?.state === 'ready' ||
    (distress.motion_reference !== 'uncalibrated' && distress.water_confirmed));
  useEffect(() => {
    let active = true;
    void client.getDistress(job).then(report => { if (active) setDistress(report); })
      .catch(e => { if (active) setDistressError(message(e)); });
    return () => { active = false; };
  }, [client, job.distress_url]);
  const frame = frameAtTime(frames, currentTime + .0005);
  const counts = useMemo(() => classCounts(frames), [frames]);
  const totalObservations = counts.reduce((sum,c) => sum+c.observations,0);
  const objects = frame?.objects.filter(o => filter === 'all' || o.class === filter) ?? [];
  const jump = (delta: number) => {
    player.pause();
    const index = Math.max(0, Math.min(frames.length - 1, (frame?.frame ?? 0) + delta));
    player.currentTime = frames[index]?.timestamp_s ?? 0;
    setCurrentTime(frames[index]?.timestamp_s ?? 0);
  };
  return <>
    <View style={styles.card}>
      <View style={styles.line}><View style={styles.row}><Icon name="video" color="#18E0D1" /><Text style={styles.section}>Analysis results</Text></View><View style={styles.badge}><Text style={styles.badgeText}>COMPLETE</Text></View></View>
      <View style={{position:'relative'}}>
        <VideoView player={player} style={styles.video} contentFit="contain" nativeControls fullscreenOptions={{ enable: true }} />
        {!!rip?.width_px && !!rip.height_px && !!ripSample?.regions.length && <Svg pointerEvents="none" width="100%" height="100%" style={{position:'absolute',top:0,left:0}} viewBox={`0 0 ${rip.width_px} ${rip.height_px}`} preserveAspectRatio="xMidYMid meet">
          {ripSample.regions.map(r => <React.Fragment key={r.region_id}>
            <SvgRect x={r.bbox_xyxy_px[0]} y={r.bbox_xyxy_px[1]} width={r.bbox_xyxy_px[2]-r.bbox_xyxy_px[0]} height={r.bbox_xyxy_px[3]-r.bbox_xyxy_px[1]} fill="rgba(24,224,209,0.08)" stroke="#18E0D1" strokeWidth={Math.max(2,rip.width_px!/450)} strokeDasharray="12 8" />
            <SvgText x={r.bbox_xyxy_px[0]+5} y={Math.max(24,r.bbox_xyxy_px[1]-8)} fill="#18E0D1" fontSize={Math.max(18,rip.width_px!/55)}>Rip candidate #{r.region_id} · {r.score.toFixed(2)}</SvgText>
          </React.Fragment>)}
        </Svg>}
      </View>
      {status === 'error' && <Text style={styles.error}>Playback failed: {videoError?.message ?? 'Try opening the video below.'}</Text>}
      <View style={styles.frameStrip}><Pressable accessibilityRole="button" accessibilityLabel="Previous frame" onPress={() => jump(-1)} disabled={!frames.length} style={styles.iconButton}><Icon name="left" /></Pressable><View style={styles.frameInfo}><Text style={styles.text}>Frame {frame?.frame ?? '—'} <Text style={styles.muted}>/ {Math.max(0, frames.length - 1)}</Text></Text><Text style={styles.muted}>{(frame?.timestamp_s ?? 0).toFixed(2)} s · {frame?.objects.length ?? 0} detections</Text></View><Pressable accessibilityRole="button" accessibilityLabel="Next frame" onPress={() => jump(1)} disabled={!frames.length} style={styles.iconButton}><Icon name="right" /></Pressable></View>
    </View>
    <View style={styles.card}>
      <View style={styles.line}><Text style={styles.section}>Rip-current review</Text><Text style={styles.accent}>{rip?.status === 'complete' ? `${rip.events.length} warning${rip.events.length === 1 ? '' : 's'}` : '—'}</Text></View>
      {!!ripError && <Text style={styles.error}>{ripError}</Text>}
      {!rip && !ripError && <Text style={styles.muted}>{job.rip_current_url ? 'Loading rip-current results…' : 'Analyze this footage again to include rip-current review.'}</Text>}
      {rip?.status === 'failed' && <Text style={styles.error}>Rip-current analysis unavailable: {rip.error}</Text>}
      {rip?.status === 'complete' && <>
        <Text style={styles.accent}>RipScout sediment-rip model active</Text>
        <Text style={styles.muted}>{rip.observations} candidate observations · {rip.sampled_frames} independent sampled frames</Text>
        <Text style={styles.muted}>Detects visible sediment-plume patterns. Warnings require three consistent predictions over at least one second. Model scores are not rip-current probabilities.</Text>
        {!rip.events.length && <Text style={styles.text}>No persistent rip candidates flagged. Rip currents without visible sediment may be missed.</Text>}
        {rip.events.map(e => <Pressable key={`${e.region_id}/${e.timestamp_s}`} accessibilityRole="button" accessibilityLabel={`Review rip candidate ${e.region_id} at ${e.timestamp_s.toFixed(1)} seconds`} onPress={() => {player.pause();player.currentTime=e.timestamp_s;setCurrentTime(e.timestamp_s);}} style={styles.alertCard}>
          <View style={styles.line}><Text style={styles.objectTitle}>Possible rip current · Region #{e.region_id}</Text><Icon name="right" /></View>
          <Text style={styles.text}>{e.timestamp_s.toFixed(1)} s · Model score {e.model_score.toFixed(2)}</Text>
          <Text style={styles.muted}>{e.distinct_predictions} distinct predictions · Peak {e.peak_score.toFixed(2)} · Tap to review the marked region</Text>
        </Pressable>)}
      </>}
    </View>
    <View style={styles.card}>
      <View style={styles.line}><Text style={styles.section}>Distress review</Text><Text style={styles.accent}>{reviewEnabled ? `${distress?.events.length ?? 0} warning${distress?.events.length === 1 ? '' : 's'}` : distress ? 'Limited' : '—'}</Text></View>
      {!!distressError && <Text style={styles.error}>Distress results unavailable: {distressError}</Text>}
      {!distress && !distressError && <Text style={styles.muted}>{job.distress_url ? 'Loading distress results…' : 'This saved analysis predates distress review. Analyze the footage again to add it.'}</Text>}
      {distress?.status === 'failed' && <Text style={styles.error}>Distress analysis unavailable: {distress.error}</Text>}
      {distress?.classifier?.state !== 'ready' && distress?.classifier && <Text style={styles.warning}>Drowning classifier unavailable · {distress.classifier.state === 'missing_checkpoint' ? 'Trained swim/drown weights are required.' : distress.classifier.message}</Text>}
      {distress?.classifier?.state === 'ready' && <>
        <Text style={styles.accent}>{distress.classifier.backend === 'yolo' ? 'Trained drowning model active' : 'Temporal swim/drown model active'}</Text>
        <Text style={styles.muted}>{distress.classifier.backend === 'yolo' ? 'Swimming · Active drowning · Possible passive drowning' : 'Swimming · Drowning'} · Predictions require review.</Text>
        {distress.classifier.observed_actions && Object.entries(distress.classifier.observed_actions).map(([label,count]) => <View key={label} style={styles.line}><Text style={[styles.text,{flex:1}]}>{label === 'Possible Passive Drowner' ? 'Possible passive drowning' : label}</Text><Text style={styles.muted}>{count} frame observations</Text></View>)}
        <Text style={styles.muted}>Warnings combine distinct model predictions. Repeated video frames do not count as independent evidence.</Text>
      </>}
      {distress?.status === 'complete' && <>
        <Text style={styles.muted}>{distress.motion_reference === 'uncalibrated' || !distress.water_confirmed ? 'Movement alerts disabled: verified camera and water context required.' : 'Movement proxies enabled for the configured camera and water context.'}</Text>
        {!distress.events.length && <Text style={styles.text}>No review warnings generated. This does not establish swimmer safety.</Text>}
        {distress.events.map((event, i) => <Pressable key={`${event.track_id}/${event.timestamp_s}/${i}`} accessibilityRole="button" accessibilityLabel={`Review swimmer ${event.track_id} at ${event.timestamp_s.toFixed(1)} seconds`} onPress={() => { player.pause(); player.currentTime = event.timestamp_s; setCurrentTime(event.timestamp_s); }} style={styles.alertCard}>
          <View style={styles.line}><Text style={[styles.objectTitle, {flex:1}]}>Possible {event.signals.some(s => ['active_drowning','possible_passive_drowning','upstream_drown_action'].includes(s)) ? 'drowning' : 'distress'} · Swimmer #{event.track_id}</Text><Icon name="right" /></View>
          <Text style={styles.warning}>{event.timestamp_s.toFixed(1)} s · {event.signals.map(s => s.replace(/_/g, ' ')).join(', ')}</Text>
          <Text style={styles.muted}>Tap to review footage{event.action_score !== null ? ` · Model score ${event.action_score.toFixed(2)}` : ''}</Text>
          {!!event.metrics?.distinct_predictions && <Text style={styles.muted}>{event.metrics.distinct_predictions} distinct predictions · Peak score {event.metrics.peak_action_score?.toFixed(2)} · Scores are not drowning probabilities.</Text>}
        </Pressable>)}
        <Pressable accessibilityRole="button" accessibilityLabel="Indicator capabilities" accessibilityState={{expanded:showCapabilities}} onPress={() => setShowCapabilities(v => !v)} style={styles.line}><Text style={styles.text}>Indicator capabilities</Text><Icon name={showCapabilities ? 'down' : 'right'} /></Pressable>
        {showCapabilities && Object.entries(distress.indicator_capabilities ?? {}).map(([name, state]) => <View key={name} style={{gap:4}}><Text style={styles.text}>{name.replace(/_/g, ' ')}</Text><Text style={styles.muted}>{state}</Text></View>)}
      </>}
    </View>
    <View style={styles.card}>
      <Text style={styles.section}>Clip summary</Text>
      <View style={styles.row}>
        <View style={styles.stat}><Text style={styles.statValue}>{job.summary?.frames}</Text><Text style={styles.muted}>Frames</Text></View>
        <View style={styles.stat}><Text style={styles.statValue}>{job.summary?.unique_tracks}</Text><Text style={styles.muted}>Track IDs</Text></View>
        <View style={styles.stat}><Text style={styles.statValue}>{job.summary?.processing_fps.toFixed(1)}</Text><Text style={styles.muted}>Processing FPS</Text></View>
      </View>
      <Text style={styles.label}>Observations by class</Text>
      {counts.map(c => {
        const percent = 100*c.observations/Math.max(1,totalObservations);
        return <View key={c.name} style={styles.countRow}><View style={styles.line}><View style={styles.row}><View style={[styles.dot, { backgroundColor: CLASS_COLORS[c.name] }]} /><Text style={styles.text}>{LABELS[c.name]}</Text></View><View style={styles.countNumbers}><Text style={styles.countValue}>{c.observations.toLocaleString()}</Text><Text style={styles.countPercent}>{percent.toFixed(1)}%</Text></View></View><View accessibilityRole="progressbar" accessibilityLabel={`${LABELS[c.name]} share of observations`} accessibilityValue={{min:0,max:Math.max(1,totalObservations),now:c.observations,text:`${percent.toFixed(1)}% of observations`}} style={styles.bar}>{c.observations > 0 && <View style={[styles.barFill, {width:`${percent}%`}]}><ObservationFill name={c.name} /></View>}</View></View>;
      })}
      <Text style={styles.muted}>Bars show each class’s share of all observations.</Text>
      <Text style={styles.muted}>One observation is one box in one frame. Track IDs are not a verified count of people or boats.</Text>
      <View style={styles.row}><Button title="Open video" icon="video" secondary onPress={() => { void Linking.openURL(uri); }} /><Button title="Tracking data" icon="layers" secondary onPress={() => { if (job.tracks_url) void Linking.openURL(new URL(job.tracks_url, uri).toString()); }} /></View>
    </View>
    <View style={styles.card}>
      <Text style={styles.section}>Objects in this frame</Text>
      {(filter === 'all' || filter === 'swimmer') && frame?.unobserved_swimmers?.map(o => <View key={`lost-${o.track_id}`} style={styles.alertCard}><Text style={styles.objectTitle}>Visual contact lost · Swimmer #{o.track_id}</Text><Text style={styles.warning}>Last seen {o.missing_seconds.toFixed(1)} s ago</Text><Text style={styles.muted}>Dashed box marks the last observed position. No current detection or drowning score. Submersion is unconfirmed.</Text>{o.last_action && <Text style={styles.muted}>Last observed action: {o.last_action.label} · Score {o.last_action.score.toFixed(2)}</Text>}</View>)}
      <View style={styles.chips}>{['all', ...CLASSES].map(c => <Pressable key={c} accessibilityRole="button" accessibilityState={{ selected: filter === c }} onPress={() => setFilter(c)} style={[styles.chip, filter === c && styles.activeChip]}><Text style={styles.text}>{c === 'all' ? 'All' : LABELS[c]}</Text></Pressable>)}</View>
      {!objects.length && <View style={styles.empty}><Icon name="layers" size={28} /><Text style={styles.muted}>No {filter === 'all' ? 'objects' : LABELS[filter].toLowerCase()} detected in this frame.</Text></View>}
      {objects.map(o => <Pressable key={o.track_id} accessibilityRole="button" onPress={() => setExpanded(expanded === o.track_id ? null : o.track_id)} style={styles.object}>
        <View style={styles.line}><View style={styles.row}><View style={[styles.dot, {backgroundColor: CLASS_COLORS[o.class] ?? '#a1b0c4'}]} /><Text style={styles.objectTitle}>{LABELS[o.class] ?? o.class} <Text style={styles.muted}>#{o.track_id}</Text></Text></View><View style={styles.confidence}><Text style={styles.accent}>{(o.confidence * 100).toFixed(1)}%</Text><Icon name={expanded === o.track_id ? 'down' : 'right'} size={14} /></View></View>
        <Text style={styles.muted}>Center {o.center_px.map(v => v.toFixed(0)).join(', ')} px · {o.motion.speed_px_s.toFixed(1)} px/s</Text>
        {o.distress_action && <Text style={o.distress_action.requires_review ? styles.warning : styles.accent}>{o.distress_action.label === 'Possible Passive Drowner' ? 'Possible passive drowning' : o.distress_action.label} · Score {o.distress_action.score.toFixed(2)}{o.distress_action.requires_review ? ' · Review' : ''}</Text>}
        {expanded === o.track_id && <View style={styles.details}>
          <Text style={styles.text}>Box: {o.bbox_xyxy_px.map(v => v.toFixed(0)).join(', ')} px</Text>
          <Text style={styles.text}>Velocity: {o.motion.velocity_px_s.map(v => v.toFixed(1)).join(', ')} px/s</Text>
          <Text style={styles.text}>Rolling velocity: {o.motion.rolling_velocity_px_s.map(v => v.toFixed(1)).join(', ')} px/s</Text>
          <Text style={styles.text}>Heading: {o.motion.heading_deg === null ? '—' : `${o.motion.heading_deg.toFixed(1)}°`} · Displacement: {o.motion.displacement_px.toFixed(1)} px</Text>
          <Text style={styles.text}>Age: {o.track_age_frames} frames · Consecutive: {o.consecutive_observed_frames} · Missed before this: {o.missed_frames}</Text>
          <Text style={styles.text}>Trail: {o.trail.length} recorded points</Text>
        </View>}
      </Pressable>)}
      <Text style={styles.muted}>Motion is measured in image pixels, not physical speed. Model labels may be incorrect.</Text>
    </View>
  </>;
}

export default function App() {
  useEffect(() => {
    if (Platform.OS === 'web' && typeof document !== 'undefined') document.title = 'AQVARIN';
  }, []);
  const [fontsLoaded, fontError] = useFonts({
    MontserratSemiBold: require('./assets/fonts/Montserrat-SemiBold.ttf'),
    MontserratBold: require('./assets/fonts/Montserrat-Bold.ttf'),
    PoppinsRegular: require('./assets/fonts/Poppins-Regular.ttf'),
    PoppinsMedium: require('./assets/fonts/Poppins-Medium.ttf'),
    PoppinsSemiBold: require('./assets/fonts/Poppins-SemiBold.ttf'),
  });
  const [server, setServer] = useState(DEFAULT_SERVER);
  const [jobServer, setJobServer] = useState(DEFAULT_SERVER);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [frames, setFrames] = useState<TrackingFrame[]>([]);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState('');
  const [retry, setRetry] = useState(0);
  const [mode, setMode] = useState<'full' | 'sliced'>('full');
  const [preset, setPreset] = useState<'continuity' | 'original'>('continuity');
  const [sceneType, setSceneType] = useState<'auto' | 'swimmers_only'>('auto');
  const [showServer, setShowServer] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [screen, setScreen] = useState<'monitor' | 'live' | 'analyses' | 'settings'>('monitor');
  const scroll = useRef<ScrollView>(null);
  const navigate = (next: 'monitor' | 'live' | 'analyses' | 'settings') => {
    setScreen(next);
    setShowServer(next === 'settings');
    scroll.current?.scrollTo({ y: 0, animated: false });
  };
  const client = useMemo(() => new AegisCoastClient(jobServer), [jobServer]);
  const busy = uploading || job?.state === 'queued' || job?.state === 'processing';

  useEffect(() => {
    void AsyncStorage.multiGet(['server', 'recent']).then(entries => {
      if (entries[0][1]) setServer(restoredServer(entries[0][1]));
      if (entries[1][1]) setRecent((JSON.parse(entries[1][1]) as Recent[]).map(item => ({...item,server:restoredServer(item.server)})));
    }).catch(() => setError('Could not restore saved analyses.'));
  }, []);

  useEffect(() => {
    if (!job) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      try {
        const updated = await client.getJob(job.job_id);
        if (stopped) return;
        failures = 0;
        setError('');
        setJob(updated);
        if (updated.state === 'completed') {
          const results = await client.getFrames(updated);
          if (!stopped) { setFrames(results); setError(''); }
        } else if (updated.state === 'failed') setError(updated.error ?? 'Analysis failed.');
        else timer = setTimeout(poll, 2000);
      } catch (e) {
        if (!stopped) {
          failures++;
          setError(`Connection interrupted. Retrying automatically… ${message(e)}`);
          timer = setTimeout(poll,Math.min(10000,1000*2**Math.min(failures,4)));
        }
      }
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [job?.job_id, client, retry]);

  async function choose() {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: 'video/*', copyToCacheDirectory: true, multiple: false });
      if (!result.canceled) { setSelected(result.assets[0]); setJob(null); setFrames([]); setError(''); }
    } catch (e) { setError(message(e)); }
  }

  async function analyze() {
    if (!selected) return;
    setUploading(true); setError(''); setJob(null); setFrames([]);
    try {
      const url = new URL(server.trim());
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Use an HTTP or HTTPS server URL.');
      const base = url.toString().replace(/\/$/, '');
      const api = new AegisCoastClient(base);
      await api.health();
      const next = await api.uploadVideo(selected.uri, selected.name, selected.mimeType, { file: selected.file, detectionMode: mode, trackingPreset: preset, sceneType });
      setJobServer(base); setJob(next);
      const history = [{id: next.job_id, name: selected.name, server: base}, ...recent].slice(0, 10);
      setRecent(history);
      await AsyncStorage.multiSet([['server', base], ['recent', JSON.stringify(history)]]);
    } catch (e) { setError(message(e)); }
    finally { setUploading(false); }
  }

  function open(item: Recent) {
    navigate('monitor');
    setError(''); setFrames([]); setSelected(null); setJobServer(item.server);
    setJob({job_id: item.id, state: 'queued', summary: null, error: null}); setRetry(v => v + 1);
  }

  if (!fontsLoaded && !fontError) return <SafeAreaProvider><SafeAreaView style={[styles.safe, {justifyContent:'center',alignItems:'center'}]}><ActivityIndicator color="#18E0D1" accessibilityLabel="Loading AQVARIN" /></SafeAreaView></SafeAreaProvider>;
  return <SafeAreaProvider><SafeAreaView style={styles.safe}><ScrollView ref={scroll} contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
    <View style={styles.header}><View style={styles.row}><AqvarinMark /><View><Text style={styles.brand}>AQVARIN</Text><Text style={styles.brandSub}>WATER INTELLIGENCE</Text></View></View><Pressable accessibilityRole="button" accessibilityLabel="Server settings" accessibilityState={{expanded:showServer}} onPress={() => navigate(screen === 'settings' ? 'monitor' : 'settings')} style={styles.serverToggle}><Icon name="tune" size={19} color="#18E0D1" /></Pressable></View>
    {screen === 'live' && <LiveScreen server={server} />}
    {screen === 'monitor' && <>
      <View style={styles.hero}>
        <View style={StyleSheet.absoluteFill}><OceanArt /></View>
        <View style={styles.heroContent}><Text style={styles.heroEyebrow}>YOUR COAST. IN FOCUS.</Text><Text style={styles.heroTitle}>A clearer view.<Text style={{color:'#eef5fa'}}>{'\n'}A closer watch.</Text></Text><Text style={styles.heroSubtitle}>Ocean insights, from every frame.</Text></View>
      </View>
      <View style={styles.quickActions}>
        {([{title:'Upload footage',sub:'Start a review',icon:'upload',action:() => { void choose(); }},{title:'Saved analyses',sub:`${recent.length} in your library`,icon:'layers',action:() => navigate('analyses')},{title:'Settings',sub:'Your connection',icon:'tune',action:() => navigate('settings')}] as {title:string;sub:string;icon:IconName;action:() => void}[]).map((item,i) => <Pressable key={item.title} accessibilityRole="button" accessibilityLabel={item.title} disabled={i === 0 && !!busy} onPress={item.action} style={({pressed}) => [styles.quickTile, pressed && {opacity:.7}, i === 0 && busy && {opacity:.4}]}><Icon name={item.icon} size={23} color={['#18E0D1','#58a8db','#b7a4e0'][i]} /><Text style={styles.quickTitle}>{item.title}</Text><Text style={styles.quickSub}>{item.sub}</Text></Pressable>)}
      </View>
    </>}
    {(screen === 'analyses' || screen === 'settings') && <View style={styles.screenHeading}><Text style={styles.label}>{screen === 'analyses' ? 'YOUR LIBRARY' : 'WORKSPACE'}</Text><Text style={styles.title}>{screen === 'analyses' ? 'Saved analyses' : 'Settings'}</Text><Text style={styles.subtitle}>{screen === 'analyses' ? 'Revisit footage. Pick up where you left off.' : 'Manage your connection to the analysis server.'}</Text></View>}
    {showServer && <View style={styles.card}>
      <View style={styles.line}><Text style={styles.section}>Analysis server</Text><Text style={styles.muted}>{connection === 'Connected' ? 'Connected' : 'Not verified'}</Text></View>
      <TextInput accessibilityLabel="Server URL" value={server} onChangeText={v => { setServer(v); setConnection(''); }} editable={!busy} autoCapitalize="none" autoCorrect={false} keyboardType="url" style={styles.input} />
      <Button title="Check connection" secondary disabled={!!busy} onPress={() => { setConnection('Checking…'); void new AegisCoastClient(server.trim().replace(/\/$/, '')).health().then(() => setConnection('Connected')).catch(e => setConnection(`Unavailable: ${message(e)}`)); }} />
      {!!connection && <Text style={styles.muted}>{connection}</Text>}
    </View>}
    {screen === 'monitor' && <View style={styles.card}>
      <View style={styles.line}><Text style={styles.label}>NEW ANALYSIS</Text><Text style={styles.muted}>01 / Upload footage</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={selected ? 'Change video' : 'Choose video'} disabled={!!busy} onPress={() => { void choose(); }} style={({pressed}) => [styles.uploadZone, selected && styles.uploadSelected, pressed && {opacity:.7}]}>
        <View style={styles.uploadIcon}><Icon name={selected ? 'video' : 'upload'} size={28} color="#18E0D1" /></View>
        <Text numberOfLines={2} style={styles.uploadTitle}>{selected?.name ?? 'Choose your video'}</Text>
        <Text style={styles.muted}>{selected ? 'Video selected · Tap to change' : 'Select footage from your device'}</Text>
        <View style={styles.selectPill}><Text style={styles.selectPillText}>{selected ? 'Change video' : 'Select video'}</Text><Icon name="arrow" size={14} color="#bccdd8" /></View>
        {!selected && <Text style={styles.formatTag}>MP4  /  MOV  /  AVI  /  MKV</Text>}
      </Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel="Analysis options" accessibilityState={{expanded:showOptions}} onPress={() => setShowOptions(v => !v)} style={styles.optionsToggle}><View style={styles.row}><Icon name="tune" size={17} /><Text style={styles.text}>Analysis options</Text></View><View style={styles.row}><Text style={styles.muted}>{mode === 'full' ? 'Full frame' : 'Small objects'}</Text><Icon name={showOptions ? 'down' : 'right'} size={16} /></View></Pressable>
      {showOptions && <View style={styles.optionsBody}><Text style={styles.label}>DETECTION</Text>
      <View style={styles.row}>{(['full', 'sliced'] as const).map(v => <Button key={v} title={v === 'full' ? 'Full frame' : 'Small objects'} secondary={mode !== v} disabled={!!busy} onPress={() => setMode(v)} />)}</View>
      {mode === 'sliced' && <Text style={styles.muted}>Scans tiles for smaller objects. Takes longer to process.</Text>}
      <Text style={styles.label}>TRACKING</Text>
      <View style={styles.row}>{(['continuity', 'original'] as const).map(v => <Button key={v} title={v === 'continuity' ? 'Stable tracks' : 'Standard tracks'} secondary={preset !== v} disabled={!!busy} onPress={() => setPreset(v)} />)}</View>
      <Text style={styles.label}>SCENE</Text>
      <View style={styles.row}><Button title="Automatic" secondary={sceneType !== 'auto'} disabled={!!busy} onPress={() => setSceneType('auto')} /><Button title="Swimmers only" secondary={sceneType !== 'swimmers_only'} disabled={!!busy} onPress={() => setSceneType('swimmers_only')} /></View>
      {sceneType === 'swimmers_only' && <Text style={styles.muted}>Use for water footage containing people and no vessels. Vessel classes are excluded from this analysis.</Text>}
      </View>}
      <Button title={uploading ? 'Uploading…' : 'Run analysis'} icon="arrow" onPress={() => { void analyze(); }} disabled={!selected || !!busy} />
      {!!busy && <View style={styles.processing}><ActivityIndicator color="#18E0D1" /><View style={{flex:1, gap:4}}><Text style={styles.objectTitle}>{uploading ? 'Uploading your footage' : 'Analysis in progress'}</Text><Text style={styles.muted}>{uploading ? 'Sending video to your analysis server.' : 'Detecting objects, building tracks and preparing playback.'}</Text></View></View>}
      {job?.state === 'failed' && <Text style={styles.error}>Analysis failed. You can select another video or retry.</Text>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      {!!error && job && <Button title="Reconnect" secondary onPress={() => { setError(''); setRetry(v => v + 1); }} />}
    </View>}
    {job?.state === 'completed' && job.video_url && <View style={{gap:18, display:screen === 'monitor' ? 'flex' : 'none'}}><Results key={`${jobServer}/${job.job_id}`} job={job} frames={frames} client={client} visible={screen === 'monitor'} /></View>}
    {screen === 'analyses' && <View style={styles.card}><View style={styles.line}><Text style={styles.section}>Footage library</Text><View style={styles.badge}><Text style={styles.badgeText}>{recent.length} SAVED</Text></View></View>{!recent.length && <View style={styles.empty}><Icon name="layers" size={32} color="#469ab0" /><Text style={styles.section}>Your next insight starts here.</Text><Text style={styles.muted}>Analyzed videos will appear in this library.</Text><Button title="Analyze footage" icon="arrow" onPress={() => navigate('monitor')} /></View>}{recent.map(item => <Pressable key={item.id} accessibilityRole="button" accessibilityLabel={`Open ${item.name}`} disabled={!!busy} onPress={() => open(item)} style={({pressed}) => [styles.recentRow, busy && {opacity:.4}, pressed && {opacity:.7}]}><View style={styles.recentIcon}><Icon name="video" color="#58a8db" /></View><View style={{flex:1,gap:4}}><Text numberOfLines={2} style={styles.text}>{item.name}</Text><Text style={styles.muted}>Open saved analysis</Text></View><Icon name="right" size={16} /></Pressable>)}</View>}
    <View style={styles.footerBlock}><Text style={styles.label}>OCEAN · DATA · PEOPLE</Text><View style={styles.classLegend}>{CLASSES.map(c => <View key={c} style={styles.row}><View style={[styles.dot,{backgroundColor:CLASS_COLORS[c]}]} /><Text style={styles.footer}>{LABELS[c]}</Text></View>)}</View></View>
  </ScrollView><View style={styles.navWrap}><View style={styles.bottomNav}>{([{key:'monitor',label:'Monitor',icon:'monitor'},{key:'live',label:'Live',icon:'camera'},{key:'analyses',label:'Analyses',icon:'layers'},{key:'settings',label:'Settings',icon:'tune'}] as const).map(item => <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel={item.label} accessibilityState={{selected:screen === item.key}} onPress={() => navigate(item.key)} style={[styles.navItem, screen === item.key && styles.navActive]}><Icon name={item.icon} size={21} color={screen === item.key ? '#18E0D1' : '#89a5b7'} /><Text style={[styles.navLabel, screen === item.key && {color:'#18E0D1'}]}>{item.label}</Text></Pressable>)}</View></View></SafeAreaView></SafeAreaProvider>;
}

const BODY_FONT = 'PoppinsRegular';
const styles = StyleSheet.create({
  selectPill: { flexDirection:'row', alignItems:'center', gap:9, borderWidth:1, borderColor:'#50606d', paddingHorizontal:17, paddingVertical:10, borderRadius:24, marginTop:3, backgroundColor:'#1a252e' },
  selectPillText: { fontFamily:BODY_FONT, fontSize:12, color:'#e1eaf1' },
  hero: { borderRadius:24, minHeight:194, overflow:'hidden', borderWidth:1, borderColor:'#253441' },
  heroContent: { padding:24, gap:12 },
  heroEyebrow: { fontFamily: 'PoppinsSemiBold', color:'#9dc6d0', fontSize:10, letterSpacing:1 },
  heroTitle: { fontFamily: 'MontserratSemiBold', color:'#92a3b2', fontSize:29, lineHeight:38, letterSpacing:-1 },
  heroSubtitle: { fontFamily: BODY_FONT, color:'#b3cbd6', fontSize:13, lineHeight:20 },
  heroBadge: { alignSelf:'flex-start', flexDirection:'row', alignItems:'center', gap:7, paddingHorizontal:11, paddingVertical:7, borderRadius:20, backgroundColor:'#163f50', marginTop:6 },
  heroBadgeText: { fontFamily:'PoppinsSemiBold', color:'#c2e9e6', fontSize:10, letterSpacing:.5 },
  quickActions: { flexDirection:'row', gap:10 },
  quickTile: { flex:1, minHeight:102, backgroundColor:'#151b21', borderRadius:18, padding:14, gap:9, borderWidth:1, borderColor:'#28333d' },
  quickTitle: { fontFamily: 'PoppinsSemiBold', color:'#e0eff4', fontSize:12, },
  quickSub: { fontFamily: BODY_FONT, color:'#89a8bb', fontSize:11, lineHeight:16 },
  screenHeading: { gap:10, paddingVertical:8 },
  navWrap: { backgroundColor:'#0d1116', borderTopWidth:1, borderColor:'#232c35', paddingHorizontal:16, paddingVertical:9 },
  bottomNav: { width:'100%', maxWidth:680, alignSelf:'center', flexDirection:'row', gap:10 },
  navItem: { flex:1, minHeight:55, gap:5, alignItems:'center', justifyContent:'center', borderRadius:16 },
  navActive: { backgroundColor:'#0F4E5F' },
  navLabel: { fontFamily: 'PoppinsSemiBold', color:'#89a5b7', fontSize:10, },
  warning: { fontFamily: BODY_FONT, color: '#ffd28a', fontSize: 13, lineHeight: 20 },
  alertCard: { borderWidth: 1, borderColor: '#826137', backgroundColor: '#29251d', padding: 14, borderRadius: 12, gap: 10 },
  safe: { flex: 1, backgroundColor: '#0A1420' },
  page: { padding: 20, paddingTop: 22, paddingBottom: 28, gap: 18, width: '100%', maxWidth: 720, alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 8 },
  logo: { width: 44, height: 44, backgroundColor: '#0F4E5F', borderWidth: 1, borderColor: '#28616a', borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  brand: { color: '#D7F8FF', fontSize: 23, letterSpacing: 2.4, fontFamily: 'MontserratSemiBold' },
  brandSub: { fontFamily: BODY_FONT, color: '#8baebf', fontSize: 9, letterSpacing: 1.2, marginTop: 4 },
  serverToggle: { flexDirection: 'row', gap: 10, minHeight: 44, paddingHorizontal: 13, borderRadius: 12, borderWidth: 1, borderColor: '#2c343d', alignItems: 'center' },
  title: { fontFamily: 'MontserratBold', color: '#f0f5fa', fontSize: 32, letterSpacing: -.9, marginBottom: 7 },
  subtitle: { fontFamily: BODY_FONT, color: '#9cb8c9', fontSize: 14, lineHeight: 22 },
  card: { backgroundColor: '#101c27', borderRadius: 22, padding: 20, gap: 18, borderWidth: 1, borderColor: '#28323b' },
  section: { fontFamily: 'MontserratSemiBold', color: '#edf3fa', fontSize: 17, letterSpacing: -.3 },
  text: { fontFamily: BODY_FONT, color: '#d4e7ef', fontSize: 13, lineHeight: 20 },
  muted: { fontFamily: BODY_FONT, color: '#98b5c6', fontSize: 11, lineHeight: 18 },
  label: { fontFamily: 'PoppinsSemiBold', color: '#b1bec8', fontSize: 11, letterSpacing: .5 },
  input: { fontFamily: BODY_FONT, backgroundColor: '#10151b', color: '#f0f5fa', padding: 14, borderRadius: 10, borderWidth: 1, borderColor: '#2b536b', fontSize: 14 },
  button: { backgroundColor: '#18E0D1', minHeight: 48, paddingHorizontal: 17, paddingVertical: 13, borderRadius: 11, flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'center' },
  secondary: { backgroundColor: '#1c252d', borderWidth: 1, borderColor: '#35414b' },
  buttonText: { fontFamily: 'PoppinsSemiBold', color: '#05243b', fontSize: 13 },
  row: { flexDirection: 'row', gap: 9, flexWrap: 'wrap', alignItems: 'center' },
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  video: { width: '100%', aspectRatio: 16 / 10, backgroundColor: '#000', borderRadius: 12 },
  stat: { flex: 1, minWidth: 75, backgroundColor: '#10161c', borderRadius: 11, padding: 13, gap: 4 },
  statValue: { fontFamily: 'MontserratSemiBold', color: '#f0f5fa', fontSize: 23, letterSpacing: -.6 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  chip: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, backgroundColor: '#1a222a', borderRadius: 22, borderWidth: 1, borderColor: '#2b3742' },
  activeChip: { borderColor: '#18E0D1', backgroundColor: '#0F4E5F' },
  object: { borderWidth: 1, borderColor: '#2b3742', borderRadius: 12, padding: 14, gap: 10, backgroundColor: '#10171e' },
  objectTitle: { fontFamily: 'PoppinsSemiBold', color: '#e0eaf5', fontSize: 13, },
  confidence: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  accent: { fontFamily: 'PoppinsSemiBold', color: '#18E0D1',  fontSize: 12 },
  details: { gap: 8, borderTopWidth: 1, borderColor: '#2b3742', paddingTop: 12 },
  error: { fontFamily: BODY_FONT, color: '#ff9c98', fontSize: 13, lineHeight: 20 },
  footer: { fontFamily: BODY_FONT, color: '#8eadc1', fontSize: 11 },
  footerBlock: { alignItems: 'center', gap: 15, paddingVertical: 8 },
  classLegend: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 13 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  uploadZone: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, paddingVertical: 29, gap: 11, backgroundColor: '#172027', borderRadius: 22, borderWidth: 1, borderColor: '#5b707e', boxShadow: 'inset 0 0 24px rgba(191, 218, 236, 0.16), 0 8px 24px rgba(0, 0, 0, 0.35)' },
  uploadSelected: { borderColor: '#6fbbb9', backgroundColor: '#122735' },
  uploadIcon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: '#121a22', borderWidth:1, borderColor:'#536572', boxShadow:'0 0 15px rgba(174, 218, 243, 0.18)', marginBottom: 5 },
  uploadTitle: { fontFamily: 'MontserratSemiBold', fontSize: 17, color: '#e9f2fb', textAlign: 'center', lineHeight: 23 },
  formatTag: { fontFamily: BODY_FONT, color: '#68819d', fontSize: 10, letterSpacing: .5, marginTop: 6 },
  optionsToggle: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, minHeight: 44 },
  optionsBody: { gap: 14, paddingBottom: 6 },
  processing: { flexDirection: 'row', gap: 14, backgroundColor: '#172832', borderRadius: 12, padding: 14, alignItems: 'center' },
  frameStrip: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#10161c', borderRadius: 12, padding: 6 },
  frameInfo: { alignItems: 'center', gap: 2 },
  iconButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: '#202b35', borderRadius: 9 },
  badge: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: 6, backgroundColor: '#0F4E5F' },
  badgeText: { fontFamily: 'PoppinsSemiBold', color: '#18E0D1', fontSize: 8,  letterSpacing: 1 },
  countRow: { gap: 9 },
  countValue: { fontFamily:'PoppinsSemiBold', color: '#e4edf8', fontSize: 13 },
  countNumbers: { flexDirection:'row',alignItems:'baseline',gap:12 },
  countPercent: { fontFamily:'PoppinsMedium',fontSize:11,color:'#94a5b2',minWidth:43,textAlign:'right' },
  bar: { height: 12, borderRadius: 8, backgroundColor: '#2a323a', borderWidth:1,borderColor:'#56616c',overflow:'hidden',boxShadow:'inset 0 2px 4px rgba(0, 0, 0, 0.35)' },
  barFill: { height:'100%',borderRadius:7,overflow:'hidden',boxShadow:'0 0 8px rgba(187, 218, 240, 0.25)' },
  empty: { alignItems: 'center', gap: 12, padding: 24 },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderTopWidth: 1, borderColor: '#28323d' },
  recentIcon: { width: 40, height: 44, borderRadius: 10, backgroundColor: '#1b2a36', alignItems: 'center', justifyContent: 'center' },
});
