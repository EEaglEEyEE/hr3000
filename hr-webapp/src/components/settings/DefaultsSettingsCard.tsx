import { useEffect, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import { DAY_FLAG_LABELS } from '../../lib/labels'
import {
  CoreTimeDaysEditor,
  coreTimeDaysFromApi,
  coreTimeDaysValid,
  initialCoreTimeDays,
  type CoreTimeDay,
} from '../coreTime/CoreTimeDaysEditor'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

/** Rahmen einer Einstellungs-Karte mit Titel, Beschreibung und Rückmeldung. */
export function SettingsCard({
  title,
  description,
  children,
  message,
  error,
}: {
  title: string
  description?: ReactNode
  children?: ReactNode
  message?: string | null
  error?: string | null
}) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">{title}</p>
        {description && <p className="text-sm text-slate-500">{description}</p>}
      </div>
      {children}
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

/** Ein-/Aus-Schalter als eigene Karte (Checkbox mit Titel und Erklärung). */
export function SettingsToggle({
  checked,
  disabled,
  onChange,
  title,
  children,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
  title: string
  children?: ReactNode
}) {
  return (
    <label className="flex items-start gap-3 rounded-md border border-slate-200 bg-white p-4">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <span className="block text-sm font-medium text-slate-800">{title}</span>
        {children && <span className="block text-sm text-slate-500">{children}</span>}
      </span>
    </label>
  )
}

function useSettingsSave() {
  const update = useUpdateSettingsMutation()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function save(payload: Parameters<typeof update.mutateAsync>[0], ok = 'Gespeichert.') {
    setError(null)
    setMessage(null)
    try {
      await update.mutateAsync(payload)
      setMessage(ok)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Eingaben prüfen.')
    }
  }

  return { save, message, error, setError, pending: update.isPending }
}

/** Mandantenweite Standardwerte für neue Mitarbeiter (Formular und CSV-Import). */
export function EmployeeDefaultsCard({ settings }: { settings: Settings }) {
  const { save, message, error, setError } = useSettingsSave()
  const [dayHours, setDayHours] = useState<string[]>(Array(7).fill(''))

  useEffect(() => {
    setDayHours(
      (settings.default_day_minutes ?? Array(7).fill(0)).map((m: number) =>
        m > 0 ? String(m / 60).replace('.', ',') : '',
      ),
    )
  }, [settings.default_day_minutes])

  return (
    <SettingsCard
      title="Standardwerte für neue Mitarbeiter"
      description="Werden beim Anlegen (Formular und CSV-Import) vorbelegt und lassen sich je Mitarbeiter ändern."
      message={message}
      error={error}
    >
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.default_auto_break}
          onChange={(e) => void save({ default_auto_break: e.target.checked })}
        />
        Automatische Pausenregelung aktiv (gesetzliche Pause wird beim Ausstempeln gebucht, wenn keine gestempelt wurde)
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={settings.default_show_birthday}
          onChange={(e) => void save({ default_show_birthday: e.target.checked })}
        />
        Geburtstag im Kalender anzeigen
      </label>
      <div className="flex flex-col gap-1.5">
        <span className="text-sm">
          Standard-Arbeitszeitmodell (Stunden je Wochentag, leer = frei; alles leer = kein Standard)
        </span>
        <div className="flex flex-wrap items-end gap-2">
          {WEEKDAYS.map((label, day) => (
            <div key={label} className="flex w-12 flex-col items-center gap-0.5">
              <span className="text-xs text-slate-500">{label}</span>
              <Input
                inputMode="decimal"
                className="px-1 text-center"
                value={dayHours[day]}
                onChange={(e) => setDayHours((c) => c.map((v, i) => (i === day ? e.target.value : v)))}
              />
            </div>
          ))}
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              const minutes = dayHours.map((h) => (h.trim() ? Math.round(Number(h.replace(',', '.')) * 60) : 0))
              if (minutes.some((m) => !Number.isFinite(m))) return setError('Bitte nur Zahlen eintragen.')
              void save({
                default_day_minutes: minutes.some((m) => m > 0) ? minutes : [],
              })
            }}
          >
            Übernehmen
          </Button>
        </div>
      </div>
    </SettingsCard>
  )
}

