import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSettingsQuery, useUpdateSettingsMutation, type Bundesland } from '../api/queries/settings'
import { BUNDESLAND_LABELS } from '../lib/labels'
import { SmtpSettingsCard } from '../components/settings/SmtpSettingsCard'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { LogoSettingsCard } from '../components/settings/LogoSettingsCard'
import {
  EmployeeDefaultsCard,
  KioskAdminPinCard,
  KioskDisplayCard,
  RfidSettingsCard,
  RulesCard,
  CoreTimeCard,
  SettingsCard,
  SettingsToggle,
  VacationCarryOverCard,
} from '../components/settings/DefaultsSettingsCard'
import { AbsenceTypesCard, NewAbsenceTypeCard } from '../components/settings/AbsenceTypesCard'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { PlanCard } from '../components/plan/PlanNotice'
import { AccountCancellationCard } from '../components/account/AccountCancellation'

const SECTIONS = [
  { value: 'allgemein', label: 'Allgemein' },
  { value: 'mitarbeiter', label: 'Mitarbeiter & Regeln' },
  { value: 'abwesenheiten', label: 'Abwesenheiten & Urlaub' },
  { value: 'kiosk', label: 'Kiosk' },
  { value: 'darstellung', label: 'Logo & E-Mail' },
]

// Zwei Spalten ab mittlerer Breite – lange Einstellungsseiten bleiben überschaubar.
const GRID = 'grid items-start gap-4 lg:grid-cols-2'

