import { useEffect, useState } from 'react'
import type { Employee, SummaryStatus } from '../api'
import { formatClock } from '../format'
import { PUNCH_TYPE_LABELS } from '../labels'
import { Brand } from './Brand'
import type { QueuedPunch } from '../offlineQueue'

/** Der Tablet-Kiosk zeigt bewusst nur drei Zustände (nicht den vollen
 * HR-Status-Katalog) – reicht für "wer ist gerade da": */
type Presence = 'PRESENT' | 'ON_BREAK' | 'ON_ERRAND' | 'ABSENT'

function toPresence(status: SummaryStatus): Presence {
  if (status === 'PRESENT') return 'PRESENT'
  if (status === 'ON_BREAK') return 'ON_BREAK'
  if (status === 'ON_ERRAND') return 'ON_ERRAND'
  return 'ABSENT'
}

const PRESENCE_TILE_CLASS: Record<Presence, string> = {
  PRESENT: 'bg-sky-950 border-2 border-sky-500 hover:bg-sky-900',
  ON_BREAK: 'bg-orange-950 border-2 border-orange-500 hover:bg-orange-900',
  ON_ERRAND: 'bg-violet-950 border-2 border-violet-500 hover:bg-violet-900',
  ABSENT: 'bg-slate-800 border-2 border-transparent hover:bg-slate-700',
}

const PRESENCE_LABEL: Record<Presence, string> = {
  PRESENT: 'Anwesend',
  ON_BREAK: 'Pause',
  ON_ERRAND: 'Dienstgang',
  ABSENT: 'Abwesend',
}