/** Berechnungsregeln: Urlaub, "Zu klären"-Sonderfälle, Nachtschicht. */
export function RulesCard({ settings }: { settings: Settings }) {
  const { save, message, error } = useSettingsSave()
  const [span, setSpan] = useState(String(settings.max_shift_span_hours))

  useEffect(() => setSpan(String(settings.max_shift_span_hours)), [settings.max_shift_span_hours])

  const disabled = new Set(settings.disabled_day_flags)

  return (
    <SettingsCard title="Regeln" message={message} error={error}>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.prorate_part_time_vacation}
          onChange={(e) => void save({ prorate_part_time_vacation: e.target.checked })}
        />
        Urlaubsanspruch für Teilzeit anteilig berechnen (Vollzeit-Anspruch × Arbeitstage ÷ 5)
      </label>
      <div className="flex flex-col gap-1">
        <span className="text-sm">Diese Sonderfälle unter „Zu klären“ anzeigen:</span>
        <label className="flex items-center gap-2 pl-1 text-sm">
          <input
            type="checkbox"
            checked={settings.report_days_without_punches}
            onChange={(e) => void save({ report_days_without_punches: e.target.checked })}
          />
          Arbeitstage ganz ohne Stempelung („Stempelung fehlt“, auch im Monatsbericht und Lohn-Export)
        </label>
        {!settings.report_days_without_punches && (
          <p className="pl-6 text-sm text-slate-500">
            Nur unvollständig gestempelte Tage gelten als offen. Das Soll zählt trotzdem: Ein Arbeitstag ohne Stempelung
            geht ins Minus. Für Teilzeit ohne feste Tage passt das Arbeitszeitmodell „Flexibel ohne feste Tage“.
          </p>
        )}
        {Object.entries(DAY_FLAG_LABELS).map(([flag, label]) => (
          <label key={flag} className="flex items-center gap-2 pl-1 text-sm">
            <input
              type="checkbox"
              checked={!disabled.has(flag)}
              onChange={(e) => {
                const next = new Set(disabled)
                if (e.target.checked) next.delete(flag)
                else next.add(flag)
                void save({ disabled_day_flags: [...next] })
              }}
            />
            {label}
          </label>
        ))}
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-sm">
          Maximale Schichtlänge (Stunden): Ein „Gehen“ am Folgetag gehört bis dahin noch zur Schicht (Nachtschicht).
          Ist danach noch kein „Gehen“ gestempelt, gilt es als vergessen und der Tag erscheint unter „Zu klären“.
        </span>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={8}
            max={24}
            className="w-24"
            value={span}
            onChange={(e) => setSpan(e.target.value)}
          />
          <Button size="sm" variant="outline" onClick={() => void save({ max_shift_span_hours: Number(span) })}>
            Übernehmen
          </Button>
        </div>
      </div>
    </SettingsCard>
  )
}

