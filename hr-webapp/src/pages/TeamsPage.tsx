import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEmployeesQuery } from '../api/queries/employees'
import { useLocationsQuery } from '../api/queries/locations'
import { useSupervisorTeamAssignmentsQuery } from '../api/queries/supervisorTeamAssignments'
import { useDeleteTeamMutation, useTeamsQuery, type Team } from '../api/queries/teams'
import { SupervisorAssignmentsDialog } from '../components/teams/SupervisorAssignmentsDialog'
import { TeamFormDialog } from '../components/teams/TeamFormDialog'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

export function TeamsPage() {
  const teamsQuery = useTeamsQuery()
  const locationsQuery = useLocationsQuery()
  const deleteTeam = useDeleteTeamMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTeam, setEditingTeam] = useState<Team | undefined>(undefined)
  const [supervisorsTeam, setSupervisorsTeam] = useState<Team | undefined>(undefined)

  const employeesQuery = useEmployeesQuery({ active: true })
  const assignmentsQuery = useSupervisorTeamAssignmentsQuery()
  const employeeName = new Map(
    (employeesQuery.data ?? []).map((employee) => [employee.id, `${employee.last_name}, ${employee.first_name}`]),
  )

  // Supervisor des Teams zuerst (auch wenn sie selbst einem anderen Team angehören), dann die Mitglieder.
  const supervisorIdsByTeam = new Map<number, Set<number>>()
  for (const assignment of assignmentsQuery.data ?? []) {
    if (assignment.employee_id === null || !employeeName.has(assignment.employee_id)) continue
    const ids = supervisorIdsByTeam.get(assignment.team_id) ?? new Set<number>()
    ids.add(assignment.employee_id)
    supervisorIdsByTeam.set(assignment.team_id, ids)
  }

  const membersByTeam = new Map<number, { id: number; name: string; supervisor: boolean }[]>()
  for (const [teamId, ids] of supervisorIdsByTeam) {
    membersByTeam.set(
      teamId,
      [...ids].map((id) => ({ id, name: employeeName.get(id)!, supervisor: true })),
    )
  }
  for (const employee of employeesQuery.data ?? []) {
    if (employee.team_id === null || supervisorIdsByTeam.get(employee.team_id)?.has(employee.id)) continue
    const list = membersByTeam.get(employee.team_id) ?? []
    list.push({ id: employee.id, name: `${employee.last_name}, ${employee.first_name}`, supervisor: false })
    membersByTeam.set(employee.team_id, list)
  }
  for (const list of membersByTeam.values()) {
    list.sort((a, b) => Number(b.supervisor) - Number(a.supervisor) || a.name.localeCompare(b.name))
  }
  const locations = locationsQuery.data ?? []
  const locationById = new Map(locations.map((location) => [location.id, location]))

  function openCreateDialog() {
    setEditingTeam(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(team: Team) {
    setEditingTeam(team)
    setDialogOpen(true)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Teams</h1>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4" />
          Neues Team
        </Button>
      </div>

      <p className="text-sm text-slate-500">
        Teams grenzen den Zugriff eines Teamleaders ein – er sieht ausschließlich Mitarbeiter der
        ihm zugeordneten Teams (siehe Mitarbeiterformular, Feld „Team“).
      </p>

      {teamsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {teamsQuery.isError && <p className="text-red-600">Teams konnten nicht geladen werden.</p>}

      {teamsQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Standort</TableHead>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {teamsQuery.data.map((team) => (
              <TableRow key={team.id}>
                <TableCell>{team.name}</TableCell>
                <TableCell className="text-slate-500">
                  {team.location_id ? locationById.get(team.location_id)?.name ?? '–' : 'Alle Standorte'}
                </TableCell>
                <TableCell className="max-w-md text-sm">
                  {(membersByTeam.get(team.id) ?? []).length === 0 ? (
                    <span className="text-slate-400">Keine</span>
                  ) : (
                    <>
                      <span className="font-medium">{membersByTeam.get(team.id)!.length}: </span>
                      {membersByTeam.get(team.id)!.map((member, index) => (
                        <span key={member.id}>
                          {index > 0 && ' · '}
                          <Link
                            className={
                              member.supervisor
                                ? 'font-semibold text-sky-800 underline underline-offset-2'
                                : 'text-sky-700 hover:underline'
                            }
                            title={member.supervisor ? 'Teamleader' : undefined}
                            to={`/employees/${member.id}`}
                          >
                            {member.name}
                          </Link>
                        </span>
                      ))}
                    </>
                  )}
                </TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setSupervisorsTeam(team)}>
                    Teamleader
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => openEditDialog(team)}>
                    Bearbeiten
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={deleteTeam.isPending}
                    onClick={() => deleteTeam.mutate(team.id)}
                  >
                    Löschen
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {teamsQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-slate-500">
                  Noch keine Teams angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <TeamFormDialog open={dialogOpen} onOpenChange={setDialogOpen} team={editingTeam} locations={locations} />
      <SupervisorAssignmentsDialog
        open={supervisorsTeam !== undefined}
        onOpenChange={(open) => !open && setSupervisorsTeam(undefined)}
        team={supervisorsTeam}
      />
    </div>
  )
}
