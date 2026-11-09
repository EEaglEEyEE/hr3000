import type { ReactNode } from 'react'
import { Navigate, NavLink, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useSettingsQuery, useUpdateSettingsMutation, type Bundesland, type Settings } from '../api/queries/settings'
import { useFeaturesQuery } from '../api/queries/workTimeModel'
import { useAuth } from '../auth/AuthContext'
import { allows, type Access } from '../lib/access'
import { BUNDESLAND_LABELS } from '../lib/labels'
import { cn } from '../lib/utils'
import { SmtpSettingsCard } from '../components/settings/SmtpSettingsCard'
import { LogoSettingsCard } from '../components/settings/LogoSettingsCard'
import { TwoFactorPolicyCard } from '../components/settings/TwoFactorPolicyCard'
import {
  CoreTimeCard,
  EmployeeDefaultsCard,
  KioskAdminPinCard,
  KioskDisplayCard,
  MaxShiftSpanCard,
  SeniorityLeaveCard,
  OvertimeLimitsCard,
  OpenDayChecksCard,
  KioskLoginCard,
  SettingsCard,
  SettingsToggle,
  VacationCarryOverCard,
  VacationRulesCard,
} from '../components/settings/DefaultsSettingsCard'
import { AbsenceTypesCard, NewAbsenceTypeCard } from '../components/settings/AbsenceTypesCard'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { PlanCard } from '../components/plan/PlanNotice'
import { AccountCancellationCard } from '../components/account/AccountCancellation'
import { SettingsTransferCard } from '../components/migration/SettingsTransferCard'
import { AuditLogPage } from './AuditLogPage'
import { BreakRulesPage } from './BreakRulesPage'
import { DevicesPage } from './DevicesPage'
import { HolidaysPage } from './HolidaysPage'
import { LocationsPage } from './LocationsPage'
import { ShiftTemplatesPage } from './ShiftTemplatesPage'
import { WorkTimeProfilesPage } from './WorkTimeProfilesPage'
import { SurchargeRulesPage } from './SurchargeRulesPage'
import { TeamsPage } from './TeamsPage'
import { DepartmentsPage } from './DepartmentsPage'
import { CostCentersPage } from './CostCentersPage'
import { AttributeSettingsPage } from './AttributeSettingsPage'
import { DocumentCategoriesPage } from './DocumentCategoriesPage'
import { DocumentTemplatesPage } from './DocumentTemplatesPage'
import { IntegrationsPage } from './IntegrationsPage'
import { WageTypesPage } from './WageTypesPage'

// Zwei Spalten ab großer Breite – lange Einstellungsseiten bleiben überschaubar.
const GRID = 'grid grid-cols-1 items-start gap-4 xl:grid-cols-2'

interface SectionContext {
  /** Firmen-Einstellungen (nur Admin – für HR nicht geladen). */
  settings: Settings | undefined
  isAdmin: boolean
  shiftPlanningEnabled: boolean
}

interface Section {
  key: string
  label: string
  access: Access
  /** Zusätzliche Bedingung (z. B. Schichtplanung eingeschaltet). */
  visible?: (context: SectionContext) => boolean
  /** Braucht die Firmen-Einstellungen (GET /settings). */
  needsSettings?: boolean
  render: (context: SectionContext) => ReactNode
}

/** Bereiche der Einstellungen nach Fachthemen. Die früheren eigenen Menüpunkte (Standorte, Feiertage,
 * Tablets, Pausenregeln …) haben hier ihren Platz; alte Adressen leiten hierher um (App.tsx). */
