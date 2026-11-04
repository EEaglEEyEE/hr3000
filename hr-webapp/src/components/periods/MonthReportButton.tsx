import { useState } from 'react'
import { Printer } from 'lucide-react'
import { ApiError } from '../../api/client'
import { openPdfInNewTab } from '../../api/documents'
import { currentYearMonth } from '../../lib/format'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

/** Monatsbericht (Druckansicht) eines Mitarbeiters für einen wählbaren Monat. */
export function MonthReportButton({ employeeId }: { employeeId: number }) {
  const [yearMonth, setYearMonth] = useState(currentYearMonth())
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function open() {
    const [year, month] = yearMonth.split('-').map(Number)
    setError(null)
    setLoading(true)
    try {
      await openPdfInNewTab(`/employees/${employeeId}/month-report?year=${year}&month=${month}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Bericht konnte nicht erstellt werden.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <Input type="month" className="h-8 w-40" value={yearMonth} onChange={(e) => e.target.value && setYearMonth(e.target.value)} />
        <Button variant="outline" size="sm" disabled={loading} onClick={() => void open()}>
          <Printer className="h-4 w-4" />
          {loading ? 'Erstelle…' : 'Monatsbericht'}
        </Button>
      </div>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}
