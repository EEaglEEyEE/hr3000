import { useEffect, useState, type FormEvent } from 'react'
import {
  useEmployeesQuery,
  useCreateEmployeeMutation,
  useResetEmployeePasswordMutation,
  useResetEmployeeTwoFactorMutation,
  useUpdateEmployeeHrRoleMutation,
  useUpdateEmployeeMutation,
  type Employee,
  type HrRole,
} from '../../api/queries/employees'
import type { Location } from '../../api/queries/locations'
import { departmentTree, useDepartmentsQuery } from '../../api/queries/departments'
import { automaticSupervisorText } from '../../lib/departments'
import { todayIsoDate } from '../../lib/format'
import { ApiError } from '../../api/client'
import { ResetPasswordDialog } from '../shared/ResetPasswordDialog'
import { OneTimeCredentialsDialog } from '../tenants/OneTimeCredentialsDialog'
import { useAuth } from '../../auth/AuthContext'
import { Button } from '../ui/button'
import { randomCardUid } from '../../lib/cardUid'
import { CardQrCode } from './CardQrCode'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { useFeaturesQuery } from '../../api/queries/workTimeModel'
import { useWorkTimeProfilesQuery } from '../../api/queries/workTimeProfiles'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface EmployeeFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  locations: Location[]
}

interface EmployeeFormProps {
  /** Ohne: Neuanlage. */
  employee?: Employee
  locations: Location[]
  /** Im Dialog: nach dem Speichern bzw. bei „Abbrechen“ schließen. Ohne: Formular bleibt stehen (Reiter „Einstellungen“). */
  onDone?: () => void
}

/** Radix-Select meldet beim Vorbelegen per Effekt kurz "" zurück, solange seine Optionen noch nicht
 * registriert sind – das darf weder ein Feld leeren noch (HR-Berechtigung) sofort speichern. */
function ifChosen(apply: (value: string) => void) {
  return (value: string) => {
    if (value) apply(value)
  }
}

const NO_HR_ROLE = 'NONE'
const NONE = '__none__'

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

/** Arbeitszeitmodell beim Anlegen: Standard der Firma, Stunden je Wochentag, nach Aufwand oder keins. */
// PROFILE-<id> = Arbeitszeitmodell zuweisen (folgt dessen Änderungen)
type ModelChoice = 'DEFAULT' | 'DAYS' | 'ON_DEMAND' | 'NONE' | `PROFILE-${number}`

/** Kurzform des Standardmodells, z. B. "Mo–Fr 8 Std." bzw. "Mo 8, Di 8, Mi 4 Std.". */
function modelSummary(minutes: number[] | null | undefined): string | null {
  if (!minutes?.some((m) => m > 0)) return null
  const days = minutes.map((m, day) => ({ day, hours: m / 60 })).filter((d) => d.hours > 0)
  const fmt = (h: number) => String(h).replace('.', ',')
  const consecutive = days.every((d, i) => i === 0 || d.day === days[i - 1].day + 1)
  if (consecutive && days.every((d) => d.hours === days[0].hours)) {
    const range = days.length > 1 ? `${WEEKDAY_LABELS[days[0].day]}–${WEEKDAY_LABELS[days.at(-1)!.day]}` : WEEKDAY_LABELS[days[0].day]
    return `${range} ${fmt(days[0].hours)} Std.`
  }
  return `${days.map((d) => `${WEEKDAY_LABELS[d.day]} ${fmt(d.hours)}`).join(', ')} Std.`
}

