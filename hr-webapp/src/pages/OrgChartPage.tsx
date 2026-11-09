import { OrgChart } from '../components/org/OrgChart'

export function OrgChartPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Organigramm</h1>
      <p className="text-sm text-slate-500">
        Die Abteilungen mit ihren Leitungen und Stellvertretungen und wer in welcher Abteilung ist. Die Leitungen sind die
        Führungskräfte der Abteilung.
      </p>
      <OrgChart />
    </div>
  )
}
