import { useEffect, useState, type FormEvent } from 'react'
import {
  useCreateEmployeeMutation,
  useResetEmployeePasswordMutation,
  useUpdateEmployeeHrRoleMutation,
  useUpdateEmployeeMutation,
  type Employee,
  type HrRole,
} from '../../api/queries/employees'
import type { Location } from '../../api/queries/locations'
import { useTeamsQuery } from '../../api/queries/teams'
import { todayIsoDate } from '../../lib/format'
import { ApiError } from '../../api/client'
import { ResetPasswordDialog } from '../shared/ResetPasswordDialog'
import { OneTimeCredentialsDialog } from '../tenants/OneTimeCredentialsDialog'
import { useAuth } from '../../auth/AuthContext'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { useFeaturesQuery } from '../../api/queries/workTimeModel'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface EmployeeFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employee?: Employee
  locations: Location[]
}

const NO_HR_ROLE = 'NONE'
const NO_TEAM = '__none__'

export function EmployeeFormDialog({
  open,
  onOpenChange,
  employee,
  locations,
}: EmployeeFormDialogProps) {
  const isEditMode = employee !== undefined
  const features = useFeaturesQuery().data
  const { isAdmin } = useAuth()
  const createEmployee = useCreateEmployeeMutation()
  const updateEmployee = useUpdateEmployeeMutation()
  const updateHrRole = useUpdateEmployeeHrRoleMutation()
  const resetPassword = useResetEmployeePasswordMutation()
  const [resetOpen, setResetOpen] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetNotice, setResetNotice] = useState<string | null>(null)
  const [credentials, setCredentials] = useState<{ password: string } | null>(null)
  const teamsQuery = useTeamsQuery()
  const teams = teamsQuery.data ?? []

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [employeeNumber, setEmployeeNumber] = useState('')
  const [locationId, setLocationId] = useState<string>('')
  const [locationValidFrom, setLocationValidFrom] = useState(todayIsoDate())
  // Nur beim Anlegen: optionales Arbeitszeitmodell (gilt ab Eintritt bzw. heute).
  const [modelDailyHours, setModelDailyHours] = useState<string[]>(['', '', '', '', '', '', ''])
  const [teamId, setTeamId] = useState<string>(NO_TEAM)
  const [active, setActive] = useState(true)
  const [loginEmail, setLoginEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  const [resetPin, setResetPin] = useState(false)
  const [nfcUid, setNfcUid] = useState('')
  const [hireDate, setHireDate] = useState('')
  const [terminationDate, setTerminationDate] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [showBirthdayInCalendar, setShowBirthdayInCalendar] = useState(true)
  const [autoBreakEnabled, setAutoBreakEnabled] = useState(true)
  const [coreTimeMode, setCoreTimeMode] = useState<'TENANT' | 'CUSTOM' | 'NONE'>('TENANT')
  const [coreStart, setCoreStart] = useState('')
  const [coreEnd, setCoreEnd] = useState('')
  const [hrRole, setHrRole] = useState<string>(NO_HR_ROLE)
  const [error, setError] = useState<string | null>(null)
  const [hrRoleError, setHrRoleError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setFirstName(employee?.first_name ?? '')
    setLastName(employee?.last_name ?? '')
    setEmployeeNumber(employee?.employee_number ?? '')
    setLocationId(employee ? String(employee.location_id) : locations[0] ? String(locations[0].id) : '')
    setLocationValidFrom(todayIsoDate())
    // Neuer Mitarbeiter: Standard-Arbeitszeitmodell des Mandanten vorbelegen (Einstellungen).
    setModelDailyHours(
      (features?.default_day_minutes ?? Array(7).fill(0)).map((m: number) => (m > 0 ? String(m / 60).replace('.', ',') : '')),
    )
    setTeamId(employee?.team_id ? String(employee.team_id) : NO_TEAM)
    setActive(employee?.active ?? true)
    setLoginEmail(employee?.login_email ?? '')
    setPassword('')
    setPin('')
    setResetPin(false)
    setNfcUid(employee?.nfc_uid ?? '')
    setHireDate(employee?.hire_date ?? '')
    setTerminationDate(employee?.termination_date ?? '')
    setBirthDate(employee?.birth_date ?? '')
    setShowBirthdayInCalendar(employee?.show_birthday_in_calendar ?? features?.default_show_birthday ?? true)
    setAutoBreakEnabled(employee?.auto_break_enabled ?? features?.default_auto_break ?? true)
    setCoreTimeMode((employee?.core_time_mode as 'TENANT' | 'CUSTOM' | 'NONE' | undefined) ?? 'TENANT')
    setCoreStart(employee?.core_time_start?.slice(0, 5) ?? '')
    setCoreEnd(employee?.core_time_end?.slice(0, 5) ?? '')
    setHrRole(employee?.hr_role ?? NO_HR_ROLE)
    setError(null)
    setHrRoleError(null)
    setResetNotice(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, employee?.id])  // bewusst nicht an das employee-Objekt gebunden: ein Refetch (z.B. nach Rollenwechsel) darf ungespeicherte Eingaben nicht verwerfen

  const locationChanged = isEditMode && locationId !== '' && Number(locationId) !== employee.location_id

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const payload = {
      location_id: Number(locationId),
      first_name: firstName,
      last_name: lastName,
      employee_number: employeeNumber,
      active,
      login_email: loginEmail || undefined,
      auto_break_enabled: autoBreakEnabled,
      core_time_mode: coreTimeMode,
      ...(coreTimeMode === 'CUSTOM' ? { core_time_start: coreStart, core_time_end: coreEnd } : {}),
      // Leerer String entfernt die Karte beim Bearbeiten (None hieße "unverändert").
      nfc_uid: nfcUid.trim(),
      hire_date: hireDate || undefined,
      termination_date: terminationDate || undefined,
      clear_hire_date: hireDate === '',
      clear_termination_date: terminationDate === '',
      birth_date: birthDate || undefined,
      clear_birth_date: birthDate === '',
      show_birthday_in_calendar: showBirthdayInCalendar,
      team_id: teamId === NO_TEAM ? undefined : Number(teamId),
      clear_team_id: teamId === NO_TEAM,
      ...(password ? { password } : {}),
      ...(pin ? { pin } : resetPin ? { pin: '' } : {}),
      ...(isEditMode && locationChanged ? { location_valid_from: locationValidFrom } : {}),
      ...(!isEditMode && modelDailyHours.some((h) => h.trim())
        ? { work_time_model: { daily_hours: modelDailyHours.map((h) => (h.trim() ? Number(h.replace(',', '.')) : 0)), flexible: false, on_demand: false } }
        : {}),
    }

    try {
      if (isEditMode) {
        await updateEmployee.mutateAsync({ employeeId: employee.id, payload })
      } else {
        await createEmployee.mutateAsync(payload)
      }
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMPLOYEE_NUMBER_TAKEN') {
        setError('Diese Personalnummer wird bereits verwendet.')
      } else if (err instanceof ApiError && err.code === 'LOGIN_EMAIL_TAKEN') {
        setError('Diese Login-E-Mail wird bereits verwendet.')
      } else if (err instanceof ApiError && err.code === 'NFC_UID_TAKEN') {
        setError('Diese NFC-Karte ist bereits einem anderen Mitarbeiter zugeordnet.')
      } else if (err instanceof ApiError && err.status !== 422) {
        setError(err.message)
      } else {
        setError('Speichern fehlgeschlagen.')
      }
    }
  }

  async function handleHrRoleChange(value: string) {
    if (!isEditMode) return
    setHrRoleError(null)
    const previous = hrRole
    setHrRole(value)
    try {
      await updateHrRole.mutateAsync({
        employeeId: employee.id,
        hrRole: value === NO_HR_ROLE ? null : (value as HrRole),
      })
    } catch (err) {
      setHrRole(previous)
      setHrRoleError(
        err instanceof ApiError && err.code === 'LAST_ADMIN'
          ? err.message
          : 'Berechtigung konnte nicht geändert werden.',
      )
    }
  }

  async function handleResetPassword(sendEmail: boolean) {
    if (!employee) return
    setResetError(null)
    try {
      const result = await resetPassword.mutateAsync({ employeeId: employee.id, sendEmail })
      setResetOpen(false)
      if (result.new_password) {
        setCredentials({ password: result.new_password })
      } else {
        setResetNotice(`Neues Passwort wurde per E-Mail an ${employee.login_email} gesendet.`)
      }
    } catch (err) {
      setResetError(
        err instanceof ApiError &&
          ['EMAIL_NOT_CONFIGURED', 'EMAIL_SEND_FAILED', 'NO_LOGIN', 'ALREADY_ANONYMIZED'].includes(err.code ?? '')
          ? err.message
          : 'Zurücksetzen fehlgeschlagen.',
      )
    }
  }

  const isSubmitting = createEmployee.isPending || updateEmployee.isPending

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}</DialogTitle>
        </DialogHeader>
        <form className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="first_name">Vorname</Label>
              <Input
                id="first_name"
                required
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="last_name">Nachname</Label>
              <Input
                id="last_name"
                required
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="employee_number">Personalnummer</Label>
            <Input
              id="employee_number"
              required
              value={employeeNumber}
              onChange={(event) => setEmployeeNumber(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Standort</Label>
            <Select value={locationId} onValueChange={setLocationId}>
              <SelectTrigger>
                <SelectValue placeholder="Standort wählen" />
              </SelectTrigger>
              <SelectContent>
                {locations.map((location) => (
                  <SelectItem key={location.id} value={String(location.id)}>
                    {location.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {locationChanged && (
            <div className="flex flex-col gap-1.5 rounded-md bg-amber-50 p-3">
              <Label htmlFor="location_valid_from">Standortwechsel gilt ab</Label>
              <Input id="location_valid_from" type="date" value={locationValidFrom} onChange={(e) => e.target.value && setLocationValidFrom(e.target.value)} />
              <p className="text-xs text-amber-800">Davor gelten weiter die Feiertage des bisherigen Standorts.</p>
            </div>
          )}
          {!isEditMode && (
            <div className="flex flex-col gap-1.5 rounded-md border border-slate-200 p-3">
              <Label>Arbeitszeitmodell (optional): Stunden je Wochentag</Label>
              <div className="grid grid-cols-7 gap-1">
                {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((label, day) => (
                  <div key={label} className="flex flex-col items-center gap-0.5">
                    <span className="text-xs text-slate-500">{label}</span>
                    <Input
                      inputMode="decimal"
                      className="w-full px-1 text-center"
                      value={modelDailyHours[day]}
                      onChange={(e) => setModelDailyHours((c) => c.map((v, i) => (i === day ? e.target.value : v)))}
                    />
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-500">
                Z. B. Vollzeit 8 an Mo–Fr, Teilzeit Mo 8 / Di 8 / Mi 4. Gilt ab Eintrittsdatum (sonst ab heute); später im
                Reiter „Arbeitszeitmodell“ änderbar.
              </p>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label>Team</Label>
            <Select value={teamId} onValueChange={setTeamId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_TEAM}>Kein Team</SelectItem>
                {teams.map((team) => (
                  <SelectItem key={team.id} value={String(team.id)}>
                    {team.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-500">
              Bestimmt, welche Teamleader diesen Mitarbeiter sehen dürfen (siehe Seite „Teams“).
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Aktiv
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="hire_date">Eintrittsdatum</Label>
              <Input
                id="hire_date"
                type="date"
                value={hireDate}
                onChange={(event) => setHireDate(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="termination_date">Austrittsdatum</Label>
              <Input
                id="termination_date"
                type="date"
                value={terminationDate}
                onChange={(event) => setTerminationDate(event.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="birth_date">Geburtsdatum</Label>
            <Input
              id="birth_date"
              type="date"
              value={birthDate}
              onChange={(event) => setBirthDate(event.target.value)}
            />
          </div>
          {birthDate && (
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={showBirthdayInCalendar}
                onChange={(event) => setShowBirthdayInCalendar(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              Geburtstag im Kalender anzeigen
            </label>
          )}
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={autoBreakEnabled}
              onChange={(event) => setAutoBreakEnabled(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Pausen automatisch stempeln (nach Pausenregeln)
          </label>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="core_time_mode">Kernarbeitszeit / Pünktlichkeit</Label>
            <select
              id="core_time_mode"
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
              value={coreTimeMode}
              onChange={(event) => setCoreTimeMode(event.target.value as 'TENANT' | 'CUSTOM' | 'NONE')}
            >
              <option value="TENANT">Wie in den Einstellungen</option>
              <option value="CUSTOM">Eigene Kernzeit</option>
              <option value="NONE">Keine Prüfung (z. B. Außendienst)</option>
            </select>
            {coreTimeMode === 'CUSTOM' && (
              <div className="flex items-center gap-2">
                <Input
                  type="time"
                  aria-label="Eigene Kernzeit von"
                  required
                  className="w-28"
                  value={coreStart}
                  onChange={(event) => setCoreStart(event.target.value)}
                />
                <span className="text-sm text-slate-500">bis</span>
                <Input
                  type="time"
                  aria-label="Eigene Kernzeit bis"
                  required
                  className="w-28"
                  value={coreEnd}
                  onChange={(event) => setCoreEnd(event.target.value)}
                />
              </div>
            )}
          </div>
          </div>

          <div className="flex flex-col gap-4">
          <div className="rounded-md border border-slate-200 p-3">
            <p className="mb-3 text-sm font-medium text-slate-700">Login (Mein Bereich)</p>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login_email">Login-E-Mail</Label>
                <Input
                  id="login_email"
                  type="email"
                  placeholder="z.B. vorname.nachname@firma.de"
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">
                  {isEditMode ? 'Neues Passwort (optional)' : 'Passwort (optional)'}
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder={isEditMode ? 'Leer lassen, um Passwort nicht zu ändern' : ''}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
              {isEditMode && isAdmin && employee?.login_email && (
                <div className="flex flex-col gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="self-start"
                    onClick={() => {
                      setResetError(null)
                      setResetOpen(true)
                    }}
                  >
                    Neues Passwort erzeugen …
                  </Button>
                  <p className="text-xs text-slate-500">
                    Erzeugt ein Einmalpasswort und sendet es per E-Mail oder zeigt es einmalig an.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-md border border-slate-200 p-3">
            <p className="mb-3 text-sm font-medium text-slate-700">Stempel-PIN (Tablet)</p>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pin">
                {isEditMode ? 'Neuer PIN (optional)' : 'PIN (optional)'}
              </Label>
              <Input
                id="pin"
                type="text"
                inputMode="numeric"
                placeholder={
                  isEditMode
                    ? employee?.has_pin
                      ? 'PIN hinterlegt – leer lassen, um ihn nicht zu ändern'
                      : 'Kein PIN hinterlegt'
                    : ''
                }
                value={pin}
                onChange={(event) => setPin(event.target.value)}
              />
              <p className="text-xs text-slate-500">
                Wird beim Stempeln am Tablet abgefragt, sofern in den Einstellungen aktiviert. Ohne PIN legt der Mitarbeiter
                ihn beim ersten Stempeln am Tablet selbst fest (wenn unter Einstellungen → Kiosk erlaubt).
              </p>
              {isEditMode && employee?.has_pin && !pin && (
                <label className="mt-1 flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-slate-300"
                    checked={resetPin}
                    onChange={(event) => setResetPin(event.target.checked)}
                  />
                  PIN zurücksetzen (vergessen) – der Mitarbeiter legt beim nächsten Stempeln am Tablet einen neuen fest
                </label>
              )}
            </div>
          </div>

          <div className="rounded-md border border-slate-200 p-3">
            <p className="mb-3 text-sm font-medium text-slate-700">NFC-Karte (Tablet)</p>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nfc_uid">Karten-UID (optional)</Label>
              <Input
                id="nfc_uid"
                type="text"
                placeholder="Hier klicken und Chip an den USB-Leser halten – oder UID eintippen"
                value={nfcUid}
                onChange={(event) => setNfcUid(event.target.value)}
              />
              <p className="text-xs text-slate-500">
                Chip/Karte des Mitarbeiters: am Tablet direkt erkannt (ersetzt den PIN, bei RFID-Pflicht notwendig).
                Unbekannte Chips zeigt das Tablet mit ihrer UID an. Feld leeren, um die Karte zu entfernen.
              </p>
            </div>
          </div>

          {isEditMode && isAdmin && (
            <div className="flex flex-col gap-1.5">
              <Label>HR-Berechtigung</Label>
              <Select value={hrRole} onValueChange={handleHrRoleChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_HR_ROLE}>Keine (nur Mein Bereich)</SelectItem>
                  <SelectItem value="HR">HR</SelectItem>
                  <SelectItem value="SUPERVISOR">Teamleader</SelectItem>
                  <SelectItem value="ADMIN">Admin</SelectItem>
                </SelectContent>
              </Select>
              {hrRoleError && <p className="text-sm text-red-600">{hrRoleError}</p>}
            </div>
          )}
          </div>

          {resetNotice && <p className="text-sm text-emerald-600 md:col-span-2">{resetNotice}</p>}
          {error && <p className="text-sm text-red-600 md:col-span-2">{error}</p>}
          <DialogFooter className="md:col-span-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={isSubmitting || !locationId}>
              {isSubmitting ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <ResetPasswordDialog
      open={resetOpen}
      onOpenChange={setResetOpen}
      title="Passwort zurücksetzen"
      description="Der Mitarbeiter bekommt ein neues Einmalpasswort, das bisherige Passwort wird ungültig."
      recipient={employee?.login_email ?? ''}
      pending={resetPassword.isPending}
      error={resetError}
      onConfirm={handleResetPassword}
    />
    <OneTimeCredentialsDialog
      open={credentials !== null}
      onOpenChange={(next) => !next && setCredentials(null)}
      title="Neues Passwort"
      email={employee?.login_email ?? ''}
      password={credentials?.password ?? ''}
      notice={null}
    />
    </>
  )
}