export function EmployeeGrid({
  employees,
  deviceName,
  isLoading,
  error,
  isOnline,
  queuedPunches,
  onDiscardQueuedPunch,
  selectionError,
  nfcSupported,
  nfcActive,
  nfcError,
  onToggleNfc,
  onSelect,
  onReset,
  terminalBar,
  rfidRequired = false,
  greeting = null,
  sort = 'LAST_NAME',
  onRegisterCard,
  cardReaderReady = false,
}: {
  employees: Employee[]
  deviceName: string
  isLoading: boolean
  error: string | null
  isOnline: boolean
  queuedPunches: QueuedPunch[]
  onDiscardQueuedPunch: (idempotencyKey: string) => void
  selectionError: string | null
  nfcSupported: boolean
  nfcActive: boolean
  nfcError: string | null
  onToggleNfc: () => void
  onSelect: (employee: Employee) => void
  /** Prüft die Admin-PIN (wirft bei falscher PIN) und setzt das Gerät danach zurück. */
  onReset: (adminPin: string) => Promise<void>
  /** RFID-Terminalmodus (Aktion wählen, Chip vorhalten) – oberhalb des Mitarbeiterrasters. */
  terminalBar?: React.ReactNode
  /** RFID-Pflicht: Kacheln lösen keine Stempelung aus. */
  rfidRequired?: boolean
  /** Hinweistext über den Kacheln (Einstellungen → Kiosk) */
  greeting?: string | null
  sort?: 'LAST_NAME' | 'FIRST_NAME'
  /** Chip-Selbstregistrierung erlaubt: bei RFID-Pflicht führt das Antippen des Namens dorthin
   * (Stempeln geht dann nur per Chip), sonst über die Stempel-Seite des Mitarbeiters. */
  onRegisterCard?: (employee: Employee) => void
  /** Chips werden über einen USB-/Bluetooth-Leser (Tastatur-Modus) gelesen – auch ohne Web-NFC. */
  cardReaderReady?: boolean
}) {
  const [search, setSearch] = useState('')
  const [now, setNow] = useState(() => new Date())
  const [resetConfirm, setResetConfirm] = useState(false)
  const [adminPin, setAdminPin] = useState('')
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [queueOpen, setQueueOpen] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(interval)
  }, [])

  const sortKey = (e: Employee) =>
    sort === 'FIRST_NAME' ? `${e.first_name} ${e.last_name}` : `${e.last_name} ${e.first_name}`
  const filtered = employees
    .filter((employee) => `${employee.first_name} ${employee.last_name}`.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => sortKey(a).localeCompare(sortKey(b), 'de'))

  return (
    <div className="flex h-full flex-col bg-slate-950 text-white">
      <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
        <div className="flex items-center gap-6">
          <Brand compact />
          <div>
            <div className="text-sm text-slate-400">Gerät: {deviceName}</div>
            <div className="text-3xl font-semibold tabular-nums">{formatClock(now)}</div>
          </div>
        </div>
        <input
          type="text"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Name suchen…"
          className="w-64 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-white outline-none focus:border-emerald-500"
        />
        <button
          type="button"
          onClick={() => setQueueOpen(true)}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
            isOnline ? 'border-slate-700 text-slate-400' : 'border-amber-600 text-amber-400'
          }`}
        >
          <span className={`h-2.5 w-2.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          {isOnline ? 'Online' : 'Offline'}
          {queuedPunches.length > 0 && (
            <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs">{queuedPunches.length}</span>
          )}
        </button>
        {!nfcSupported && cardReaderReady && (
          <span
            className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-400"
            title="Web-NFC gibt es nur in Chrome auf Android. Auf iPhone, iPad und Mac Chips über einen USB- oder Bluetooth-Leser einlesen."
          >
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            Chip-Leser: USB/Bluetooth bereit
          </span>
        )}
        {nfcSupported && (
          <button
            type="button"
            onClick={onToggleNfc}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
              nfcActive ? 'border-emerald-600 text-emerald-400' : 'border-slate-700 text-slate-400'
            }`}
          >
            <span className={`h-2.5 w-2.5 rounded-full ${nfcActive ? 'bg-emerald-500' : 'bg-slate-600'}`} />
            {nfcActive ? 'NFC aktiv – Chip vorhalten' : 'NFC aktivieren'}
          </button>
        )}
        <button
          type="button"
          onClick={() => setResetConfirm(true)}
          className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-400"
        >
          Gerät zurücksetzen
        </button>
      </header>

      {terminalBar}

      <main className="flex-1 overflow-y-auto p-6">
        {greeting && <p className="mb-4 text-xl font-medium text-slate-200">{greeting}</p>}
        {rfidRequired && (
          <p className="mb-3 text-slate-400">
            Stempeln nur mit Chip: oben eine Aktion wählen und den Chip vorhalten.
            {onRegisterCard && ' Noch kein Chip? Eigenen Namen antippen und mit dem PIN registrieren.'}
          </p>
        )}
        {isLoading && <p className="text-slate-400">Lädt…</p>}
        {error && <p className="text-red-400">{error}</p>}
        {nfcError && <p className="text-amber-400">{nfcError}</p>}
        {selectionError && <p className="text-red-400">{selectionError}</p>}
        <div className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5">
          {filtered.map((employee) => {
            const presence = toPresence(employee.today_status)
            return (
              <button
                key={employee.id}
                type="button"
                onClick={() => {
                  if (!rfidRequired) onSelect(employee)
                  else if (onRegisterCard) onRegisterCard(employee)
                }}
                className={`flex flex-col items-center justify-center gap-1 rounded-xl p-6 text-center text-lg font-medium transition-colors active:scale-[0.98] ${PRESENCE_TILE_CLASS[presence]}`}
              >
                <span>{employee.first_name}</span>
                <span>{employee.last_name}</span>
                <span className="mt-1 text-xs font-normal uppercase tracking-wide text-slate-300">
                  {PRESENCE_LABEL[presence]}
                </span>
              </button>
            )
          })}
          {!isLoading && filtered.length === 0 && (
            <p className="col-span-full text-slate-500">Keine Mitarbeiter gefunden.</p>
          )}
        </div>
      </main>

      <div className="flex gap-4 border-t border-slate-800 px-6 py-3 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-2 border-sky-500 bg-sky-950" />
          Anwesend
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-2 border-orange-500 bg-orange-950" />
          Pause
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-2 border-violet-500 bg-violet-950" />
          Dienstgang
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border-2 border-transparent bg-slate-800" />
          Abwesend
        </span>
      </div>

      {queueOpen && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/70">
          <div className="flex max-h-[80vh] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-xl bg-slate-900 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Offline-Warteschlange</h2>
              <button type="button" onClick={() => setQueueOpen(false)} className="text-slate-400">
                Schließen
              </button>
            </div>
            {queuedPunches.length === 0 && (
              <p className="text-slate-400">Keine wartenden Stempelungen.</p>
            )}
            {queuedPunches.map((punch) => (
              <div
                key={punch.idempotency_key}
                className="flex items-center justify-between rounded-lg border border-slate-700 px-4 py-3"
              >
                <div>
                  <div className="font-medium">
                    {punch.employee_name} – {PUNCH_TYPE_LABELS[punch.punch_type]}
                  </div>
                  <div className="text-xs text-slate-400">{new Date(punch.timestamp_utc).toLocaleString('de-DE')}</div>
                  {punch.error && <div className="text-xs text-red-400">Fehler: {punch.error}</div>}
                </div>
                {punch.error && (
                  <button
                    type="button"
                    onClick={() => onDiscardQueuedPunch(punch.idempotency_key)}
                    className="rounded-lg border border-red-700 px-3 py-1.5 text-sm text-red-400"
                  >
                    Verwerfen
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {resetConfirm && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/70">
          <div className="flex w-full max-w-sm flex-col gap-4 rounded-xl bg-slate-900 p-6">
            <p>Gerät zurücksetzen und neues Tablet-Token eingeben? Dafür ist die Tablet-Admin-PIN nötig.</p>
            <input
              type="password"
              inputMode="numeric"
              autoComplete="off"
              autoFocus
              value={adminPin}
              onChange={(event) => setAdminPin(event.target.value.replace(/\D/g, '').slice(0, 8))}
              placeholder="Admin-PIN"
              className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-center text-2xl tracking-widest outline-none focus:border-emerald-500"
            />
            {resetError && <p className="text-sm text-red-400">{resetError}</p>}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setResetConfirm(false)
                  setAdminPin('')
                  setResetError(null)
                }}
                className="rounded-lg border border-slate-700 px-4 py-2"
              >
                Abbrechen
              </button>
              <button
                type="button"
                disabled={adminPin.length < 4 || resetting}
                onClick={() => {
                  setResetting(true)
                  setResetError(null)
                  onReset(adminPin)
                    .catch((err: unknown) => setResetError(err instanceof Error ? err.message : 'Zurücksetzen fehlgeschlagen.'))
                    .finally(() => {
                      setResetting(false)
                      setAdminPin('')
                    })
                }}
                className="rounded-lg bg-red-600 px-4 py-2 font-medium disabled:opacity-50"
              >
                {resetting ? 'Prüfe…' : 'Zurücksetzen'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