/** RFID-Pflicht am Kiosk. */
export function RfidSettingsCard({ settings }: { settings: Settings }) {
  const { save, message, error, pending } = useSettingsSave()
  return (
    <div className="flex flex-col gap-2">
      <SettingsToggle
        checked={settings.kiosk_rfid_enabled}
        disabled={pending}
        onChange={(checked) => void save({ kiosk_rfid_enabled: checked })}
        title="Chips/RFID am Tablet nutzen"
      >
        Zeigt am Tablet die Leiste „Aktion wählen, dann Chip vorhalten“ (Terminalmodus) und öffnet einen Mitarbeiter
        direkt, wenn ohne gewählte Aktion ein Chip vorgehalten wird. Aus = Stempeln nur über die Kacheln; ein Chip
        ersetzt dann auch nicht mehr den PIN.
      </SettingsToggle>
      <SettingsToggle
        checked={settings.kiosk_card_self_registration}
        disabled={pending || !settings.kiosk_rfid_enabled}
        onChange={(checked) => void save({ kiosk_card_self_registration: checked })}
        title="Mitarbeiter registrieren ihren Chip selbst"
      >
        Am Tablet den eigenen Namen antippen, „Eigenen Chip registrieren“ wählen (bei RFID-Pflicht direkt), mit dem
        eigenen PIN bestätigen und den Chip vorhalten. Nur für Mitarbeiter mit PIN; ein vorhandener Chip wird ersetzt, jede Registrierung steht im
        Audit-Log.
      </SettingsToggle>
      <SettingsToggle
        checked={settings.rfid_required}
        disabled={pending || !settings.kiosk_rfid_enabled}
        onChange={(checked) => void save({ rfid_required: checked })}
        title="RFID-Pflicht"
      >
        Stempeln nur mit Chip/Karte. Am Tablet wird oben die Aktion gewählt (Kommen, Gehen, Pause …) und dann der Chip
        vorgehalten – mehrere Mitarbeiter können nacheinander scannen, nach 10 s ohne Scan ist keine Aktion mehr
        gewählt. Kacheln lösen dann keine Stempelung aus. Chips werden am Mitarbeiter unter „Karten-UID“ hinterlegt.
      </SettingsToggle>
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}

/** PIN zum Zurücksetzen eines Kiosk-Tablets. */
export function KioskAdminPinCard({ settings }: { settings: Settings }) {
  const { save, message, error } = useSettingsSave()
  const [pin, setPin] = useState('')
  return (
    <SettingsCard
      title="Kiosk-Admin-PIN"
      description={
        <>
          Wird am Tablet zum Zurücksetzen des Geräts abgefragt. Ohne PIN ist das Zurücksetzen am Tablet gesperrt.{' '}
          {settings.kiosk_admin_pin_set ? 'Eine PIN ist festgelegt.' : 'Noch keine PIN festgelegt.'}
        </>
      }
      message={message}
      error={error}
    >
      <div className="flex items-center gap-2">
        <Input
          type="password"
          inputMode="numeric"
          autoComplete="new-password"
          placeholder="4–8 Ziffern"
          className="w-36"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
        />
        <Button
          size="sm"
          disabled={pin.length < 4}
          onClick={() => void save({ kiosk_admin_pin: pin }, 'Kiosk-Admin-PIN gespeichert.').then(() => setPin(''))}
        >
          {settings.kiosk_admin_pin_set ? 'PIN ändern' : 'PIN festlegen'}
        </Button>
        {settings.kiosk_admin_pin_set && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void save({ kiosk_admin_pin: '' }, 'Kiosk-Admin-PIN entfernt.')}
          >
            Entfernen
          </Button>
        )}
      </div>
    </SettingsCard>
  )
}

/** Resturlaub automatisch übertragen, mit Obergrenze und Verfall zum Stichtag. */
export function VacationCarryOverCard({ settings }: { settings: Settings }) {
  const { save, message, error } = useSettingsSave()
  const [maxDays, setMaxDays] = useState(settings.vacation_carry_over_max_days?.toString() ?? '')
  const [expiry, setExpiry] = useState(toGermanDay(settings.vacation_carry_over_expiry))

  useEffect(() => {
    setMaxDays(settings.vacation_carry_over_max_days?.toString() ?? '')
    setExpiry(toGermanDay(settings.vacation_carry_over_expiry))
  }, [settings.vacation_carry_over_max_days, settings.vacation_carry_over_expiry])

  function saveLimits() {
    const parsedExpiry = fromGermanDay(expiry)
    if (parsedExpiry === undefined) return // Fehlermeldung steht schon an der Karte
    const max = maxDays.trim() ? Number(maxDays.replace(',', '.')) : null
    void save({
      ...(max === null ? { clear_vacation_carry_over_max_days: true } : { vacation_carry_over_max_days: max }),
      vacation_carry_over_expiry: parsedExpiry,
    })
  }

  return (
    <SettingsCard
      title="Urlaubsübertrag ins neue Jahr"
      description="Ohne automatischen Übertrag trägt HR den Resturlaub am Mitarbeiter ein. Ein dort eingetragener Wert hat immer Vorrang."
      message={message}
      error={error ?? (fromGermanDay(expiry) === undefined ? 'Verfallsdatum als TT.MM. eingeben, z. B. 31.03.' : null)}
    >
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.vacation_carry_over_auto}
          onChange={(e) => void save({ vacation_carry_over_auto: e.target.checked })}
        />
        Resturlaub automatisch ins Folgejahr übertragen
      </label>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Höchstens (Tage, leer = unbegrenzt)
          <Input className="w-28" inputMode="decimal" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Übertrag verfällt nach (TT.MM., leer = nie)
          <Input className="w-28" placeholder="31.03." value={expiry} onChange={(e) => setExpiry(e.target.value)} />
        </label>
        <Button size="sm" variant="outline" onClick={saveLimits}>
          Übernehmen
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Genommener Urlaub zählt zuerst gegen den Übertrag. Hinweis: Urlaub verfällt rechtlich nur, wenn der Mitarbeiter
        rechtzeitig auf den drohenden Verfall hingewiesen wurde (BAG) – HR3000 zeigt die verfallenden Tage im
        Urlaubskonto des Mitarbeiters an.
      </p>
    </SettingsCard>
  )
}

