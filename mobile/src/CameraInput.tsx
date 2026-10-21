import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { ImageManipulator, ImageRef, SaveFormat } from 'expo-image-manipulator';
import { deleteAsync } from 'expo-file-system/legacy';
import { CameraHandle, CameraProps, decodeBase64 } from './liveTypes';

export default forwardRef<CameraHandle, CameraProps>(function CameraInput(props, ref) {
  const camera = useRef<CameraView>(null);
  const [pictureSize,setPictureSize] = useState<string>();
  const configured = useRef(false);
  const [permission, requestPermission] = useCameraPermissions();
  const callbacks = useRef(props); callbacks.current = props;
  useEffect(() => {
    let active = true;
    if (permission && !permission.granted) {
      void requestPermission().then(p => {if(active && !p.granted) callbacks.current.onError('Camera permission is required. Allow camera access in your device settings, then retry.');})
        .catch(e => {if(active) callbacks.current.onError(String(e));});
    }
    return () => {active=false;};
  }, [permission?.status]);
  useImperativeHandle(ref, () => ({
    async capture() {
      // Keep the native, orientation-correct bitmap until the final resize.
      // Avoid writing, compressing, and decoding a full-resolution JPEG first.
      const picture = await camera.current?.takePictureAsync({pictureRef:true,skipProcessing:false,shutterSound:false});
      if (!picture) throw new Error('Camera is not ready.');
      const context = ImageManipulator.manipulate(picture);
      let bitmap: ImageRef | undefined;
      let resized: string | undefined;
      try {
        if(Math.max(picture.width,picture.height)>1280) context.resize(picture.width >= picture.height ? {width:1280} : {height:1280});
        bitmap = await context.renderAsync();
        const image = await bitmap.saveAsync({compress:.9,format:SaveFormat.JPEG,base64:true});
        resized = image.uri;
        if (!image.base64) throw new Error('Could not encode camera frame.');
        return decodeBase64(image.base64);
      } finally {
        bitmap?.release();context.release();picture.release();
        if (resized) await deleteAsync(resized,{idempotent:true}).catch(() => {});
      }
    },
  }), []);
  async function ready() {
    if(!configured.current) {
      configured.current=true;
      try {
        const sizes=await camera.current!.getAvailablePictureSizesAsync();
        const ranked=sizes.map(value => ({value,dimensions:value.split('x').map(Number)}))
          .filter(s => s.dimensions.length===2 && s.dimensions.every(Number.isFinite) && Math.max(...s.dimensions)>=1280)
          .sort((a,b) => Math.abs(Math.max(...a.dimensions)-1920)-Math.abs(Math.max(...b.dimensions)-1920));
        if(ranked[0]) {setPictureSize(ranked[0].value);return;}
      } catch { /* The default capture size remains supported on this camera. */ }
    }
    callbacks.current.onReady();
  }
  if (!permission?.granted) return null;
  return <CameraView ref={camera} facing={props.facing} pictureSize={pictureSize} mirror={false} mode="picture" animateShutter={false} onCameraReady={() => {void ready();}}
    onMountError={e => props.onError(e.message)} style={{width:'100%',aspectRatio:16/10,borderRadius:14,overflow:'hidden'}} />;
});
