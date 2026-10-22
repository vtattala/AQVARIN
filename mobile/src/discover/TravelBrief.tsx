import React,{useEffect,useState} from 'react';
import {ActivityIndicator,Image,Linking,Pressable,StyleSheet,Text,View} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type {Beach} from './beaches';
import {fetchTravelBrief,TravelBrief as Brief,TravelPlace} from './travel';
const CACHE='aqvarin.discover.travel.v1';
let saves=Promise.resolve();
function Link({label,url}:{label:string;url:string}) {return <Pressable accessibilityRole="link" onPress={()=>void Linking.openURL(url)}><Text style={s.link}>{label} ↗</Text></Pressable>;}
function Place({place}:{place:TravelPlace}){return <View style={s.place}><View style={s.row}><Text style={s.placeName}>{place.name}</Text><Text style={s.small}>{place.distance.toFixed(1)} km</Text></View>{!!place.description&&<Text style={s.body}>{place.description}</Text>}<Link label="Travel guide listing" url={place.url}/></View>;}
export default function TravelBrief({beach}:{beach:Beach}) {
  const [brief,setBrief]=useState<Brief>(),[loading,setLoading]=useState(true),[failedImage,setFailedImage]=useState(false),[retry,setRetry]=useState(0),[storageError,setStorageError]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();let mounted=true;setBrief(undefined);setLoading(true);setFailedImage(false);setStorageError(false);
    const timer=setTimeout(()=>void(async()=>{
      let cached:Brief|undefined;
      try{const all=JSON.parse(await AsyncStorage.getItem(CACHE)??'{}');cached=all[beach.id];if(mounted&&cached?.beachId===beach.id)setBrief(cached);if(!retry&&cached&&Date.now()-cached.fetchedAt<(cached.errors.length?5*60000:24*3600000))return;}
      catch{if(mounted)setStorageError(true);}
      const result=await fetchTravelBrief(beach,controller.signal);if(!mounted||controller.signal.aborted)return;
      // Keep sourced content during a partial outage and label the original retrieval time.
      const next=result.errors.length&&cached?{...cached,errors:result.errors}:result;
      setBrief(next);saves=saves.catch(()=>{}).then(async()=>{const all=JSON.parse(await AsyncStorage.getItem(CACHE)??'{}');all[beach.id]=next;const bounded=Object.fromEntries(Object.entries(all).sort((a,b)=>(b[1] as Brief).fetchedAt-(a[1] as Brief).fetchedAt).slice(0,40));await AsyncStorage.setItem(CACHE,JSON.stringify(bounded));});
      void saves.catch(()=>{if(mounted)setStorageError(true);});
    })().catch(()=>{if(mounted)setBrief({beachId:beach.id,fetchedAt:Date.now(),food:[],nearby:[],guides:[],errors:['Travel information is temporarily unavailable.']});}).finally(()=>{if(mounted)setLoading(false);}),300);
    return()=>{mounted=false;clearTimeout(timer);controller.abort();};
  },[beach.id,retry]);
  const current=brief?.beachId===beach.id?brief:undefined;
  const photo=current?.photo;
  const maps=`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`restaurants near ${beach.name} ${beach.area} ${beach.latitude},${beach.longitude}`)}`;
  return <View style={s.wrap}>
    {photo&&!failedImage?<View style={s.photoWrap}><Image key={photo.url} source={{uri:photo.url}} accessibilityLabel={`Photograph of ${beach.name}`} resizeMode="cover" style={s.photo} onError={()=>setFailedImage(true)}/><View style={s.credit}><Text style={s.small}>{photo.credit} · Displayed cropped to fit.</Text><View style={s.row}><Link label="Photo & original" url={photo.page}/><Link label={photo.license} url={photo.licenseUrl}/></View></View></View>:<View style={s.placeholder}>{loading?<ActivityIndicator color="#42e0cc"/>:<Text style={s.placeholderIcon}>≈</Text>}<Text style={s.section}>{loading?'Finding a photo of this beach…':'Beach photo unavailable'}</Text><Text style={s.small}>{loading?'Matching the beach name and location.':'No matching, licensed photo could be loaded for this location.'}</Text>{!loading&&<Link label="Find photos online" url={`https://commons.wikimedia.org/w/index.php?search=${encodeURIComponent(beach.name+' '+beach.area)}&title=Special:MediaSearch&type=image`}/>}</View>}
    <Text style={s.eyebrow}>A LITTLE LOCAL KNOWLEDGE</Text>
    <Text style={s.body}>{current?.description||beach.description}</Text>
    {current?.article&&<View style={s.row}><Link label={`${current.article.title} · ${current.article.language} Wikipedia`} url={current.article.url}/><Link label="Text · CC BY-SA 4.0 · excerpt" url="https://creativecommons.org/licenses/by-sa/4.0/"/></View>}
    {loading&&<View style={s.row}><ActivityIndicator color="#42e0cc" size="small"/><Text style={s.small}>Finding local places and travel notes…</Text></View>}
    {!!current?.food.length&&<View style={s.group}><Text style={s.section}>A bite by the beach</Text>{current.food.map(place=><Place key={place.name} place={place}/>)}</View>}
    {!!current?.nearby.length&&<View style={s.group}><Text style={s.section}>Make a day of it</Text>{current.nearby.map(place=><Place key={place.name} place={place}/>)}</View>}
    {!loading&&!current?.food.length&&<View style={s.group}><Text style={s.section}>Explore the neighborhood</Text><Text style={s.body}>No sourced food listings were found within 3 km. Explore nearby dining on the map.</Text></View>}
    <View style={s.row}><Link label="Explore nearby food" url={maps}/><Link label="Plan your visit" url={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${beach.latitude},${beach.longitude}`)}`}/></View>
    {!!current?.guides.length&&<View style={s.row}>{current.guides.map(g=><Link key={g.url} label={g.title+' · Wikivoyage'} url={g.url}/>)}<Link label="Guide text · CC BY-SA 4.0 · excerpts" url="https://creativecommons.org/licenses/by-sa/4.0/"/></View>}
    <Text style={s.small}>Nearby places are travel-guide listings, not rankings. Distances are straight-line from the beach location. Check current hours, prices, access and reservations with each venue.</Text>
    {current&&<Text style={s.small}>Travel information checked {new Date(current.fetchedAt).toLocaleString()}{Date.now()-current.fetchedAt>24*3600000?' · Saved information':''}. Refreshed after 24 hours when viewed.</Text>}
    {!!current?.errors.length&&<Text style={s.warning}>{current.errors.join(' ')}</Text>}
    {storageError&&<Text style={s.small}>Travel information could not be saved for offline reuse.</Text>}
    {!loading&&<Pressable accessibilityRole="button" onPress={()=>setRetry(n=>n+1)} style={s.retry}><Text style={s.link}>{((current?.errors.length??0)>0||!photo||failedImage)?'Retry travel information':'↻ Refresh travel information'}</Text></Pressable>}
  </View>;
}
const s=StyleSheet.create({wrap:{gap:14},photoWrap:{overflow:'hidden',borderRadius:18,backgroundColor:'#0b1e2b'},photo:{width:'100%',height:210},credit:{padding:12,gap:5},placeholder:{minHeight:185,backgroundColor:'#183b47',borderRadius:18,padding:20,justifyContent:'center',alignItems:'center',gap:10},placeholderIcon:{fontSize:44,color:'#42e0cc'},eyebrow:{fontFamily:'PoppinsSemiBold',fontSize:10,letterSpacing:1.6,color:'#69e5d7'},section:{fontFamily:'PoppinsSemiBold',fontSize:15,color:'#e0f1f4'},body:{fontFamily:'PoppinsRegular',fontSize:13,lineHeight:21,color:'#c6dce3'},small:{fontFamily:'PoppinsRegular',fontSize:10,lineHeight:17,color:'#9db8c4'},link:{fontFamily:'PoppinsMedium',fontSize:11,lineHeight:20,color:'#66e2d6'},row:{flexDirection:'row',flexWrap:'wrap',gap:9,alignItems:'center'},group:{gap:12},place:{backgroundColor:'#0c202c',borderRadius:14,padding:14,gap:7},placeName:{flexGrow:1,flexShrink:1,fontFamily:'PoppinsSemiBold',fontSize:12,color:'#e1f2f4'},warning:{fontFamily:'PoppinsRegular',fontSize:11,lineHeight:18,color:'#ffd28a'},retry:{alignSelf:'flex-start',paddingVertical:8}});
