import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';
import { checkFavoriteAlerts } from './alerts';
const TASK='aqvarin-beach-advisories';
TaskManager.defineTask(TASK,async()=>{try{await checkFavoriteAlerts();return BackgroundTask.BackgroundTaskResult.Success;}catch{return BackgroundTask.BackgroundTaskResult.Failed;}});
export async function registerAlertChecks(enabled: boolean): Promise<string> {
  if(!enabled){if(await TaskManager.isTaskRegisteredAsync(TASK))await BackgroundTask.unregisterTaskAsync(TASK);return 'Alerts paused';}
  if(await BackgroundTask.getStatusAsync()!==BackgroundTask.BackgroundTaskStatus.Available)return 'Background checks unavailable; alerts refresh while the app is open.';
  if(!await TaskManager.isTaskRegisteredAsync(TASK))await BackgroundTask.registerTaskAsync(TASK,{minimumInterval:15});
  return 'Background checks requested. Your phone decides when they run; delivery may be delayed.';
}
