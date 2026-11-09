import { OrgChart } from '../components/org/OrgChart'

export function OrgChartPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Organigramm</h1>
      <p className="text-sm text-slate-500">
        Aus der Führungskraft je Mitarbeiter (Mitarbeiterformular). Abteilungen und Positionen pflegst du dort und unter
        „Einstellungen“ → „Abteilungen“.
      </p>
      <OrgChart />
    </div>
  )
}