/** „Neuer Mitarbeiter“; bearbeitet wird im Reiter „Einstellungen“ der Detailseite. */
export function EmployeeFormDialog({ open, onOpenChange, locations }: EmployeeFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Neuer Mitarbeiter</DialogTitle>
        </DialogHeader>
        {open && <EmployeeForm locations={locations} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

/** Stammdaten, Zuordnung, Login/PIN/Chip und HR-Berechtigung eines Mitarbeiters (Anlegen im Dialog, Bearbeiten im Reiter). */
export function EmployeeForm({ employee, locations, onDone }: EmployeeFormProps) {
  const isEditMode = employee !== undefined
  const features = useFeaturesQuery().data
  const { isAdmin } = useAuth()
  const createEmployee = useCreateEmployeeMutation()
  const updateEmployee = useUpdateEmployeeMutation()
  const updateHrRole = useUpdateEmployeeHrRoleMutation()
  const resetPassword = useResetEmployeePasswordMutation()
  const resetTwoFactor = useResetEmployeeTwoFactorMutation()
  const [resetOpen, setResetOpen] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetNotice, setResetNotice] = useState<string | null>(null)
  const [credentials, setCredentials] = useState<{ password: string } | null>(null)
  const departmentList = useDepartmentsQuery().data ?? []
  const departments = departmentTree(departmentList)
  const colleagues = (useEmployeesQuery({ active: true }).data ?? []).filter((e) => e.id !== employee?.id)

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [employeeNumber, setEmployeeNumber] = useState('')
  // Schon beim ersten Rendern vorbelegen (siehe ifChosen).
  const [locationId, setLocationId] = useState<string>(() =>
    employee ? String(employee.location_id) : locations[0] ? String(locations[0].id) : '',
  )
  const [locationValidFrom, setLocationValidFrom] = useState(todayIsoDate())
  // Nur beim Anlegen: optionales Arbeitszeitmodell (gilt ab Eintritt bzw. heute).
  const [modelDailyHours, setModelDailyHours] = useState<string[]>(['', '', '', '', '', '', ''])
  const [modelChoice, setModelChoice] = useState<ModelChoice>('NONE')
  const [modelTouched, setModelTouched] = useState(false)
  const [departmentId, setDepartmentId] = useState<string>(NONE)
  const [supervisorId, setSupervisorId] = useState<string>(NONE)
  const [position, setPosition] = useState('')
  const [active, setActive] = useState(true)
  const [loginEmail, setLoginEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  const [resetPin, setResetPin] = useState(false)
  const [nfcUid, setNfcUid] = useState('')
  const [showQr, setShowQr] = useState(false)
  const [hireDate, setHireDate] = useState('')
  const [terminationDate, setTerminationDate] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [showBirthdayInCalendar, setShowBirthdayInCalendar] = useState(true)
  const [autoBreakEnabled, setAutoBreakEnabled] = useState(true)
  const [hrRole, setHrRole] = useState<string>(NO_HR_ROLE)
  const [payrollAccess, setPayrollAccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  // „Änderungen verwerfen“ im Reiter: Formular neu aus den gespeicherten Daten füllen.
  const [resetKey, setResetKey] = useState(0)
  const [hrRoleError, setHrRoleError] = useState<string | null>(null)

  useEffect(() => {
    setFirstName(employee?.first_name ?? '')
    setLastName(employee?.last_name ?? '')
    setEmployeeNumber(employee?.employee_number ?? '')
    setLocationId(employee ? String(employee.location_id) : locations[0] ? String(locations[0].id) : '')
    setLocationValidFrom(todayIsoDate())
    // Neuer Mitarbeiter: Standard-Arbeitszeitmodell des Mandanten vorbelegen (Einstellungen).
    setModelDailyHours(
      (features?.default_day_minutes ?? Array(7).fill(0)).map((m: number) => (m > 0 ? String(m / 60).replace('.', ',') : '')),
    )
    setModelChoice(modelSummary(features?.default_day_minutes) ? 'DEFAULT' : 'NONE')
    setModelTouched(false)
    setDepartmentId(employee?.department_id ? String(employee.department_id) : NONE)
    setSupervisorId(employee?.supervisor_id ? String(employee.supervisor_id) : NONE)
    setPosition(employee?.position ?? '')
    setActive(employee?.active ?? true)
    setLoginEmail(employee?.login_email ?? '')
    setPassword('')
    setPin('')
    setResetPin(false)
    setNfcUid(employee?.nfc_uid ?? '')
    setShowQr(false)
    setHireDate(employee?.hire_date ?? '')
    setTerminationDate(employee?.termination_date ?? '')
    setBirthDate(employee?.birth_date ?? '')
    setShowBirthdayInCalendar(employee?.show_birthday_in_calendar ?? features?.default_show_birthday ?? true)
    setAutoBreakEnabled(employee?.auto_break_enabled ?? features?.default_auto_break ?? true)
    setHrRole(employee?.hr_role ?? NO_HR_ROLE)
    setPayrollAccess(employee?.hr_payroll_access ?? false)
    setError(null)
    setSaved(false)
    setHrRoleError(null)
    setResetNotice(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, employee?.id])  // bewusst nicht an das employee-Objekt gebunden: ein Refetch (z.B. nach Rollenwechsel) darf ungespeicherte Eingaben nicht verwerfen

  const locationChanged = isEditMode && locationId !== '' && Number(locationId) !== employee.location_id
  const defaultModel = modelSummary(features?.default_day_minutes)
  const profiles = useWorkTimeProfilesQuery({ enabled: !isEditMode }).data ?? []

  // Die Firmen-Standards kommen evtl. erst nach dem Öffnen an – dann vorbelegen, solange nichts gewählt ist.
  useEffect(() => {
    if (isEditMode || modelTouched) return
    setModelChoice(defaultModel ? 'DEFAULT' : 'NONE')
    setModelDailyHours(
      (features?.default_day_minutes ?? Array(7).fill(0)).map((m: number) => (m > 0 ? String(m / 60).replace('.', ',') : '')),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultModel])

  /** Arbeitszeitmodell beim Anlegen; „Standard“ sendet nichts (das Backend nimmt den Standard). */
  function modelPayload() {
    switch (modelChoice) {
      case 'DAYS':
        return {
          no_work_time_model: false,
          work_time_model: {
            daily_hours: modelDailyHours.map((h) => (h.trim() ? Number(h.replace(',', '.')) : 0)),
            flexible: false,
            on_demand: false,
          },
        }
      case 'ON_DEMAND':
        return { no_work_time_model: false, work_time_model: { on_demand: true, flexible: false } }
      case 'NONE':
        return { no_work_time_model: true }
      default:
        return modelChoice.startsWith('PROFILE-')
          ? { no_work_time_model: false, work_time_profile_id: Number(modelChoice.slice('PROFILE-'.length)) }
          : { no_work_time_model: false }
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSaved(false)

    const payload = {
      location_id: Number(locationId),
      first_name: firstName,
      last_name: lastName,
      employee_number: employeeNumber,
      active,
      login_email: loginEmail || undefined,
      auto_break_enabled: autoBreakEnabled,
      // Leerer String entfernt die Karte beim Bearbeiten (None hieße "unverändert").
      nfc_uid: nfcUid.trim(),
      hire_date: hireDate || undefined,
      termination_date: terminationDate || undefined,
      clear_hire_date: hireDate === '',
      clear_termination_date: terminationDate === '',
      birth_date: birthDate || undefined,
      clear_birth_date: birthDate === '',
      show_birthday_in_calendar: showBirthdayInCalendar,
      department_id: departmentId === NONE ? undefined : Number(departmentId),
      clear_department_id: departmentId === NONE,
      supervisor_id: supervisorId === NONE ? undefined : Number(supervisorId),
      clear_supervisor_id: supervisorId === NONE,
      position: position.trim(),
      ...(password ? { password } : {}),
      ...(pin ? { pin } : resetPin ? { pin: '' } : {}),
      ...(isEditMode && locationChanged ? { location_valid_from: locationValidFrom } : {}),
    }
    if (!isEditMode && modelChoice === 'DAYS' && !modelDailyHours.some((h) => Number(h.replace(',', '.')) > 0)) {
      setError('Bitte mindestens einen Wochentag mit Stunden eintragen – oder ein anderes Arbeitszeitmodell wählen.')
      return
    }

    try {
      if (isEditMode) {
        await updateEmployee.mutateAsync({ employeeId: employee.id, payload })
      } else {
        await createEmployee.mutateAsync({ ...payload, ...modelPayload() })
      }
      if (onDone) {
        onDone()
      } else {
        // Im Reiter bleibt das Formular stehen; Einmal-Eingaben leeren.
        setPassword('')
        setPin('')
        setResetPin(false)
        setSaved(true)
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === 'EMPLOYEE_NUMBER_TAKEN') {
        setError('Diese Personalnummer wird bereits verwendet.')
      } else if (err instanceof ApiError && err.code === 'LOGIN_EMAIL_TAKEN') {
        setError('Diese Login-E-Mail wird bereits verwendet.')
      } else if (err instanceof ApiError && err.code === 'NFC_UID_TAKEN') {
        setError('Dieser Chip ist bereits einem anderen Mitarbeiter zugeordnet.')
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

  async function handlePayrollAccessChange(checked: boolean) {
    if (!isEditMode || hrRole !== 'HR') return
    setHrRoleError(null)
    setPayrollAccess(checked)
    try {
      await updateHrRole.mutateAsync({ employeeId: employee.id, hrRole: 'HR', payrollAccess: checked })
    } catch {
      setPayrollAccess(!checked)
      setHrRoleError('Berechtigung konnte nicht geändert werden.')
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
      {/* Zwei Spalten nach verfügbarer Breite (Dialog bzw. Reiter), nicht nach Bildschirm */}
      <div className="@container">
        <form className="grid grid-cols-1 gap-x-6 gap-y-4 @2xl:grid-cols-2" onSubmit={handleSubmit}>
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
            <Select value={locationId} onValueChange={ifChosen(setLocationId)}>
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
              <Label htmlFor="model_choice">Arbeitszeitmodell</Label>
              <select
                id="model_choice"
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
                value={modelChoice}
                onChange={(e) => {
                  setModelChoice(e.target.value as ModelChoice)
                  setModelTouched(true)
                }}
              >
                {defaultModel && <option value="DEFAULT">Standard aus den Einstellungen ({defaultModel})</option>}
                {profiles.map((profile) => (
                  <option key={profile.id} value={`PROFILE-${profile.id}`}>
                    Arbeitszeitmodell „{profile.name}“
                  </option>
                ))}
                <option value="DAYS">Stunden je Wochentag</option>
                <option value="ON_DEMAND">Nach Aufwand (Aushilfe, ohne Soll)</option>
                <option value="NONE">Kein Arbeitszeitmodell (ohne Soll, z. B. reines HR-Konto)</option>
              </select>
              {modelChoice === 'DAYS' && (
                <div className="grid grid-cols-7 gap-1">
                  {WEEKDAY_LABELS.map((label, day) => (
                    <div key={label} className="flex flex-col items-center gap-0.5">
                      <span className="text-xs text-slate-500">{label}</span>
                      <Input
                        inputMode="decimal"
                        aria-label={`Stunden ${label}`}
                        className="w-full px-1 text-center"
                        value={modelDailyHours[day]}
                        onChange={(e) => setModelDailyHours((c) => c.map((v, i) => (i === day ? e.target.value : v)))}
                      />
                    </div>
                  ))}
                </div>
              )}
              <p className="text-xs text-slate-500">
                {modelChoice === 'DAYS' && 'Z. B. Vollzeit 8 an Mo–Fr, Teilzeit Mo 8 / Di 8 / Mi 4. '}
                {modelChoice === 'NONE' && 'Ohne Soll – Tage ohne Stempelung sind dann nicht „zu klären“. '}
                {modelChoice.startsWith('PROFILE-') && 'Folgt automatisch den Änderungen des Modells. '}
                Gilt ab Anstelldatum (sonst ab heute); Wochen- oder Monatsstunden, Pausen und Kernzeit im Reiter
                „Arbeitszeit“.
              </p>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Abteilung</Label>
              <Select value={departmentId} onValueChange={ifChosen(setDepartmentId)}>
                <SelectTrigger aria-label="Abteilung">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Keine Abteilung</SelectItem>
                  {departments.map(({ department, depth }) => (
                    <SelectItem key={department.id} value={String(department.id)}>
                      {'\u00a0'.repeat(depth * 3)}
                      {department.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="position">Position</Label>
              <Input id="position" maxLength={150} value={position} onChange={(event) => setPosition(event.target.value)} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Abweichende Führungskraft</Label>
            <Select value={supervisorId} onValueChange={ifChosen(setSupervisorId)}>
              <SelectTrigger aria-label="Abweichende Führungskraft">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Wie Abteilung (automatisch)</SelectItem>
                {colleagues.map((colleague) => (
                  <SelectItem key={colleague.id} value={String(colleague.id)}>
                    {colleague.last_name}, {colleague.first_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-slate-500">
              {supervisorId === NONE
                ? automaticSupervisorText(departmentList, departmentId === NONE ? null : Number(departmentId), employee?.id)
                : 'Ausnahme: gilt statt der Abteilungsleitung.'}{' '}
              Führungskraft für Organigramm, Sichtbarkeit und Genehmigungen.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hire_date">Anstelldatum</Label>
            <Input id="hire_date" type="date" value={hireDate} onChange={(event) => setHireDate(event.target.value)} />
          </div>
          <details className="rounded-md border border-slate-200 p-3" open={isEditMode}>
            <summary className="cursor-pointer text-sm font-medium text-slate-700">
              Weitere Angaben (Austritt, Geburtstag, Aktiv, Pausen)
            </summary>
            <div className="mt-3 flex flex-col gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Aktiv
          </label>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="termination_date">Austrittsdatum</Label>
            <Input
              id="termination_date"
              type="date"
              value={terminationDate}
              onChange={(event) => setTerminationDate(event.target.value)}
            />
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
            </div>
          </details>
          </div>

          <div className="flex flex-col gap-4">
          <details className="flex flex-col rounded-md border border-slate-200 p-3" open={isEditMode}>
            <summary className="cursor-pointer text-sm font-medium text-slate-700">
              Login und Stempeln am Tablet (E-Mail, Passwort, PIN, Chip)
            </summary>
            <div className="mt-3 flex flex-col gap-4">
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
              {isEditMode && isAdmin && employee?.two_factor_enabled && (
                <div className="flex flex-col gap-1">
                  <p className="text-xs text-slate-600">Zwei-Faktor-Anmeldung ist eingerichtet.</p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="self-start"
                    disabled={resetTwoFactor.isPending}
                    onClick={() => employee && resetTwoFactor.mutate(employee.id)}
                  >
                    Zwei-Faktor-Anmeldung zurücksetzen
                  </Button>
                  <p className="text-xs text-slate-500">
                    Z. B. wenn das Handy verloren ist. Danach meldet sich die Person nur mit Passwort an bzw. richtet sie neu
                    ein, wenn sie Pflicht ist.
                  </p>
                </div>
              )}
              {isEditMode && isAdmin && resetTwoFactor.isSuccess && !employee?.two_factor_enabled && (
                <p className="text-xs text-emerald-700">Zwei-Faktor-Anmeldung zurückgesetzt.</p>
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
                pattern="\d{4,8}"
                maxLength={8}
                title="4 bis 8 Ziffern"
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
                4 bis 8 Ziffern. Wird beim Stempeln am Tablet abgefragt, sofern in den Einstellungen aktiviert. Ohne PIN legt der Mitarbeiter
                ihn beim ersten Stempeln am Tablet selbst fest (wenn unter Einstellungen → „Stempeln“ erlaubt).
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
            <p className="mb-3 text-sm font-medium text-slate-700">Chip (Tablet)</p>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="nfc_uid">Chip-UID (optional)</Label>
              <Input
                id="nfc_uid"
                type="text"
                placeholder="Hier klicken und Chip an den USB-Leser halten – oder UID eintippen"
                value={nfcUid}
                onChange={(event) => setNfcUid(event.target.value)}
              />
              <p className="text-xs text-slate-500">
                Chip oder Karte des Mitarbeiters: am Tablet direkt erkannt (ersetzt den PIN, bei „Nur Chip“ notwendig).
                Unbekannte Chips zeigt das Tablet mit ihrer UID an. Feld leeren, um den Chip zu entfernen.
              </p>
              {!showQr && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="self-start"
                  onClick={() => {
                    if (!nfcUid.trim()) setNfcUid(randomCardUid())
                    setShowQr(true)
                  }}
                >
                  QR-Code fürs Tablet
                </Button>
              )}
              {showQr && nfcUid.trim() && (
                <>
                  <CardQrCode uid={nfcUid.trim()} name={`${firstName} ${lastName}`.trim()} />
                  {nfcUid.trim() !== (employee?.nfc_uid ?? '') && (
                    <p className="text-xs text-amber-700">Neue Chip-UID – bitte unten speichern, sonst gilt der QR-Code nicht.</p>
                  )}
                </>
              )}
            </div>
          </div>
            </div>
          </details>

          {isEditMode && isAdmin && (
            <div className="flex flex-col gap-1.5">
              <Label>HR-Berechtigung</Label>
              <Select value={hrRole} onValueChange={ifChosen((value) => void handleHrRoleChange(value))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_HR_ROLE}>Keine (nur Mein Bereich)</SelectItem>
                  <SelectItem value="HR">HR</SelectItem>
                  <SelectItem value="SUPERVISOR">Führungskraft</SelectItem>
                  <SelectItem value="ADMIN">Admin</SelectItem>
                </SelectContent>
              </Select>
              {hrRole === 'HR' && (
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300"
                    checked={payrollAccess}
                    onChange={(event) => void handlePayrollAccessChange(event.target.checked)}
                  />
                  Vergütung &amp; Lohn-Export (Vergütung, Zulagen, Lohnkosten, DATEV, Lohnarten)
                </label>
              )}
              {hrRole === 'ADMIN' && (
                <p className="text-xs text-slate-500">Admins haben „Vergütung &amp; Lohn-Export“ immer.</p>
              )}
              {hrRoleError && <p className="text-sm text-red-600">{hrRoleError}</p>}
            </div>
          )}
          </div>

          {resetNotice && <p className="text-sm text-emerald-600 @2xl:col-span-2">{resetNotice}</p>}
          {error && <p className="text-sm text-red-600 @2xl:col-span-2">{error}</p>}
          {onDone ? (
            <DialogFooter className="@2xl:col-span-2">
              <Button type="button" variant="outline" onClick={onDone}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={isSubmitting || !locationId}>
                {isSubmitting ? 'Speichern…' : 'Speichern'}
              </Button>
            </DialogFooter>
          ) : (
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-4 @2xl:col-span-2">
              <Button type="submit" disabled={isSubmitting || !locationId}>
                {isSubmitting ? 'Speichern…' : 'Speichern'}
              </Button>
              <Button type="button" variant="outline" onClick={() => setResetKey((key) => key + 1)}>
                Änderungen verwerfen
              </Button>
              {saved && <span className="text-sm text-emerald-700">Gespeichert.</span>}
            </div>
          )}
        </form>
      </div>

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