function toGermanDay(value: string | null | undefined): string {
  if (!value) return ''
  const [month, day] = value.split('-')
  return `${day}.${month}.`
}

/** "31.03." → "03-31", leer → "" (kein Verfall), ungültig → undefined. */
function fromGermanDay(value: string): string | undefined {
  const trimmed = value.trim()
  if (!trimmed) return ''
  const match = /^(\d{1,2})\.(\d{1,2})\.?$/.exec(trimmed)
  if (!match) return undefined
  const day = Number(match[1])
  const month = Number(match[2])
  if (month < 1 || month > 12 || day < 1 || day > 31) return undefined
  return `${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** Was das Tablet zeigt: Saldo/Resturlaub (Datenschutz), Pausen-Buttons, Text, Sortierung. */
export function KioskDisplayCard({ settings }: { settings: Settings }) {
  const { save, message, error } = useSettingsSave()
  const [greeting, setGreeting] = useState(settings.kiosk_greeting ?? '')
  // Bildschirmzeiten: aus = immer an (Standard); an = nur im Fenster von–bis (Standort-Zeitzone)
  const savedFrom = hhmm(settings.kiosk_screen_on_from)
  const savedUntil = hhmm(settings.kiosk_screen_on_until)
  const [screenLimited, setScreenLimited] = useState(Boolean(savedFrom))
  const [screenFrom, setScreenFrom] = useState(savedFrom || '06:00')
  const [screenUntil, setScreenUntil] = useState(savedUntil || '21:00')

  useEffect(() => setGreeting(settings.kiosk_greeting ?? ''), [settings.kiosk_greeting])
  useEffect(() => {
    setScreenLimited(Boolean(savedFrom))
    if (savedFrom) setScreenFrom(savedFrom)
    if (savedUntil) setScreenUntil(savedUntil)
  }, [savedFrom, savedUntil])

  return (
    <SettingsCard
      title="Anzeige am Tablet"
      description="Änderungen erreichen die Tablets innerhalb von etwa 30 Sekunden."
      message={message}
      error={error}
    >
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.kiosk_show_balance}
          onChange={(e) => void save({ kiosk_show_balance: e.target.checked })}
        />
        Gleitzeitsaldo nach dem Stempeln anzeigen
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.kiosk_show_vacation}
          onChange={(e) => void save({ kiosk_show_vacation: e.target.checked })}
        />
        Resturlaub anzeigen
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.kiosk_break_buttons}
          onChange={(e) => void save({ kiosk_break_buttons: e.target.checked })}
        />
        Pausen-Buttons anzeigen (aus = Pausen nur über die automatische Pausenregelung)
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.kiosk_errand_buttons}
          onChange={(e) => void save({ kiosk_errand_buttons: e.target.checked })}
        />
        Dienstgang-Buttons anzeigen (Zeit auf Dienstgang zählt voll als Arbeitszeit)
      </label>
      <div className="flex flex-col gap-1 text-sm">
        Darstellung am Tablet
        <div className="flex gap-2">
          {(['DARK', 'LIGHT'] as const).map((theme) => (
            <Button
              key={theme}
              size="sm"
              variant={settings.kiosk_theme === theme ? 'default' : 'outline'}
              onClick={() => void save({ kiosk_theme: theme })}
            >
              {theme === 'DARK' ? 'Dunkel' : 'Hell'}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={screenLimited}
            onChange={(e) => {
              setScreenLimited(e.target.checked)
              if (!e.target.checked && savedFrom) void save({ clear_kiosk_screen_hours: true })
            }}
          />
          <span>
            Bildschirm nur zu bestimmten Zeiten anlassen
            <span className="block text-xs text-slate-500">
              Außerhalb dieser Zeit geht der Bildschirm nach dem Geräte-Timeout aus. Morgens per Ein/Aus-Taste wecken.
              Es gilt die Zeitzone des Standorts; „bis“ vor „von“ = über Mitternacht. Je Tablet abweichend einstellbar.
            </span>
          </span>
        </label>
        {screenLimited && (
          <div className="flex flex-wrap items-center gap-2 pl-6">
            <Input
              type="time"
              aria-label="Bildschirm an von"
              className="w-28"
              value={screenFrom}
              onChange={(e) => setScreenFrom(e.target.value)}
            />
            <span className="text-slate-500">bis</span>
            <Input
              type="time"
              aria-label="Bildschirm an bis"
              className="w-28"
              value={screenUntil}
              onChange={(e) => setScreenUntil(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              aria-label="Bildschirmzeiten übernehmen"
              disabled={!screenFrom || !screenUntil || screenFrom === screenUntil}
              onClick={() => void save({ kiosk_screen_on_from: screenFrom, kiosk_screen_on_until: screenUntil })}
            >
              Übernehmen
            </Button>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-1 text-sm">
        Sortierung der Kacheln
        <div className="flex gap-2">
          {(['LAST_NAME', 'FIRST_NAME'] as const).map((sort) => (
            <Button
              key={sort}
              size="sm"
              variant={settings.kiosk_sort === sort ? 'default' : 'outline'}
              onClick={() => void save({ kiosk_sort: sort })}
            >
              {sort === 'LAST_NAME' ? 'Nachname' : 'Vorname'}
            </Button>
          ))}
        </div>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Hinweistext über den Kacheln (optional)
        <div className="flex gap-2">
          <Input
            maxLength={120}
            placeholder="z. B. Bitte beim Gehen ausstempeln"
            value={greeting}
            onChange={(e) => setGreeting(e.target.value)}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={greeting === (settings.kiosk_greeting ?? '')}
            onClick={() => void save({ kiosk_greeting: greeting })}
          >
            Übernehmen
          </Button>
        </div>
      </label>
    </SettingsCard>
  )
}

const hhmm = (value: string | null | undefined) => (value ? value.slice(0, 5) : '')

/** Von–bis-Uhrzeit mit "Übernehmen" und "Entfernen". */
function TimeRangeField({
  label,
  start,
  end,
  onSave,
  onClear,
  clearLabel,
}: {
  label: string
  start: string | null | undefined
  end: string | null | undefined
  onSave: (start: string, end: string) => void
  onClear: () => void
  clearLabel: string
}) {
  const [from, setFrom] = useState(hhmm(start))
  const [to, setTo] = useState(hhmm(end))
  useEffect(() => {
    setFrom(hhmm(start))
    setTo(hhmm(end))
  }, [start, end])
  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm">{label}</span>
      <div className="flex flex-wrap items-center gap-2">
        <Input type="time" aria-label={`${label} von`} className="w-28" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="text-sm text-slate-500">bis</span>
        <Input type="time" aria-label={`${label} bis`} className="w-28" value={to} onChange={(e) => setTo(e.target.value)} />
        <Button size="sm" variant="outline" disabled={!from || !to} onClick={() => onSave(from, to)}>
          Übernehmen
        </Button>
        {start && (
          <Button size="sm" variant="ghost" onClick={onClear}>
            {clearLabel}
          </Button>
        )}
      </div>
    </div>
  )
}

/** Kernzeit je Wochentag: an = eigene Zeiten je Tag (z. B. freitags kürzer), aus = jeden Tag dieselbe. */
function CoreTimeByWeekday({
  settings,
  save,
}: {
  settings: Settings
  save: ReturnType<typeof useSettingsSave>['save']
}) {
  const saved = coreTimeDaysFromApi(settings.core_time_days)
  const [days, setDays] = useState<CoreTimeDay[] | null>(saved)
  const savedKey = JSON.stringify(saved)
  useEffect(() => setDays(coreTimeDaysFromApi(settings.core_time_days)), [savedKey]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={days !== null}
          onChange={(e) => {
            if (e.target.checked) {
              setDays(initialCoreTimeDays(hhmm(settings.core_time_start), hhmm(settings.core_time_end)))
            } else {
              setDays(null)
              if (saved) void save({ core_time_days: null })
            }
          }}
        />
        Kernzeit je Wochentag unterschiedlich (z. B. freitags kürzer)
      </label>
      {days && (
        <>
          <CoreTimeDaysEditor days={days} onChange={setDays} />
          <div>
            <Button
              size="sm"
              variant="outline"
              disabled={!coreTimeDaysValid(days) || JSON.stringify(days) === savedKey}
              onClick={() => void save({ core_time_days: days })}
            >
              Kernzeiten übernehmen
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

/** Kernarbeitszeit, Pünktlichkeit und Gleitzeit-Rahmen – alles optional, Standard aus. */
export function CoreTimeCard({ settings }: { settings: Settings }) {
  const { save, message, error } = useSettingsSave()
  const [tolerance, setTolerance] = useState(String(settings.late_tolerance_minutes))
  useEffect(() => setTolerance(String(settings.late_tolerance_minutes)), [settings.late_tolerance_minutes])

  return (
    <SettingsCard
      title="Kernarbeitszeit & Gleitzeit"
      description="Optional. Auffälligkeiten erscheinen als Sonderfall unter „Zu klären“ (oben einzeln abschaltbar); an den Stunden ändert sich nichts. Je Mitarbeiter abweichend einstellbar (Mitarbeiter → Bearbeiten)."
      message={message}
      error={error}
    >
      <TimeRangeField
        label="Kernzeit"
        start={settings.core_time_start}
        end={settings.core_time_end}
        onSave={(start, end) => void save({ core_time_start: start, core_time_end: end })}
        onClear={() => void save({ clear_core_time: true })}
        clearLabel="Keine Kernzeit"
      />
      <CoreTimeByWeekday settings={settings} save={save} />
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={settings.punctuality_check}
          onChange={(e) => void save({ punctuality_check: e.target.checked })}
        />
        <span>
          Pünktlichkeit prüfen: zu spät kommen bzw. zu früh gehen unter „Zu klären“ melden
          <span className="block text-xs text-slate-500">
            Maßstab ist die geplante Schicht (Schichtplanung mit Uhrzeiten), sonst die Kernzeit.
          </span>
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>Toleranz</span>
        <Input
          type="number"
          min={0}
          max={120}
          aria-label="Toleranz in Minuten"
          className="w-20"
          value={tolerance}
          onChange={(e) => setTolerance(e.target.value)}
        />
        <span className="text-slate-500">Minuten</span>
        <Button
          size="sm"
          variant="outline"
          disabled={tolerance === String(settings.late_tolerance_minutes)}
          onClick={() => void save({ late_tolerance_minutes: Number(tolerance) })}
        >
          Übernehmen
        </Button>
      </div>
      <TimeRangeField
        label="Gleitzeit-Rahmen (frühestes Kommen – spätestes Gehen)"
        start={settings.flex_frame_start}
        end={settings.flex_frame_end}
        onSave={(start, end) => void save({ flex_frame_start: start, flex_frame_end: end })}
        onClear={() => void save({ clear_flex_frame: true })}
        clearLabel="Kein Rahmen"
      />
    </SettingsCard>
  )
}
