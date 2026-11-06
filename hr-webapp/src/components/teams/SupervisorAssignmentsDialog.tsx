import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useEmployeesQuery } from '../../api/queries/employees'
import {
  useCreateSupervisorTeamAssignmentMutation,
  useDeleteSupervisorTeamAssignmentMutation,
  useSupervisorTeamAssignmentsQuery,
} from '../../api/queries/supervisorTeamAssignments'
import type { Team } from '../../api/queries/teams'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface SupervisorAssignmentsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  team?: Team
}

export function SupervisorAssignmentsDialog({ open, onOpenChange, team }: SupervisorAssignmentsDialogProps) {
  const assignmentsQuery = useSupervisorTeamAssignmentsQuery(team?.id)
  const employeesQuery = useEmployeesQuery({ active: true })
  const createAssignment = useCreateSupervisorTeamAssignmentMutation()
  const deleteAssignment = useDeleteSupervisorTeamAssignmentMutation()
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')

  const employees = employeesQuery.data ?? []
  const employeeById = new Map(employees.map((employee) => [employee.id, employee]))
  const assignedEmployeeIds = new Set(
    (assignmentsQuery.data ?? []).map((assignment) => assignment.employee_id).filter((id) => id !== null),
  )
  const assignableEmployees = employees.filter(
    (employee) => employee.hr_role === 'SUPERVISOR' && !assignedEmployeeIds.has(employee.id),
  )

  async function handleAdd() {
    if (!team || !selectedEmployeeId) return
    await createAssignment.mutateAsync({ team_id: team.id, employee_id: Number(selectedEmployeeId) })
    setSelectedEmployeeId('')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Teamleiter/innen – {team?.name}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <ul className="flex flex-col gap-2">
            {(assignmentsQuery.data ?? []).map((assignment) => {
              const employee =
                assignment.employee_id !== null ? employeeById.get(assignment.employee_id) : undefined
              return (
                <li
                  key={assignment.id}
                  className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm"
                >
                  <span>
                    {employee ? `${employee.first_name} ${employee.last_name}` : `Mitarbeiter #${assignment.employee_id}`}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => deleteAssignment.mutate(assignment.id)}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </li>
              )
            })}
            {assignmentsQuery.data?.length === 0 && (
              <li className="text-sm text-slate-500">Noch keine Teamleiter/in zugeordnet.</li>
            )}
          </ul>

          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Select value={selectedEmployeeId} onValueChange={setSelectedEmployeeId}>
                <SelectTrigger>
                  <SelectValue placeholder="Mitarbeiter mit Rolle Teamleiter/in wählen" />
                </SelectTrigger>
                <SelectContent>
                  {assignableEmployees.map((employee) => (
                    <SelectItem key={employee.id} value={String(employee.id)}>
                      {employee.first_name} {employee.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {assignableEmployees.length === 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  Kein Mitarbeiter mit Rolle „Teamleiter/in“ verfügbar (siehe HR-Berechtigung im
                  Mitarbeiterformular).
                </p>
              )}
            </div>
            <Button type="button" disabled={!selectedEmployeeId} onClick={handleAdd}>
              Hinzufügen
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Schließen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
