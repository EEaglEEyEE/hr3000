import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createPunch,
  deviceLogin,
  generateIdempotencyKey,
  pairDevice,
  registerCard,
  setupPin,
  getKioskConfig,
  getLeaveEntitlement,
  getOvertimeBalance,
  listLocationEmployees,
  NetworkError,
  verifyAdminPin,
  type DeviceLoginResponse,
  type Employee,
  type LeaveEntitlement,
  type OvertimeBalance,
  type PunchType,
} from './api'
import {
  clearStoredDeviceToken,
  getStoredDeviceToken,
  loginWithStoredToken,
  resumeSession,
  storeDeviceToken,
  type ResumeResult,
} from './deviceAuth'
import { getCachedEmployees, setCachedEmployees } from './employeeCache'
import { describeNfcError, isNfcSupported, startNfcScan, type NfcScanSession } from './nfcScanner'
import { discardQueuedPunch, enqueuePunch, flushQueue, getQueuedPunches, type QueuedPunch } from './offlineQueue'
import { CardScan, type CardScanStatus } from './components/CardScan'
import { ConfirmationOverlay } from './components/ConfirmationOverlay'
import { DeviceSetup } from './components/DeviceSetup'
import { EmployeeGrid } from './components/EmployeeGrid'
import { PinPad } from './components/PinPad'
import { PunchPad } from './components/PunchPad'
import { TERMINAL_ARM_SECONDS, TerminalBar, type TerminalResult } from './components/TerminalBar'
import { normalizeCardUid, useKeyboardCardReader } from './cardReader'
import { useWakeLock } from './wakeLock'
import { useScreenHours } from './screenHours'
import { tokenFromQr } from './components/QrScanner'
import { formatDays, formatMinutesAsHours } from './format'
import { PUNCH_TYPE_LABELS } from './labels'

const QUEUE_FLUSH_INTERVAL_MS = 20_000

/** Einrichtung per QR-Code-Link ".../#token=…" (Kamera-App des Tablets): Token einmalig beim Laden
 * übernehmen und sofort aus der Adresse entfernen (steht im Fragment, geht nie an den Server). */
const LINK_TOKEN = (() => {
  if (!window.location.hash.includes('token=')) return null
  const token = tokenFromQr(window.location.hash)
  window.history.replaceState(null, '', window.location.pathname)
  return token || null
})()
const CONFIG_REFRESH_MS = 30_000
/** Einrichtungsbildschirm mit gespeichertem Token: so oft erneut anmelden */
const RESUME_RETRY_MS = 60_000

function resumeMessage(kind: Exclude<ResumeResult['kind'], 'ok'>): string | undefined {
  if (kind === 'rejected')
    return 'Der Server hat die Anmeldung dieses Tablets abgelehnt. Es versucht es jede Minute erneut – wurde es in der HR-Webapp entfernt, bitte neu einrichten.'
  if (kind === 'unreachable')
    return 'Server nicht erreichbar – das Tablet meldet sich automatisch wieder an, sobald er erreichbar ist.'
  return undefined
}

type Screen =
  | { kind: 'loading' }
  | { kind: 'setup' }
  | { kind: 'grid' }
  | { kind: 'punchpad'; employee: Employee; nfcUid?: string; pin?: string }
  | { kind: 'pinpad'; employee: Employee }
  // Eigenen Chip registrieren: erst PIN, dann Chip vorhalten
  | { kind: 'cardPin'; employee: Employee; error?: string }
  // Erster eigener PIN: eingeben, wiederholen, dann direkt weiter zum Stempeln
  | { kind: 'pinSetup'; employee: Employee; first?: string; error?: string }
  | { kind: 'cardScan'; employee: Employee; pin: string; status: CardScanStatus; message?: string }
  | { kind: 'confirm'; employee: Employee; punchType: PunchType; balance: OvertimeBalance | null; offline: boolean }

function genericErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  return 'Keine Verbindung zum Server.'
}

