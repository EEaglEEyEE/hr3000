import type { Employee } from './api'

const CACHE_KEY = 'kiosk.employee_cache'

export function getCachedEmployees(): Employee[] | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? (JSON.parse(raw) as Employee[]) : null
  } catch {
    return null
  }
}

export function setCachedEmployees(employees: Employee[]): void {
  localStorage.setItem(CACHE_KEY, JSON.stringify(employees))
}
