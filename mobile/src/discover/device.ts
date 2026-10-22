import * as Location from 'expo-location';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { Position } from './beaches';
Notifications.setNotificationHandler({handleNotification:async()=>({shouldShowBanner:true,shouldShowList:true,shouldPlaySound:true,shouldSetBadge:false})});
export async function locate(): Promise<Position> {
  const permission=await Location.requestForegroundPermissionsAsync();
  if(!permission.granted)throw new Error('Location permission was declined. You can still search every listed beach.');
  const position=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.Balanced});
  return position.coords;
}
export async function enableNotifications(): Promise<boolean> {
  if(Platform.OS==='android')await Notifications.setNotificationChannelAsync('beach-alerts',{name:'Beach advisories',importance:Notifications.AndroidImportance.HIGH});
  return (await Notifications.requestPermissionsAsync()).granted;
}
export async function notify(title: string, body: string): Promise<void> {
  if(!(await Notifications.getPermissionsAsync()).granted)return;
  await Notifications.scheduleNotificationAsync({content:{title,body,sound:true},trigger:null});
}
