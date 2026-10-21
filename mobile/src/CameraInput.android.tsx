import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { requireNativeViewManager } from 'expo-modules-core';
import { useCameraPermissions } from 'expo-camera';
import type { ViewProps } from 'react-native';
import { CameraHandle, CameraProps, decodeBase64 } from './liveTypes';

type FrameView = {captureFrame(): Promise<{base64:string;width:number;height:number}>};
const NativeCamera = requireNativeViewManager<ViewProps & {ref?:React.Ref<FrameView>;facing:string;onReady:()=>void;onError:(e:{nativeEvent:{message:string}})=>void}>('AqvarinFrameCamera');

export default forwardRef<CameraHandle,CameraProps>(function CameraInput(props,ref) {
  const camera = useRef<FrameView>(null);
  const [permission,requestPermission] = useCameraPermissions();
  const callbacks=useRef(props);callbacks.current=props;
  useEffect(() => {
    let active=true;
    if(permission && !permission.granted) void requestPermission().then(p => {
      if(active && !p.granted) callbacks.current.onError('Camera permission is required. Allow camera access in your device settings, then retry.');
    }).catch(e => {if(active) callbacks.current.onError(String(e));});
    return () => {active=false;};
  },[permission?.status]);
  useImperativeHandle(ref,() => ({async capture() {
    const frame=await camera.current?.captureFrame();
    if(!frame) throw new Error('Camera is not ready.');
    return decodeBase64(frame.base64);
  }}),[]);
  if(!permission?.granted) return null;
  return <NativeCamera ref={camera} facing={props.facing} onReady={() => callbacks.current.onReady()}
    onError={e => callbacks.current.onError(e.nativeEvent.message)} style={{width:'100%',aspectRatio:16/10,borderRadius:14,overflow:'hidden'}} />;
});
