import React,{forwardRef,useEffect,useImperativeHandle,useRef,useState} from 'react';
import {ActivityIndicator,Image,Text,View} from 'react-native';
import type {CameraHandle} from './liveTypes';
import {frameBase64,piFrame,piRequest} from './piCamera';
type Props={address:string;token:string;onReady:()=>void;onError:(message:string)=>void};
export default forwardRef<CameraHandle,Props>(function PiCameraInput(props,ref){
  const [image,setImage]=useState('');const callbacks=useRef(props);callbacks.current=props;
  const capture=useRef<()=>Promise<Uint8Array>>(async()=>{throw Error('Pi camera is not ready.');});
  useImperativeHandle(ref,()=>({capture:()=>capture.current()}),[]);
  useEffect(()=>{
    let active=true,sequence=-1,ready=false,timer:ReturnType<typeof setTimeout>|undefined;
    let pending:Promise<Uint8Array>|undefined;const controller=new AbortController();
    const take=():Promise<Uint8Array>=>{
      if(pending)return pending;
      const task=(async()=>{const frame=await piFrame(props.address,props.token,sequence,controller.signal);if(!active)throw Error('Pi camera stopped.');sequence=frame.sequence;setImage(`data:image/jpeg;base64,${frameBase64(frame.bytes)}`);return frame.bytes;})();
      pending=task;void task.finally(()=>{if(pending===task)pending=undefined;}).catch(()=>{});return task;
    };
    capture.current=async()=>{if(pending)await pending;if(!active)throw Error('Pi camera stopped.');return take();};
    const preview=async()=>{try{await take();if(!active)return;if(!ready){ready=true;callbacks.current.onReady();}timer=setTimeout(()=>void preview(),300);}catch(e){if(active)callbacks.current.onError(e instanceof Error?e.message:'Pi camera unavailable.');}};
    void piRequest(props.address,props.token,'/api/camera/health',controller.signal).then(()=>{if(active)void preview();}).catch(e=>{if(active)callbacks.current.onError(e instanceof Error?e.message:'Pi camera unavailable.');});
    return()=>{active=false;controller.abort();clearTimeout(timer);};
  },[props.address,props.token]);
  return <View style={{aspectRatio:16/10,backgroundColor:'#050a10',borderRadius:14,overflow:'hidden',justifyContent:'center'}}>{image?<Image accessibilityLabel="Live Raspberry Pi camera preview" source={{uri:image}} resizeMode="contain" style={{width:'100%',height:'100%'}}/>:<View style={{alignItems:'center',gap:10}}><ActivityIndicator color="#18E0D1"/><Text style={{color:'#98b5c6'}}>Connecting to Raspberry Pi camera…</Text></View>}</View>;
});
