import { useNavigate } from 'react-router-dom'
import { useEmployeesQuery } from '../../api/queries/employees'
import { useDecideAbsenceMutation, usePendingAbsencesQuery } from '../../api/queries/absences'
import { useAbsenceTypeMap } from '../../api/queries/absenceTypes'
import { formatDate, formatHoursMinutes } from '../../lib/format'
import { ABSENCE_TYPE_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

/** „Zu klären“ → „Urlaubsanträge“: offene Anträge genehmigen oder ablehnen. */
export function PendingAbsencesPanel() {
  const absenceTypes = useAbsenceTypeMap()
  const navigate = useNavigate()
  const pendingQuery = usePendingAbsencesQuery()
  const employeesQuery = useEmployeesQuery()
  const decideAbsence = useDecideAbsenceMutation()

  const employeeById = new Map((employeesQuery.data ?? []).map((employee) => [employee.id, employee]))

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-500">
        Offene Anträge, die auf Genehmigung warten (je Abwesenheitsart unter Einstellungen → „Abwesenheitsarten“ mit
        „Genehmigung nötig“). Als Teamleiter/in sieht man hier nur Anträge aus den eigenen Teams.
      </p>

      {pendingQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {pendingQuery.isError && <p className="text-red-600">Anträge konnten nicht geladen werden.</p>}

      {pendingQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead>Art</TableHead>
              <TableHead>Von</TableHead>
              <TableHead>Bis</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pendingQuery.data.map((absence) => {
              const employee = employeeById.get(absence.employee_id)
              return (
                <TableRow key={absence.id}>
                  <TableCell
                    className="cursor-pointer"
                    onClick={() => navigate(`/employees/${absence.employee_id}`)}
                  >
                    {employee ? `${employee.first_name} ${employee.last_name}` : `#${absence.employee_id}`}
                  </TableCell>
                  <TableCell>
                    {absence.half_day && '½ '}
                    {absenceTypes.get(absence.absence_type_id ?? -1)?.name ?? ABSENCE_TYPE_LABELS[absence.type]}
                    {absence.duration_minutes != null && ` (${formatHoursMinutes(absence.duration_minutes)} Std.)`}
                  </TableCell>
                  <TableCell>{formatDate(absence.date_from)}</TableCell>
                  <TableCell>{formatDate(absence.date_to)}</TableCell>
                  <TableCell className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      disabled={decideAbsence.isPending}
                      onClick={() => decideAbsence.mutate({ absenceId: absence.id, payload: { approve: true } })}
                    >
                      Genehmigen
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={decideAbsence.isPending}
                      onClick={() => decideAbsence.mutate({ absenceId: absence.id, payload: { approve: false } })}
                    >
                      Ablehnen
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
            {pendingQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-slate-500">
                  Keine offenen Anträge.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