const GROUPS: { title: string; sections: Section[] }[] = [
  {
    title: 'Unternehmen',
    sections: [
      { key: 'firma', label: 'Allgemein', access: 'admin', needsSettings: true, render: ({ settings }) => <CompanySection settings={settings!} /> },
      { key: 'standorte', label: 'Standorte', access: 'hr', render: () => <LocationsPage /> },
      { key: 'teams', label: 'Teams', access: 'hr', render: () => <TeamsPage /> },
      { key: 'abteilungen', label: 'Abteilungen', access: 'hr', render: () => <DepartmentsPage /> },
      { key: 'kostenstellen', label: 'Kostenstellen', access: 'hr', render: () => <CostCentersPage /> },
      { key: 'personalakte-felder', label: 'Felder der Personalakte', access: 'admin', render: () => <AttributeSettingsPage /> },
      { key: 'dokumentkategorien', label: 'Dokumentkategorien', access: 'admin', render: () => <DocumentCategoriesPage /> },
      { key: 'dokumentvorlagen', label: 'Dokumentvorlagen', access: 'admin', render: () => <DocumentTemplatesPage /> },
      { key: 'feiertage', label: 'Feiertagskalender', access: 'hr', render: () => <HolidaysPage /> },
    ],
  },
  {
    title: 'Arbeitszeit & Pausen',
    sections: [
      { key: 'arbeitszeit', label: 'Arbeitszeit', access: 'admin', needsSettings: true, render: ({ settings }) => <WorkingTimeSection settings={settings!} /> },
      { key: 'arbeitszeitmodelle', label: 'Arbeitszeitmodelle', access: 'hr', render: () => <WorkTimeProfilesPage /> },
      { key: 'pausen', label: 'Pausenregeln', access: 'admin', render: () => <BreakRulesPage /> },
      {
        key: 'schichtplanung',
        label: 'Schichtplanung',
        access: 'hr',
        // HR pflegt die Schichtvorlagen, das Ein- und Ausschalten bleibt beim Admin.
        visible: ({ isAdmin, shiftPlanningEnabled }) => isAdmin || shiftPlanningEnabled,
        render: (context) => <ShiftPlanningSection {...context} />,
      },
    ],
  },
  {
    title: 'Abwesenheiten & Urlaub',
    sections: [
      { key: 'urlaub', label: 'Urlaub & Anträge', access: 'admin', needsSettings: true, render: ({ settings }) => <VacationSection settings={settings!} /> },
      {
        key: 'abwesenheitsarten',
        label: 'Abwesenheitsarten',
        access: 'admin',
        render: () => (
          <div className={GRID}>
            <AbsenceTypesCard />
            <NewAbsenceTypeCard />
          </div>
        ),
      },
    ],
  },
  {
    title: 'Stempeln & Tablets',
    sections: [
      { key: 'stempeln', label: 'Stempeln', access: 'admin', needsSettings: true, render: ({ settings }) => <PunchingSection settings={settings!} /> },
      {
        key: 'tablet-anzeige',
        label: 'Anzeige am Tablet',
        access: 'admin',
        needsSettings: true,
        render: ({ settings }) => (
          <div className={GRID}>
            <KioskDisplayCard settings={settings!} />
            <KioskAdminPinCard settings={settings!} />
          </div>
        ),
      },
      { key: 'tablets', label: 'Tablets', access: 'hr', render: () => <DevicesPage /> },
    ],
  },
  {
    title: 'Prüfungen',
    sections: [
      {
        key: 'zu-klaeren',
        label: '„Zu klären“',
        access: 'admin',
        needsSettings: true,
        render: ({ settings }) => (
          <div className={GRID}>
            <OpenDayChecksCard settings={settings!} />
          </div>
        ),
      },
    ],
  },
  {
    title: 'Abrechnung',
    sections: [
      { key: 'zuschlaege', label: 'Zuschläge', access: 'admin', render: () => <SurchargeRulesPage /> },
      { key: 'lohnarten', label: 'Lohnarten', access: 'payroll', render: () => <WageTypesPage /> },
    ],
  },
  {
    title: 'Konto',
    sections: [
      {
        key: 'konto',
        label: 'Tarif & Konto',
        access: 'admin',
        render: () => (
          <div className={GRID}>
            <div className="flex flex-col gap-4">
              <PlanCard />
              <SettingsTransferCard />
            </div>
            {/* Kündigen bewusst zuletzt */}
            <AccountCancellationCard />
          </div>
        ),
      },
      {
        key: 'e-mail',
        label: 'E-Mail-Versand',
        access: 'admin',
        needsSettings: true,
        render: ({ settings }) => (
          <div className={GRID}>
            <SmtpSettingsCard settings={settings!} />
          </div>
        ),
      },
      { key: 'api', label: 'API & Webhooks', access: 'admin', render: () => <IntegrationsPage /> },
      { key: 'audit-log', label: 'Audit-Protokoll', access: 'hr', render: () => <AuditLogPage /> },
    ],
  },
]

