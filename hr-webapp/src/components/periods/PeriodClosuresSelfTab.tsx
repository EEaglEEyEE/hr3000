import { useState } from 'react'
import { ApiError } from '../../api/client'
import { downloadDocument, useDocumentsQuery } from '../../api/documents'
import {
  useConfirmPeriodMutation,
  useDisputePeriodMutation,
  useEmployeePeriodClosuresQuery,
  type PeriodClosure,
} from '../../api/queries/periodClosures'
import { formatMinutesAsHours } from '../../lib/format'
import { PERIOD_STATUS_LABELS, PERIOD_STATUS_VARIANT } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

/** "Mein Bereich": Monatsnachweise prüfen, bestätigen oder beanstanden. */
export function PeriodClosuresSelfTab({ employeeId }: { employeeId: number }) {
  const closuresQuery = useEmployeePeriodClosuresQuery(employeeId)
  const documentsQuery = useDocumentsQuery(employeeId)
  const confirm = useConfirmPeriodMutation()
  const dispute = useDisputePeriodMutation()
  const [disputing, setDisputing] = useState<PeriodClosure | null>(null)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen.')
    }
  }

  const closures = closuresQuery.data ?? []
  const documents = documentsQuery.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500">
        Bitte prüfe deinen Monatsnachweis und bestätige ihn oder widersprich mit einer kurzen Begründung. Nach deiner
        Bestätigung kann der Monat nicht mehr geändert werden.
      </p>
      {message && <p className="text-sm text-red-600">{message}</p>}
      {closuresQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Monat</TableHead>
            <TableHead>Soll</TableHead>
            <TableHead>Ist</TableHead>
            <TableHead>Saldo</TableHead>
            <TableHead>Status</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {closures.map((closure) => {
            const document = documents.find((d) => d.id === closure.document_id)
            return (
              <TableRow key={closure.id}>
                <TableCell>
                  {MONTHS[closure.month - 1]} {closure.year}
                </TableCell>
                <TableCell>{formatMinutesAsHours(closure.target_minutes).replace('+', '')}</TableCell>
                <TableCell>{formatMinutesAsHours(closure.actual_minutes).replace('+', '')}</TableCell>
                <TableCell>{formatMinutesAsHours(closure.delta_minutes)}</TableCell>
                <TableCell>
                  <Badge variant={PERIOD_STATUS_VARIANT[closure.status]}>{PERIOD_STATUS_LABELS[closure.status]}</Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  {document && (
                    <Button size="sm" variant="outline" onClick={() => void run(() => downloadDocument(employeeId, document))}>
                      PDF ansehen
                    </Button>
                  )}{' '}
                  {closure.status === 'SUBMITTED' && (
                    <>
                      <Button
                        size="sm"
                        disabled={confirm.isPending}
                        onClick={() => void run(() => confirm.mutateAsync({ employeeId, year: closure.year, month: closure.month }))}
                      >
                        Bestätigen
                      </Button>{' '}
                      <Button size="sm" variant="outline" onClick={() => { setDisputing(closure); setReason('') }}>
                        Widersprechen
                      </Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
          {closures.length === 0 && !closuresQuery.isLoading && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-slate-500">
                Noch keine Monatsnachweise vorhanden.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {disputing && (
        <form
          className="flex max-w-xl flex-col gap-2 rounded-md border border-slate-200 bg-white p-4"
          onSubmit={(event) => {
            event.preventDefault()
            void run(async () => {
              await dispute.mutateAsync({ employeeId, year: disputing.year, month: disputing.month, reason })
              setDisputing(null)
            })
          }}
        >
          <p className="text-sm font-medium text-slate-900">
            Widerspruch zu {MONTHS[disputing.month - 1]} {disputing.year}
          </p>
          <Input required minLength={3} maxLength={500} placeholder="Was stimmt nicht? (z. B. fehlende Stempelung am 12.)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" disabled={dispute.isPending}>Widerspruch senden</Button>
            <Button type="button" variant="outline" onClick={() => setDisputing(null)}>Abbrechen</Button>
          </div>
        </form>
      )}
    </div>
  )
}