export default function App() {
  const [session, setSession] = useState<DeviceLoginResponse | null>(null)
  const [screen, setScreen] = useState<Screen>({ kind: 'loading' })
  const [setupError, setSetupError] = useState<string | undefined>(undefined)
  const [setupSubmitting, setSetupSubmitting] = useState(false)

  const [employees, setEmployees] = useState<Employee[]>([])
  const [employeesLoading, setEmployeesLoading] = useState(false)
  const [employeesError, setEmployeesError] = useState<string | null>(null)

  const [punchSubmitting, setPunchSubmitting] = useState(false)
  const [punchError, setPunchError] = useState<string | null>(null)

  const [isOnline, setIsOnline] = useState(() => navigator.onLine)
  const [queuedPunches, setQueuedPunches] = useState<QueuedPunch[]>(() => getQueuedPunches())

  const [employeeInfo, setEmployeeInfo] = useState<{
    balance: OvertimeBalance | null
    leave: LeaveEntitlement | null
  } | null>(null)

  const [nfcSession, setNfcSession] = useState<NfcScanSession | null>(null)
  const [nfcError, setNfcError] = useState<string | null>(null)

  // RFID-Terminalmodus: gewählte Aktion bleibt 10 s (ab letztem Scan) aktiv.
  const [armed, setArmed] = useState<PunchType | null>(null)
  const [armedUntil, setArmedUntil] = useState(0)
  const [terminalResult, setTerminalResult] = useState<TerminalResult | null>(null)
  const recentScans = useRef(new Map<string, number>())
  const handleCardRef = useRef<(uid: string) => void>(() => undefined)

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true)
    }
    function handleOffline() {
      setIsOnline(false)
    }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Beim Start: falls schon ein Geräte-Token gespeichert ist, direkt neu
  // einloggen (es gibt keinen Refresh-Endpoint, siehe deviceAuth.ts).
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (LINK_TOKEN) {
        try {
          const result = await deviceLogin(LINK_TOKEN)
          storeDeviceToken(LINK_TOKEN)
          if (cancelled) return
          setSession(result)
          setScreen({ kind: 'grid' })
          return
        } catch {
          if (!cancelled) setSetupError('Der QR-Code enthält kein gültiges Tablet-Token.')
        }
      }
      // Token bleibt auch bei Fehlern erhalten (siehe resumeSession); der Einrichtungsbildschirm
      // versucht es dann regelmäßig erneut.
      const result = await resumeSession()
      if (cancelled) return
      if (result.kind === 'ok') {
        setSession(result.session)
        setScreen({ kind: 'grid' })
        return
      }
      setSetupError(resumeMessage(result.kind))
      setScreen({ kind: 'setup' })
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  // Einrichtungsbildschirm, obwohl ein Token gespeichert ist (Server war nicht erreichbar oder hat
  // abgelehnt): jede Minute erneut anmelden – nach einer Störung ist das Tablet so von selbst zurück.
  useEffect(() => {
    if (screen.kind !== 'setup' || setupSubmitting || !getStoredDeviceToken()) return
    let active = true
    const interval = setInterval(() => {
      void resumeSession().then((result) => {
        if (!active || result.kind !== 'ok') return
        setSession(result.session)
        setSetupError(undefined)
        setScreen({ kind: 'grid' })
      })
    }, RESUME_RETRY_MS)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [screen.kind, setupSubmitting])

  const loadEmployees = useCallback(async (activeSession: DeviceLoginResponse) => {
    setEmployeesLoading(true)
    setEmployeesError(null)
    try {
      const result = await listLocationEmployees(activeSession.location_id, activeSession.access_token)
      setEmployees(result)
      setCachedEmployees(result)
    } catch (err) {
      // Offline: letzten bekannten Stand aus dem Cache zeigen statt eines leeren Grids.
      const cached = err instanceof NetworkError ? getCachedEmployees() : null
      if (cached) {
        setEmployees(cached)
        setEmployeesError('Offline – zeigt zuletzt geladenen Stand.')
      } else {
        setEmployeesError(genericErrorMessage(err))
      }
    } finally {
      setEmployeesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (session && screen.kind === 'grid') void loadEmployees(session)
  }, [session, screen.kind, loadEmployees])

  // Einstellungen (Saldo/Resturlaub zeigen, Pausen-Buttons, Text, Sortierung) regelmäßig nachladen –
  // Änderungen in der HR-Webapp wirken so ohne Neuanmeldung des Tablets.
  const accessToken = session?.access_token
  useEffect(() => {
    if (!accessToken || screen.kind !== 'grid') return
    let cancelled = false
    async function refresh() {
      try {
        const config = await getKioskConfig(accessToken!)
        if (cancelled) return
        setSession((current) => {
          if (!current) return current
          const changed = (Object.keys(config) as (keyof typeof config)[]).some((key) => current[key] !== config[key])
          return changed ? { ...current, ...config } : current
        })
      } catch {
        // offline oder Token abgelaufen – beim nächsten Durchlauf erneut
      }
    }
    void refresh()
    const interval = setInterval(() => void refresh(), CONFIG_REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [accessToken, screen.kind])

  async function handleSetupSubmit(input: string) {
    setSetupSubmitting(true)
    setSetupError(undefined)
    try {
      // Kurzer Kopplungscode (XXXX-XXXX) oder das lange Geräte-Token
      const compact = input.replace(/[\s-]/g, '')
      const deviceToken = /^[A-Za-z0-9]{8}$/.test(compact) ? (await pairDevice(compact)).device_token : input
      const result = await deviceLogin(deviceToken)
      storeDeviceToken(deviceToken)
      setSession(result)
      setScreen({ kind: 'grid' })
    } catch (err) {
      setSetupError(
        err instanceof ApiError && err.code === 'INVALID_DEVICE_TOKEN'
          ? 'Unbekanntes Gerätetoken.'
          : err instanceof ApiError && err.code === 'PAIRING_CODE_INVALID'
            ? 'Kopplungscode ungültig oder abgelaufen – bitte in der HR-Webapp neu erzeugen.'
            : genericErrorMessage(err),
      )
    } finally {
      setSetupSubmitting(false)
    }
  }

  async function handleReset(adminPin: string) {
    // Nur mit gültiger Kiosk-Admin-PIN (online geprüft) – sonst könnte jeder das Tablet abmelden.
    try {
      await withAuthRetry((accessToken) => verifyAdminPin(adminPin, accessToken))
    } catch (err) {
      if (err instanceof NetworkError) throw new Error('Offline – Zurücksetzen ist nur mit Verbindung möglich.')
      if (err instanceof ApiError) throw new Error(err.message)
      throw err
    }
    clearStoredDeviceToken()
    setSession(null)
    setEmployees([])
    setScreen({ kind: 'setup' })
  }

  /** Führt eine Aktion aus; bei 401 (abgelaufenes Access-Token) einmalig mit
   * dem gespeicherten Geräte-Token neu einloggen und erneut versuchen. */
  const withAuthRetry = useCallback(
    async <T,>(action: (accessToken: string) => Promise<T>): Promise<T> => {
      if (!session) throw new ApiError(401, 'NO_SESSION', 'Nicht angemeldet.')
      try {
        return await action(session.access_token)
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          const refreshed = await loginWithStoredToken()
          if (refreshed) {
            setSession(refreshed)
            return action(refreshed.access_token)
          }
        }
        throw err
      }
    },
    [session],
  )

  const flushOfflineQueue = useCallback(async () => {
    if (!session) return
    const before = getQueuedPunches().length
    if (before === 0) return
    await flushQueue(
      (punch) =>
        withAuthRetry((accessToken) =>
          createPunch(accessToken, {
            employee_id: punch.employee_id,
            punch_type: punch.punch_type,
            timestamp_utc: punch.timestamp_utc,
            idempotency_key: punch.idempotency_key,
            ...(punch.pin ? { pin: punch.pin } : {}),
            ...(punch.nfc_uid ? { nfc_uid: punch.nfc_uid } : {}),
          }),
        ),
      setQueuedPunches,
    )
    // Erfolgreich nachgesendete Stempelungen ändern den Anwesenheitsstatus im
    // Grid – ohne diesen Reload bliebe die Kachel bis zum nächsten Bildschirm-
    // wechsel auf dem veralteten Offline-Stand stehen.
    if (getQueuedPunches().length < before) void loadEmployees(session)
  }, [session, withAuthRetry, loadEmployees])

  useEffect(() => {
    if (!isOnline || !session) return
    void flushOfflineQueue()
    const interval = setInterval(() => void flushOfflineQueue(), QUEUE_FLUSH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [isOnline, session, flushOfflineQueue])

  const punchpadEmployeeId = screen.kind === 'punchpad' ? screen.employee.id : null
  // Einstellungen → Kiosk: Saldo/Resturlaub am Gemeinschafts-Tablet zeigen (Standard: ja)
  const showBalance = session?.show_balance !== false
  const showVacation = session?.show_vacation !== false

  // Resturlaub/Gleitzeitsaldo sind nur Zusatzinfo bei der Mitarbeiterauswahl –
  // schlägt der Abruf fehl (z.B. offline), wird einfach nichts angezeigt.
  useEffect(() => {
    if (punchpadEmployeeId === null || !session) {
      setEmployeeInfo(null)
      return
    }
    const employeeId = punchpadEmployeeId
    let cancelled = false
    async function load() {
      const [balance, leave] = await Promise.all([
        showBalance
          ? withAuthRetry((accessToken) => getOvertimeBalance(employeeId, accessToken)).catch(() => null)
          : null,
        showVacation
          ? withAuthRetry((accessToken) => getLeaveEntitlement(employeeId, accessToken)).catch(() => null)
          : null,
      ])
      if (!cancelled) setEmployeeInfo({ balance, leave })
    }
    setEmployeeInfo(null)
    void load()
    return () => {
      cancelled = true
    }
  }, [punchpadEmployeeId, session, withAuthRetry, showBalance, showVacation])

  async function handleToggleNfc() {
    if (nfcSession) {
      nfcSession.stop()
      setNfcSession(null)
      return
    }
    setNfcError(null)
    try {
      // Über die Ref immer die aktuelle Logik (Mitarbeiterliste, gewählte Aktion) verwenden.
      const newSession = await startNfcScan(
        (serialNumber) => handleCardRef.current(serialNumber),
        (message) => setNfcError(message),
      )
      setNfcSession(newSession)
    } catch (err) {
      setNfcError(describeNfcError(err))
    }
  }

  useEffect(() => () => nfcSession?.stop(), [nfcSession])

  // Gewählte Aktion läuft nach 10 s ohne Scan ab.
  useEffect(() => {
    if (!armed) return
    const timeout = setTimeout(() => setArmed(null), Math.max(0, armedUntil - Date.now()))
    return () => clearTimeout(timeout)
  }, [armed, armedUntil])

  // Ergebnis-Hinweis nach ein paar Sekunden ausblenden.
  useEffect(() => {
    if (!terminalResult) return
    const timeout = setTimeout(() => setTerminalResult(null), 6000)
    return () => clearTimeout(timeout)
  }, [terminalResult])

  function armAction(type: PunchType) {
    setArmed(type)
    setArmedUntil(Date.now() + TERMINAL_ARM_SECONDS * 1000)
    setTerminalResult(null)
    // Web-NFC braucht eine Nutzeraktion zum Starten – das Antippen der Aktion genügt.
    if (isNfcSupported() && !nfcSession) void handleToggleNfc()
  }

  /** Ein Chip wurde gelesen (Web-NFC oder USB-/Bluetooth-Leser). */
  function handleCard(rawUid: string) {
    if (session?.rfid_enabled === false) return
    if (screen.kind === 'cardScan') {
      if (screen.status === 'waiting') void submitCardRegistration(screen.employee, screen.pin, normalizeCardUid(rawUid))
      return
    }
    if (screen.kind !== 'grid') return
    const uid = normalizeCardUid(rawUid)
    const employee = employees.find((candidate) => candidate.nfc_uid && normalizeCardUid(candidate.nfc_uid) === uid)
    if (!employee) {
      const message = `Chip ist keinem Mitarbeiter zugeordnet (UID: ${uid}).`
      if (armed) setTerminalResult({ ok: false, title: message })
      else setNfcError(message)
      return
    }
    setNfcError(null)
    if (!armed) {
      // Ohne gewählte Aktion: Mitarbeiter direkt öffnen (kein Antippen nötig).
      setScreen({ kind: 'punchpad', employee, nfcUid: uid })
      return
    }
    setArmedUntil(Date.now() + TERMINAL_ARM_SECONDS * 1000)
    const key = `${uid}:${armed}`
    const last = recentScans.current.get(key)
    if (last && Date.now() - last < 60_000) {
      setTerminalResult({ ok: false, title: `${employee.first_name} ${employee.last_name}: ${PUNCH_TYPE_LABELS[armed]} wurde gerade schon erfasst.` })
      return
    }
    recentScans.current.set(key, Date.now())
    void terminalPunch(employee, armed, uid)
  }
  handleCardRef.current = handleCard

  // Einstellungen → Kiosk: Chip-Funktion kann je Mandant abgeschaltet werden.
  const rfidEnabled = session?.rfid_enabled !== false
  useKeyboardCardReader(
    (uid) => handleCardRef.current(uid),
    Boolean(session) && (screen.kind === 'grid' || screen.kind === 'cardScan') && rfidEnabled,
  )
  const cardSelfRegistration = rfidEnabled && session?.card_self_registration !== false

  function startCardRegistration(employee: Employee, pin?: string) {
    setPunchError(null)
    if (!employee.has_pin) {
      if (session?.pin_self_setup !== false) {
        // Erst eigenen PIN festlegen, danach steht „Eigenen Chip registrieren“ auf der Stempel-Seite bereit.
        setScreen({ kind: 'pinSetup', employee })
        return
      }
      setPunchError('Zum Registrieren eines Chips ist ein PIN nötig – bitte bei HR melden.')
      setScreen({ kind: 'grid' })
      return
    }
    if (pin) beginCardScan(employee, pin)
    else setScreen({ kind: 'cardPin', employee })
  }

  function beginCardScan(employee: Employee, pin: string) {
    setScreen({ kind: 'cardScan', employee, pin, status: 'waiting' })
    // Web-NFC braucht eine Nutzeraktion – die PIN-Bestätigung bzw. der Tipp zählt.
    if (isNfcSupported() && !nfcSession) void handleToggleNfc()
  }

  async function submitCardRegistration(employee: Employee, pin: string, uid: string) {
    setScreen({ kind: 'cardScan', employee, pin, status: 'saving' })
    try {
      await withAuthRetry((accessToken) => registerCard(accessToken, { employee_id: employee.id, pin, nfc_uid: uid }))
      setScreen({ kind: 'cardScan', employee, pin, status: 'done' })
      if (session) void loadEmployees(session)
      setTimeout(() => setScreen((current) => (current.kind === 'cardScan' ? { kind: 'grid' } : current)), 3000)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'PIN_INVALID') {
        setScreen({ kind: 'cardPin', employee, error: 'PIN falsch.' })
        return
      }
      setScreen({ kind: 'cardScan', employee, pin, status: 'error', message: genericErrorMessage(err) })
    }
  }

  // Ohne Chip innerhalb von 30 s zurück zur Übersicht.
  const waitingForCard = screen.kind === 'cardScan' && screen.status === 'waiting'
  useEffect(() => {
    if (!waitingForCard) return
    const timeout = setTimeout(() => setScreen({ kind: 'grid' }), 30_000)
    return () => clearTimeout(timeout)
  }, [waitingForCard])
  // Kiosk-Tablet nicht in den Ruhezustand gehen lassen, solange es eingerichtet ist – und nur im
  // eingestellten Zeitfenster (Einstellungen → Kiosk bzw. Gerät). Außerhalb gibt die App die Sperre
  // frei, Android schaltet den Bildschirm nach dem Geräte-Timeout aus; eine Web-App kann ihn morgens
  // nicht wieder einschalten (Ein/Aus-Taste), beim Aufwachen wird die Sperre neu angefordert.
  const withinScreenHours = useScreenHours(session?.screen_on_from, session?.screen_on_until, session?.timezone)
  useWakeLock(Boolean(session) && withinScreenHours)

  // Einstellungen → Kiosk: helle Darstellung kehrt die Farbskalen um (siehe theme-inverted.css).
  const light = session?.theme === 'LIGHT'
  useEffect(() => {
    document.documentElement.classList.toggle('theme-inverted', light)
    document.documentElement.style.colorScheme = light ? 'light' : 'dark'
  }, [light])

  async function terminalPunch(employee: Employee, punchType: PunchType, uid: string) {
    const name = `${employee.first_name} ${employee.last_name}`
    try {
      await withAuthRetry((accessToken) =>
        createPunch(accessToken, {
          employee_id: employee.id,
          punch_type: punchType,
          timestamp_utc: new Date().toISOString(),
          idempotency_key: generateIdempotencyKey(),
          nfc_uid: uid,
        }),
      )
      const [balance, leave] = await Promise.all([
        showBalance
          ? withAuthRetry((accessToken) => getOvertimeBalance(employee.id, accessToken)).catch(() => null)
          : null,
        showVacation
          ? withAuthRetry((accessToken) => getLeaveEntitlement(employee.id, accessToken)).catch(() => null)
          : null,
      ])
      const details = [
        balance ? `Saldo ${formatMinutesAsHours(balance.running_balance_minutes)} Std.` : null,
        leave ? `Resturlaub ${formatDays(leave.remaining_days)} Tage` : null,
      ].filter(Boolean)
      setTerminalResult({ ok: true, title: `✓ ${name}: ${PUNCH_TYPE_LABELS[punchType]} erfasst`, detail: details.join(' · ') })
      if (session) void loadEmployees(session)
    } catch (err) {
      if (err instanceof NetworkError) {
        setQueuedPunches(
          enqueuePunch({
            idempotency_key: generateIdempotencyKey(),
            employee_id: employee.id,
            employee_name: name,
            punch_type: punchType,
            timestamp_utc: new Date().toISOString(),
            nfc_uid: uid,
          }),
        )
        setTerminalResult({ ok: true, title: `⏳ ${name}: ${PUNCH_TYPE_LABELS[punchType]} offline gespeichert`, detail: 'wird automatisch gesendet' })
        return
      }
      recentScans.current.delete(`${uid}:${punchType}`)
      setTerminalResult({ ok: false, title: `${name}: ${genericErrorMessage(err)}` })
    }
  }

  /** Entscheidet beim Antippen einer Mitarbeiter-Kachel, ob zuerst der PIN
   * abgefragt werden muss – die Abfrage soll vor der Aktionsauswahl kommen,
   * nicht erst danach. Eine NFC-Karte hat das bereits vorher geklärt (siehe
   * handleToggleNfc) und ruft diese Funktion nicht auf. */
  function handleSelectEmployee(employee: Employee) {
    setPunchError(null)
    if (!session?.require_pin) {
      setScreen({ kind: 'punchpad', employee })
      return
    }
    if (!employee.has_pin) {
      if (session.pin_self_setup !== false) {
        setScreen({ kind: 'pinSetup', employee })
        return
      }
      setPunchError('Für diesen Mitarbeiter ist kein PIN hinterlegt. Bitte bei HR melden.')
      return
    }
    setScreen({ kind: 'pinpad', employee })
  }

  async function handlePinSetup(employee: Employee, first: string | undefined, pin: string) {
    if (!first) {
      setScreen({ kind: 'pinSetup', employee, first: pin })
      return
    }
    if (first !== pin) {
      setScreen({ kind: 'pinSetup', employee, error: 'Die PINs stimmen nicht überein – bitte neu festlegen.' })
      return
    }
    setPunchSubmitting(true)
    try {
      await withAuthRetry((accessToken) => setupPin(accessToken, { employee_id: employee.id, pin }))
      if (session) void loadEmployees(session)
      // Direkt weiter zum Stempeln – der PIN ist gerade bestätigt.
      setScreen({ kind: 'punchpad', employee: { ...employee, has_pin: true }, pin })
    } catch (err) {
      setScreen({ kind: 'pinSetup', employee, error: genericErrorMessage(err) })
    } finally {
      setPunchSubmitting(false)
    }
  }

  function handlePunchTypeSelected(punchType: PunchType) {
    if (screen.kind !== 'punchpad') return
    void submitPunch(screen.employee, punchType, screen.pin, screen.nfcUid)
  }

  async function submitPunch(employee: Employee, punchType: PunchType, pin?: string, nfcUid?: string) {
    setPunchSubmitting(true)
    setPunchError(null)
    try {
      await withAuthRetry((accessToken) =>
        createPunch(accessToken, {
          employee_id: employee.id,
          punch_type: punchType,
          timestamp_utc: new Date().toISOString(),
          idempotency_key: generateIdempotencyKey(),
          ...(pin ? { pin } : {}),
          ...(nfcUid ? { nfc_uid: nfcUid } : {}),
        }),
      )
      let balance: OvertimeBalance | null = null
      try {
        if (showBalance) balance = await withAuthRetry((accessToken) => getOvertimeBalance(employee.id, accessToken))
      } catch {
        // Saldo ist nur eine Zusatzinfo – Stempelung selbst war bereits erfolgreich.
      }
      setScreen({ kind: 'confirm', employee, punchType, balance, offline: false })
    } catch (err) {
      if (err instanceof NetworkError) {
        // Keine Verbindung: lokal merken und später automatisch nachsenden,
        // statt dem Mitarbeiter einen harten Fehler zu zeigen.
        setQueuedPunches(
          enqueuePunch({
            idempotency_key: generateIdempotencyKey(),
            employee_id: employee.id,
            employee_name: `${employee.first_name} ${employee.last_name}`,
            punch_type: punchType,
            timestamp_utc: new Date().toISOString(),
            ...(pin ? { pin } : {}),
            ...(nfcUid ? { nfc_uid: nfcUid } : {}),
          }),
        )
        setScreen({ kind: 'confirm', employee, punchType, balance: null, offline: true })
        return
      }
      setPunchError(
        err instanceof ApiError && err.code === 'PIN_INVALID'
          ? 'PIN falsch.'
          : genericErrorMessage(err),
      )
      if (pin !== undefined) setScreen({ kind: 'pinpad', employee })
    } finally {
      setPunchSubmitting(false)
    }
  }

  if (screen.kind === 'loading') {
    return <div className="flex h-full items-center justify-center bg-slate-950 text-white">Lädt…</div>
  }

  if (screen.kind === 'setup') {
    return <DeviceSetup onSubmit={handleSetupSubmit} error={setupError} isSubmitting={setupSubmitting} />
  }

  if (screen.kind === 'grid' && session) {
    return (
      <EmployeeGrid
        employees={employees}
        deviceName={session.device_name}
        isLoading={employeesLoading}
        error={employeesError}
        isOnline={isOnline}
        queuedPunches={queuedPunches}
        onDiscardQueuedPunch={(key) => setQueuedPunches(discardQueuedPunch(key))}
        selectionError={punchError}
        nfcSupported={rfidEnabled && isNfcSupported()}
        cardReaderReady={rfidEnabled}
        nfcActive={nfcSession !== null}
        nfcError={nfcError}
        onToggleNfc={() => void handleToggleNfc()}
        onSelect={handleSelectEmployee}
        onReset={handleReset}
        rfidRequired={rfidEnabled && Boolean(session.rfid_required)}
        onRegisterCard={cardSelfRegistration ? (employee) => startCardRegistration(employee) : undefined}
        greeting={session.greeting}
        sort={session.sort}
        terminalBar={
          rfidEnabled && (
            <TerminalBar
              armed={armed}
              armedUntil={armedUntil}
              onArm={armAction}
              onDisarm={() => setArmed(null)}
              result={terminalResult}
              breakButtons={session.break_buttons !== false}
              errandButtons={session.errand_buttons === true}
            />
          )
        }
      />
    )
  }

  if (screen.kind === 'punchpad') {
    return (
      <PunchPad
        employee={screen.employee}
        isSubmitting={punchSubmitting}
        error={punchError}
        balance={employeeInfo?.balance ?? null}
        leaveEntitlement={employeeInfo?.leave ?? null}
        identifiedViaCard={Boolean(screen.nfcUid)}
        pinConfirmed={Boolean(screen.pin)}
        breakButtons={session?.break_buttons !== false}
        errandButtons={session?.errand_buttons === true}
        onRegisterCard={
          cardSelfRegistration && screen.employee.has_pin
            ? () => startCardRegistration(screen.employee, screen.pin)
            : undefined
        }
        onPunch={handlePunchTypeSelected}
        onCancel={() => {
          setPunchError(null)
          setScreen({ kind: 'grid' })
        }}
      />
    )
  }

  if (screen.kind === 'pinpad') {
    return (
      <PinPad
        employee={screen.employee}
        isSubmitting={punchSubmitting}
        error={punchError}
        onSubmit={(pin) => {
          setPunchError(null)
          setScreen({ kind: 'punchpad', employee: screen.employee, pin })
        }}
        onCancel={() => {
          setPunchError(null)
          setScreen({ kind: 'grid' })
        }}
      />
    )
  }

  if (screen.kind === 'pinSetup') {
    return (
      <PinPad
        key={screen.first ? 'confirm' : 'first'}
        employee={screen.employee}
        isSubmitting={punchSubmitting}
        error={screen.error ?? null}
        minLength={4}
        title={
          screen.first
            ? 'PIN zur Bestätigung wiederholen'
            : 'Willkommen! Bitte einen eigenen PIN festlegen (4–8 Ziffern) – er wird ab jetzt beim Stempeln abgefragt.'
        }
        onSubmit={(pin) => void handlePinSetup(screen.employee, screen.first, pin)}
        onCancel={() => setScreen({ kind: 'grid' })}
      />
    )
  }

  if (screen.kind === 'cardPin') {
    return (
      <PinPad
        employee={screen.employee}
        isSubmitting={false}
        error={screen.error ?? null}
        title="PIN eingeben, um den eigenen Chip zu registrieren"
        onSubmit={(pin) => beginCardScan(screen.employee, pin)}
        onCancel={() => setScreen({ kind: 'grid' })}
      />
    )
  }

  if (screen.kind === 'cardScan') {
    return (
      <CardScan
        employee={screen.employee}
        status={screen.status}
        message={screen.message}
        nfcHint={nfcError}
        onCancel={() => setScreen({ kind: 'grid' })}
      />
    )
  }

  if (screen.kind === 'confirm') {
    return (
      <ConfirmationOverlay
        employee={screen.employee}
        punchType={screen.punchType}
        balance={screen.balance}
        offline={screen.offline}
        onDismiss={() => setScreen({ kind: 'grid' })}
      />
    )
  }

  return null
}