/** Frühere Reiter (?bereich=…) – Links aus Handbuch und Lesezeichen funktionieren weiter. */
const LEGACY_SECTIONS: Record<string, string> = {
  allgemein: 'firma',
  mitarbeiter: 'arbeitszeit',
  abwesenheiten: 'urlaub',
  kiosk: 'stempeln',
  darstellung: 'firma',
}

export function SettingsPage() {
  const { isAdmin, isFullHr, canPayroll } = useAuth()
  const { seite } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const settingsQuery = useSettingsQuery(isAdmin)
  const featuresQuery = useFeaturesQuery()
  const context: SectionContext = {
    settings: settingsQuery.data,
    isAdmin,
    shiftPlanningEnabled: featuresQuery.data?.shift_planning_enabled ?? false,
  }

  const groups = GROUPS.map((group) => ({
    ...group,
    sections: group.sections.filter(
      (section) => allows(section.access, { isAdmin, isFullHr, canPayroll }) && (section.visible?.(context) ?? true),
    ),
  })).filter((group) => group.sections.length > 0)
  const sections = groups.flatMap((group) => group.sections)

  const legacy = searchParams.get('bereich')
  if (!seite && legacy && LEGACY_SECTIONS[legacy]) {
    return <Navigate to={`/einstellungen/${LEGACY_SECTIONS[legacy]}`} replace />
  }
  const current = sections.find((section) => section.key === seite) ?? sections[0]
  if (!current) {
    return <p className="text-slate-500">Für die Einstellungen fehlt die Berechtigung.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Einstellungen</h1>
        <p className="text-sm text-slate-500">Gelten für alle Standorte und Tablets dieser Firma.</p>
      </div>

      {/* Handy: Auswahlliste statt Seitenleiste */}
      <select
        aria-label="Bereich der Einstellungen"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm md:hidden"
        value={current.key}
        onChange={(event) => navigate(`/einstellungen/${event.target.value}`)}
      >
        {groups.map((group) => (
          <optgroup key={group.title} label={group.title}>
            {group.sections.map((section) => (
              <option key={section.key} value={section.key}>
                {section.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

      <div className="flex items-start gap-6">
        <nav aria-label="Bereiche der Einstellungen" className="hidden w-52 shrink-0 flex-col gap-3 md:flex">
          {groups.map((group) => (
            <div key={group.title} className="flex flex-col gap-0.5">
              <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{group.title}</p>
              {group.sections.map((section) => (
                <NavLink
                  key={section.key}
                  to={`/einstellungen/${section.key}`}
                  aria-current={section.key === current.key ? 'page' : undefined}
                  className={cn(
                    'rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-100',
                    section.key === current.key && 'bg-slate-200 font-medium text-slate-900 hover:bg-slate-200',
                  )}
                >
                  {section.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <section className="flex min-w-0 flex-1 flex-col gap-4" aria-label={current.label}>
          {current.needsSettings && settingsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
          {current.needsSettings && settingsQuery.isError && (
            <p className="text-red-600">Einstellungen konnten nicht geladen werden.</p>
          )}
          {(!current.needsSettings || context.settings) && current.render(context)}
        </section>
      </div>
    </div>
  )
}

function saveError(error: unknown): string | null {
  if (!error) return null
  return error instanceof ApiError && error.status !== 422 ? error.message : 'Speichern fehlgeschlagen – bitte Eingaben prüfen.'
}

/** Schalter dieser Seite speichern direkt; Fehler (z. B. abgeschlossene Monate) stehen oben. */
function useInlineSettings() {
  const update = useUpdateSettingsMutation()
  return { update, pending: update.isPending, error: saveError(update.error) }
}

function InlineError({ error }: { error: string | null }) {
  return error ? <p className="text-sm text-red-600">{error}</p> : null
}

function CompanySection({ settings }: { settings: Settings }) {
  const { update, pending, error } = useInlineSettings()
  return (
    <>
      <InlineError error={error} />
      <div className={GRID}>
        <div className="flex flex-col gap-4">
          <SettingsCard
            title="Standard-Bundesland"
            description="Wird beim automatischen Import der Feiertage (siehe „Feiertagskalender“) verwendet, wenn dort kein abweichendes Bundesland gewählt wird."
          >
            <Select
              value={settings.default_bundesland ?? undefined}
              onValueChange={(value) => update.mutate({ default_bundesland: value as Bundesland })}
            >
              <SelectTrigger className="w-64 max-w-full" aria-label="Standard-Bundesland">
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
          <SettingsToggle
            checked={settings.show_birthdays_in_calendar}
            disabled={pending}
            onChange={(checked) => update.mutate({ show_birthdays_in_calendar: checked })}
            title="Geburtstage im Kalender anzeigen"
          >
            Markiert den Geburtstag eines Mitarbeiters im Kalender, sofern ein Geburtsdatum hinterlegt ist. Kann im
            Mitarbeiterformular pro Mitarbeiter zusätzlich deaktiviert werden.
          </SettingsToggle>
          <SettingsToggle
            checked={settings.reminders_enabled}
            disabled={pending}
            onChange={(checked) => update.mutate({ reminders_enabled: checked })}
            title="Erinnerungen an Admin und HR"
          >
            Einmal am Tag als Benachrichtigung (und per E-Mail, wenn ein Mailversand eingerichtet ist): Probezeit endet in 14
            Tagen, Befristung endet in 30 Tagen, Austritt in 14 Tagen, Resturlaub aus dem Vorjahr verfällt in 30 Tagen – das
            Letzte auch an die Person selbst.
          </SettingsToggle>
          <SettingsToggle
            checked={settings.org_chart_for_employees}
            disabled={pending}
            onChange={(checked) => update.mutate({ org_chart_for_employees: checked })}
            title="Mitarbeiter sehen das Organigramm"
          >
            Reiter „Organigramm“ in „Mein Bereich“ mit Name, Position, Abteilung und Führungskraft aller aktiven
            Mitarbeiter. Admin, HR und Führungskräfte sehen es immer.
          </SettingsToggle>
          <TwoFactorPolicyCard
            roles={settings.two_factor_roles}
            disabled={pending}
            onChange={(roles) => update.mutate({ two_factor_roles: roles })}
          />
        </div>
        <LogoSettingsCard />
      </div>
    </>
  )
}

function WorkingTimeSection({ settings }: { settings: Settings }) {
  const { update, pending, error } = useInlineSettings()
  return (
    <>
      <InlineError error={error} />
      <div className={GRID}>
        <div className="flex flex-col gap-4">
          <SettingsCard
            title="Überstundenkonten führen ab"
            description="Leer = je Mitarbeiter ab der ersten Stempelung (frühestens ab Eintritt). Mit einem Datum (z. B. Einführung von HR3000) beginnt das Konto für alle an diesem Tag – auch für Mitarbeiter, die noch nie gestempelt haben; fehlende Stunden zählen dann ins Minus. Altsalden lassen sich am Mitarbeiter als „Übertrag“ buchen. Eine Änderung rechnet alle Konten neu."
          >
            <input
              type="date"
              aria-label="Überstundenkonten führen ab"
              className="h-9 w-44 rounded-md border border-slate-300 px-2 text-sm"
              value={settings.balance_start_date ?? ''}
              disabled={pending}
              onChange={(event) =>
                update.mutate(
                  event.target.value
                    ? { balance_start_date: event.target.value, clear_balance_start_date: false }
                    : { clear_balance_start_date: true },
                )
              }
            />
          </SettingsCard>
          <EmployeeDefaultsCard settings={settings} />
          <MaxShiftSpanCard settings={settings} />
          <OvertimeLimitsCard settings={settings} />
        </div>
        <CoreTimeCard settings={settings} />
      </div>
    </>
  )
}

function ShiftPlanningSection({ settings, isAdmin, shiftPlanningEnabled }: SectionContext) {
  const { update, pending, error } = useInlineSettings()
  return (
    <>
      <InlineError error={error} />
      {isAdmin && settings && (
        <SettingsToggle
          checked={settings.shift_planning_enabled}
          disabled={pending}
          onChange={(checked) => update.mutate({ shift_planning_enabled: checked })}
          title="Schichtplanung aktivieren"
        >
          Ohne Schichtplanung gilt für jeden Mitarbeiter nur sein Arbeitszeitmodell (Reiter „Arbeitszeit“). Mit
          Schichtplanung kommen Schichtvorlagen mit Uhrzeiten, der Schichtplan-Kalender und Tagesausnahmen hinzu. Beim
          Ausschalten bleiben gespeicherte Einträge erhalten: Tagesausnahmen aus dem Kalender wirken dann nicht mehr,
          Uhrzeiten aus Schichtvorlagen im Arbeitszeitmodell gelten weiter.
        </SettingsToggle>
      )}
      {shiftPlanningEnabled && <ShiftTemplatesPage />}
    </>
  )
}

function VacationSection({ settings }: { settings: Settings }) {
  const { update, pending, error } = useInlineSettings()
  return (
    <>
      <InlineError error={error} />
      <div className={GRID}>
        <div className="flex flex-col gap-4">
          <VacationRulesCard settings={settings} />
          <SeniorityLeaveCard settings={settings} />
          <VacationCarryOverCard settings={settings} />
        </div>
        <div className="flex flex-col gap-4">
          <SettingsToggle
            checked={settings.absence_requests_enabled}
            disabled={pending}
            onChange={(checked) => update.mutate({ absence_requests_enabled: checked })}
            title="Mitarbeiter dürfen Urlaub/Abwesenheiten beantragen"
          >
            Aus = Mitarbeiter können unter „Mein Bereich“ keine Anträge mehr stellen; Urlaub und Abwesenheiten trägt nur
            noch HR bzw. die Teamleitung ein. Offene Anträge stehen weiter unter „Zu klären“ → „Urlaubsanträge“. Welche
            Arten beantragt werden dürfen und ob sie genehmigt werden müssen, steht unter „Abwesenheitsarten“.
          </SettingsToggle>
          <SettingsToggle
            checked={settings.absence_four_eyes}
            disabled={pending}
            onChange={(checked) => update.mutate({ absence_four_eyes: checked })}
            title="Vier-Augen-Prinzip: eigene Anträge genehmigt jemand anderes"
          >
            An = Wer genehmigen darf (Admin, HR, Führungskräfte), bekommt eigene Abwesenheiten mit „Genehmigung nötig“ nicht
            direkt genehmigt – sie erscheinen als Antrag unter „Zu klären“ → „Urlaubsanträge“ und eine andere Person entscheidet. Aus =
            eigene Einträge gelten sofort.
          </SettingsToggle>
          <SettingsToggle
            checked={settings.absence_overlaps_for_employees}
            disabled={pending}
            onChange={(checked) => update.mutate({ absence_overlaps_for_employees: checked })}
            title="Mitarbeiter sehen beim Antrag, wer im Team gleichzeitig abwesend ist"
          >
            An = Im Antrag stehen Name und Zeitraum der Abwesenheiten anderer aus demselben Team (ohne Art). Wer genehmigt,
            sieht das unter „Zu klären“ → „Urlaubsanträge“ immer – dort mit Art und Resturlaub.
          </SettingsToggle>
          <SettingsToggle
            checked={settings.team_calendar_for_employees}
            disabled={pending}
            onChange={(checked) => update.mutate({ team_calendar_for_employees: checked })}
            title="Mitarbeiter sehen den Teamkalender ihres Teams"
          >
            An = In „Mein Bereich“ gibt es den Reiter „Teamkalender“ mit den Abwesenheiten im eigenen Team. Die Art steht nur bei
            Abwesenheitsarten mit „Im Teamkalender: farbig“, sonst nur, dass jemand fehlt; Homeoffice-Angaben gar nicht.
          </SettingsToggle>
        </div>
      </div>
    </>
  )
}

function PunchingSection({ settings }: { settings: Settings }) {
  const { update, pending, error } = useInlineSettings()
  return (
    <>
      <InlineError error={error} />
      <div className={GRID}>
        <div className="flex flex-col gap-4">
          <SettingsToggle
            checked={settings.portal_punching_enabled}
            disabled={pending}
            onChange={(checked) => update.mutate({ portal_punching_enabled: checked })}
            title="Stempeln über den Web-Login (Home-Office)"
          >
            Mitarbeiter mit eigenem Login sehen nach der Anmeldung auf ihrer Startseite eine Karte „Stempeln“ und können
            dort Kommen/Gehen buchen – z. B. im Home-Office oder unterwegs. Es gilt immer die Serverzeit, nachträgliches
            Eintragen ist so nicht möglich; die Stempelung ist mit der Quelle „Web-Login“ gekennzeichnet. Pausen- und
            Dienstgang-Buttons richten sich nach „Anzeige am Tablet“.
          </SettingsToggle>
        </div>
        <KioskLoginCard settings={settings} />
      </div>
    </>
  )
}
