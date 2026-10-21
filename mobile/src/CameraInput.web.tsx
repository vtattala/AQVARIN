import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { CameraHandle, CameraProps } from './liveTypes';

export default forwardRef<CameraHandle, CameraProps>(function CameraInput(props, ref) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const callbacks = useRef(props); callbacks.current = props;
  useImperativeHandle(ref, () => ({
    async capture() {
      const source = video.current;
      if (!source || source.readyState < 2 || !source.videoWidth) throw new Error('Camera is not producing frames.');
      const target = canvas.current ?? (canvas.current = document.createElement('canvas'));
      const scale = Math.min(1, 1280/Math.max(source.videoWidth,source.videoHeight));
      target.width = Math.round(source.videoWidth*scale);
      target.height = Math.round(source.videoHeight*scale);
      const context = target.getContext('2d');
      if (!context) throw new Error('Camera frame capture is unavailable in this browser.');
      context.drawImage(source,0,0,target.width,target.height);
      const blob = await new Promise<Blob>((resolve,reject) => target.toBlob(b => b ? resolve(b) : reject(new Error('Could not capture camera frame.')),'image/jpeg',.85));
      return new Uint8Array(await blob.arrayBuffer());
    },
  }), []);
  useEffect(() => {
    let stopped = false;
    let stream: MediaStream | undefined;
    async function open() {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        callbacks.current.onError('Camera access needs localhost or HTTPS. Open this app on localhost on this computer, or use the native mobile app.');
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({audio:false,video:{
          ...(props.deviceId ? {deviceId:{exact:props.deviceId}} : {facingMode:{ideal:props.facing === 'back' ? 'environment' : 'user'}}),
          width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30},
        }});
        if (stopped) {stream.getTracks().forEach(t => t.stop());return;}
        const source = video.current!;
        source.srcObject = stream;
        await source.play();
        if (stopped) return;
        stream.getVideoTracks()[0].addEventListener('ended', () => {
          if (!stopped) callbacks.current.onError('Camera disconnected. Reconnect it and start again.');
        });
        const devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput');
        if (stopped) return;
        callbacks.current.onDevices(devices.map((d,i) => ({id:d.deviceId,label:d.label || `Camera ${i+1}`})));
        if (source.readyState >= 2) callbacks.current.onReady();
        else source.addEventListener('loadeddata', () => { if (!stopped) callbacks.current.onReady(); },{once:true});
      } catch (error) {
        if (stopped) return;
        const e = error as DOMException;
        callbacks.current.onError(e.name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access for this app in the browser, then start again.'
          : e.name === 'NotFoundError' ? 'No camera found. Connect a webcam or camera capture device, then start again.'
          : e.name === 'NotReadableError' ? 'The camera is in use or unavailable. Close other camera apps and retry.' : `Camera could not open: ${e.message}`);
      }
    }
    void open();
    return () => {stopped=true;stream?.getTracks().forEach(t => t.stop());if(video.current) video.current.srcObject=null;};
  }, [props.deviceId,props.facing]);
  return <video ref={video} aria-label="Live camera preview" muted autoPlay playsInline style={{width:'100%',maxHeight:400,aspectRatio:'16 / 10',objectFit:'contain',background:'#050a10',borderRadius:14}} />;
});
