import { deviceLogin, type DeviceLoginResponse } from './api'

const STORAGE_KEY = 'kiosk.device_token'

export function getStoredDeviceToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function storeDeviceToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearStoredDeviceToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/** Es gibt bewusst keinen Refresh-Endpoint für Geräte (siehe app/api/auth.py) –
 * der rohe device_token ist ein statisches, langlebiges Geheimnis, daher kann
 * bei jedem 401 (abgelaufenes Access-Token, siehe jwt_device_token_expire_hours)
 * einfach erneut damit eingeloggt werden. */
export async function loginWithStoredToken(): Promise<DeviceLoginResponse | null> {
  const token = getStoredDeviceToken()
  if (!token) return null
  return deviceLogin(token)
}