export function SettingsPage() {
  const settingsQuery = useSettingsQuery()
  const updateSettings = useUpdateSettingsMutation()
  const [searchParams, setSearchParams] = useSearchParams()
  const section = SECTIONS.some((s) => s.value === searchParams.get('bereich'))
    ? searchParams.get('bereich')!
    : 'allgemein'

  const [defaultAnnualVacationDays, setDefaultAnnualVacationDays] = useState(0)

  useEffect(() => {
    if (settingsQuery.data) {
      setDefaultAnnualVacationDays(settingsQuery.data.default_annual_vacation_days)
    }
  }, [settingsQuery.data])

  const settings = settingsQuery.data
  const pending = updateSettings.isPending

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Einstellungen</h1>
        <p className="text-sm text-slate-500">
          Einstellungen für diesen Mandanten – gelten für alle Standorte und Tablets.
        </p>
      </div>

      {settingsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {settingsQuery.isError && <p className="text-red-600">Einstellungen konnten nicht geladen werden.</p>}

      {settings && (
        <Tabs value={section} onValueChange={(value) => setSearchParams({ bereich: value }, { replace: true })}>
          <TabsList>
            {SECTIONS.map((s) => (
              <TabsTrigger key={s.value} value={s.value}>
                {s.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="allgemein">
            <div className={GRID}>
              <div className="flex flex-col gap-4">
                <PlanCard />
                <AccountCancellationCard />
                <SettingsCard
                  title="Gleitzeitkonten führen ab"
                  description="Leer = je Mitarbeiter ab der ersten Stempelung (frühestens ab Eintritt). Mit einem Datum (z. B. Einführung von HR3000) beginnt das Konto für alle an diesem Tag – auch für Mitarbeiter, die noch nie gestempelt haben; fehlende Stunden zählen dann ins Minus. Altsalden lassen sich am Mitarbeiter als „Übertrag“ buchen. Eine Änderung rechnet alle Konten neu."
                >
                  <input
                    type="date"
                    className="h-9 w-44 rounded-md border border-slate-300 px-2 text-sm"
                    value={settings.balance_start_date ?? ''}
                    disabled={pending}
                    onChange={(event) =>
                      updateSettings.mutate(
                        event.target.value
                          ? {
                              balance_start_date: event.target.value,
                              clear_balance_start_date: false,
                            }
                          : { clear_balance_start_date: true },
                      )
                    }
                  />
                </SettingsCard>

                <SettingsCard
                  title="Standard-Jahresurlaub"
                  description="Wird einem Mitarbeiter automatisch als Urlaubsanspruch zugewiesen, sobald für ihn zum ersten Mal ein Jahr geöffnet wird (siehe Urlaubsanspruch-Karte im Mitarbeiterprofil). Bereits angelegte Ansprüche werden dadurch nicht rückwirkend geändert."
                >
                  <div className="flex items-end gap-2">
                    <Input
                      type="number"
                      min={0}
                      step={0.5}
                      className="w-32"
                      value={defaultAnnualVacationDays}
                      onChange={(event) => setDefaultAnnualVacationDays(Number(event.target.value) || 0)}
                    />
                    <Button
                      size="sm"
                      disabled={pending || defaultAnnualVacationDays === settings.default_annual_vacation_days}
                      onClick={() =>
                        updateSettings.mutate({
                          default_annual_vacation_days: defaultAnnualVacationDays,
                        })
                      }
                    >
                      {pending ? 'Speichern…' : 'Speichern'}
                    </Button>
                  </div>
                </SettingsCard>

                <SettingsCard
                  title="Standard-Bundesland"
                  description="Wird beim automatischen Import der Feiertage (siehe Feiertage-Seite) verwendet, wenn dort kein abweichendes Bundesland gewählt wird."
                >
                  <Select
                    value={settings.default_bundesland ?? undefined}
                    onValueChange={(value) =>
                      updateSettings.mutate({
                        default_bundesland: value as Bundesland,
                      })
                    }
                  >
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Bundesland wählen" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(BUNDESLAND_LABELS).map(([code, label]) => (
                        <SelectItem key={code} value={code}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </SettingsCard>
              </div>

              <div className="flex flex-col gap-4">
                <SettingsToggle
                  checked={settings.shift_planning_enabled}
                  disabled={pending}
                  onChange={(checked) => updateSettings.mutate({ shift_planning_enabled: checked })}
                  title="Schichtplanung aktivieren"
                >
                  Ohne Schichtplanung gilt für jeden Mitarbeiter nur sein einfaches Arbeitszeitmodell (Reiter
                  „Arbeitszeitmodell“). Mit Schichtplanung kommen Schichtvorlagen mit Uhrzeiten, der
                  Schichtplan-Kalender und Tagesausnahmen hinzu. Beim Ausschalten bleiben gespeicherte Einträge
                  erhalten, wirken aber nicht.
                </SettingsToggle>

                <SettingsToggle
                  checked={settings.portal_punching_enabled}
                  disabled={pending}
                  onChange={(checked) => updateSettings.mutate({ portal_punching_enabled: checked })}
                  title="Stempeln über den Web-Login (Home-Office)"
                >
                  Mitarbeiter mit eigenem Login sehen nach der Anmeldung auf ihrer Startseite eine Karte „Stempeln“ und
                  können dort Kommen/Gehen buchen – z. B. im Home-Office oder unterwegs. Es gilt immer die Serverzeit,
                  nachträgliches Eintragen ist so nicht möglich; die Stempelung ist mit der Quelle „Web-Login“
                  gekennzeichnet. Pausen- und Dienstgang-Buttons richten sich nach den Kiosk-Einstellungen.
                </SettingsToggle>
                <SettingsToggle
                  checked={settings.show_birthdays_in_calendar}
                  disabled={pending}
                  onChange={(checked) =>
                    updateSettings.mutate({
                      show_birthdays_in_calendar: checked,
                    })
                  }
                  title="Geburtstage im Kalender anzeigen"
                >
                  Markiert den Geburtstag eines Mitarbeiters im Kalender, sofern ein Geburtsdatum hinterlegt ist. Kann
                  im Mitarbeiterformular pro Mitarbeiter zusätzlich deaktiviert werden.
                </SettingsToggle>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="mitarbeiter">
            <div className={GRID}>
              <EmployeeDefaultsCard settings={settings} />
              <div className="flex flex-col gap-4">
                <RulesCard settings={settings} />
                <CoreTimeCard settings={settings} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="abwesenheiten">
            <div className={GRID}>
              <AbsenceTypesCard />
              <div className="flex flex-col gap-4">
                <SettingsToggle
                  checked={settings.absence_requests_enabled}
                  disabled={pending}
                  onChange={(checked) => updateSettings.mutate({ absence_requests_enabled: checked })}
                  title="Mitarbeiter dürfen Urlaub/Abwesenheiten beantragen"
                >
                  Aus = Mitarbeiter können unter „Mein Bereich“ keine Anträge mehr stellen; Urlaub und Abwesenheiten trägt
                  nur noch HR bzw. der Teamleader ein. Der Menüpunkt „Urlaubsanträge“ verschwindet, sobald keine offenen
                  Anträge mehr da sind. Welche Arten beantragt werden dürfen und ob sie genehmigt werden müssen, steht
                  links je Abwesenheitsart.
                </SettingsToggle>
                <NewAbsenceTypeCard />
                <VacationCarryOverCard settings={settings} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="kiosk">
            <div className={GRID}>
              <div className="flex flex-col gap-4">
                <SettingsToggle
                  checked={settings.require_pin_for_punch}
                  disabled={pending}
                  onChange={(checked) => updateSettings.mutate({ require_pin_for_punch: checked })}
                  title="PIN zum Stempeln erforderlich"
                >
                  Mitarbeiter müssen am Tablet ihren PIN eingeben, um zu stempeln (ein gültiger Chip ersetzt den PIN).
                  Mitarbeiter ohne hinterlegten PIN können dann nicht mehr stempeln, bis ein PIN vergeben wurde.
                </SettingsToggle>
                <SettingsToggle
                  checked={settings.kiosk_pin_self_setup}
                  disabled={pending || !settings.require_pin_for_punch}
                  onChange={(checked) => updateSettings.mutate({ kiosk_pin_self_setup: checked })}
                  title="PIN beim ersten Stempeln selbst festlegen"
                >
                  Wer noch keinen PIN hat, legt ihn beim ersten Stempeln am Tablet selbst fest (zweimal eingeben). Bei
                  vergessenem PIN setzt HR ihn am Mitarbeiter zurück – dann wird er beim nächsten Stempeln neu
                  festgelegt – oder vergibt selbst einen. Jede Festlegung steht im Audit-Log.
                </SettingsToggle>
                <RfidSettingsCard settings={settings} />
              </div>
              <div className="flex flex-col gap-4">
                <KioskDisplayCard settings={settings} />
                <KioskAdminPinCard settings={settings} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="darstellung">
            <div className={GRID}>
              <LogoSettingsCard />
              <SmtpSettingsCard settings={settings} />
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
