import React from 'react';
import Svg, { Path, Circle, Defs, LinearGradient, Stop, Rect, Image as SvgImage } from 'react-native-svg';

export const PALETTE = { ocean: '#0A1420', teal: '#0F4E5F', sea: '#18E0D1', aqua: '#D7F8FF', ink: '#0A1420' };

export function ObservationFill({ name }: { name: string }) {
  const id = `observation-${name}`;
  return <Svg width="100%" height="100%" viewBox="0 0 100 12" preserveAspectRatio="none">
    <Defs><LinearGradient id={id} x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor="#ffffff" /><Stop offset=".45" stopColor="#e0eff8" /><Stop offset="1" stopColor="#92bfd9" /></LinearGradient></Defs>
    <Rect width="100" height="12" fill={`url(#${id})`} />
  </Svg>;
}

/** Display the supplied emblem directly from the bundled brand board. */
export function AqvarinMark({ size = 52 }: { size?: number }) {
  return <Svg width={size} height={size} viewBox="395 75 450 480" accessibilityLabel="AQVARIN water intelligence logo">
    <SvgImage href={require('../assets/branding/aqvarin-brand.png')} x={0} y={0} width={1254} height={1254} />
  </Svg>;
}

export function OceanArt() {
  return <Svg width="100%" height="100%" viewBox="0 0 600 300" preserveAspectRatio="xMidYMid slice">
    <Defs><LinearGradient id="ocean-bg" x1="0" y1="0" x2="1" y2="1"><Stop offset="0" stopColor="#0A1420" /><Stop offset="1" stopColor="#080e16" /></LinearGradient><LinearGradient id="ocean-swell" x1="0" y1="1" x2="1" y2="0"><Stop offset="0" stopColor="#0F4E5F" /><Stop offset="1" stopColor="#18E0D1" /></LinearGradient></Defs>
    <Rect width="600" height="300" fill="url(#ocean-bg)" />
    <Path d="M0 235C140 290 180 130 305 176S480 275 600 100V300H0Z" fill="url(#ocean-swell)" opacity=".22" />
    <Path d="M0 261C130 310 197 179 320 212S510 270 600 170V300H0Z" fill="#0d7390" opacity=".16" />
    <Path d="M280 205C375 167 447 298 600 108M310 224C408 203 473 290 600 158M325 246C443 228 480 280 600 201" stroke="#9be1dc" strokeWidth="1" fill="none" opacity=".12" />
    <Circle cx="490" cy="54" r="65" fill="#78d5d4" opacity=".035" /><Circle cx="490" cy="54" r="40" stroke="#91d9d8" strokeWidth="1" opacity=".14" fill="none" />
  </Svg>;
}

export const CLASS_COLORS: Record<string, string> = {
  swimmer: '#18E0D1', boat: '#58a8db', buoy: '#edc47f', jetski: '#b7a4e0', life_saving_appliances: '#eea49c',
};

const paths = {
  compass: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m4 6-2 6-6 2 2-6 6-2',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  bell: 'M18 8a6 6 0 0 0-12 0v6l-2 3h16l-2-3V8m-9 12h6',
  camera: 'M3 7h4l2-3h6l2 3h4v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5',
  video: 'M4 4h16v16H4zM4 8h16M8 4v4m8-4v4m-6 4 5 3-5 3z',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  left: 'm14 6-6 6 6 6',
  right: 'm10 6 6 6-6 6',
  down: 'm6 9 6 6 6-6',
  tune: 'M4 7h16M4 17h16M8 4v6m8 4v6',
  layers: 'm12 3 9 5-9 5-9-5 9-5m-9 10 9 5 9-5m-18 5 9 5 9-5',
  clock: 'M12 6v6l4 2',
  check: 'm5 12 4 4L19 6',
  monitor: 'M3 4h18v13H3zM8 21h8m-4-4v4',
};
export type IconName = keyof typeof paths;
export function Icon({ name, size = 20, color = '#a1b0c4' }: { name: IconName; size?: number; color?: string }) {
  return <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    {name === 'clock' && <Circle cx="12" cy="12" r="9" />}
    <Path d={paths[name]} />
  </Svg>;
}
