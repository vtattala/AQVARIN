export async function registerAlertChecks(enabled: boolean): Promise<string> {
  return enabled?'Alerts refresh while AQVARIN is open. Browser background delivery is unavailable.':'Alerts paused';
}
