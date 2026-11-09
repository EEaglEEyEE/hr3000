import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Upload } from 'lucide-react'
import { useDepartmentsQuery } from '../api/queries/departments'
import { useEmployeesQuery, type HrRole } from '../api/queries/employees'
import { departmentPaths } from '../lib/departments'
import { EMPLOYMENT_STATUS_LABELS } from '../lib/labels'
import { PlanNotice } from '../components/plan/PlanNotice'
import { useLocationsQuery } from '../api/queries/locations'
import { useAuth } from '../auth/AuthContext'
import { EmployeeFormDialog } from '../components/employees/EmployeeFormDialog'
import { Badge, type BadgeProps } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const ALL_LOCATIONS = '__all__'
const ALL_DEPARTMENTS = '__all__'
const NO_DEPARTMENT = '__none__'

const HR_ROLE_LABELS: Record<HrRole, string> = {
  HR: 'HR',
  SUPERVISOR: 'Führungskraft',
  ADMIN: 'Admin',
  SUPER_ADMIN: 'Super-Admin',
}

const HR_ROLE_BADGE_VARIANT: Record<HrRole, BadgeProps['variant']> = {
  HR: 'info',
  SUPERVISOR: 'violet',
  ADMIN: 'warning',
  SUPER_ADMIN: 'danger',
}

export function EmployeesPage() {
  // Supervisor: nur ansehen (kein Anlegen/Bearbeiten), siehe Backend-Rechte.
  const { isFullHr } = useAuth()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [locationFilter, setLocationFilter] = useState(ALL_LOCATIONS)
  const [departmentFilter, setDepartmentFilter] = useState(ALL_DEPARTMENTS)
  const locationsQuery = useLocationsQuery()
  const departmentsQuery = useDepartmentsQuery()
  const employeesQuery = useEmployeesQuery({
    search,
    active: showInactive ? undefined : true,
    locationId: locationFilter === ALL_LOCATIONS ? undefined : Number(locationFilter),
    departmentId: departmentFilter === ALL_DEPARTMENTS || departmentFilter === NO_DEPARTMENT ? undefined : Number(departmentFilter),
    withoutDepartment: departmentFilter === NO_DEPARTMENT,
  })
  const [dialogOpen, setDialogOpen] = useState(false)

  const locations = locationsQuery.data ?? []
  const locationNameById = new Map(locations.map((location) => [location.id, location.name]))
  const departments = departmentsQuery.data ?? []
  // Pfad wie „Vertrieb › Innendienst“ – sortiert, damit Unterabteilungen unter ihrer Abteilung stehen
  const departmentPath = departmentPaths(departments)
  const departmentOptions = [...departments].sort((a, b) => departmentPath.get(a.id)!.localeCompare(departmentPath.get(b.id)!, 'de'))
  const departmentNameById = new Map(departments.map((department) => [department.id, department.name]))

  function openCreateDialog() {
    setDialogOpen(true)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Mitarbeiter</h1>
        {isFullHr && (
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate('/mitarbeiter-import')}>
              <Upload className="h-4 w-4" />
              CSV-Import
            </Button>
            <Button onClick={openCreateDialog} disabled={locations.length === 0}>
              <Plus className="h-4 w-4" />
              Neuer Mitarbeiter
            </Button>
          </div>
        )}
      </div>

      {isFullHr && <PlanNotice />}

      {!locationsQuery.isLoading && locations.length === 0 && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Es ist noch kein Standort angelegt.{' '}
          <Link to="/einstellungen/standorte" className="underline">
            Standort anlegen
          </Link>
          , um Mitarbeiter erfassen zu können.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Suche nach Name oder Personalnummer…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="max-w-sm"
        />
        <Select value={locationFilter} onValueChange={setLocationFilter}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_LOCATIONS}>Alle Standorte</SelectItem>
            {locations.map((location) => (
              <SelectItem key={location.id} value={String(location.id)}>
                {location.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {departments.length > 0 && (
          <Select value={departmentFilter} onValueChange={setDepartmentFilter}>
            <SelectTrigger className="w-56 max-w-full" aria-label="Abteilung">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_DEPARTMENTS}>Alle Abteilungen</SelectItem>
              <SelectItem value={NO_DEPARTMENT}>Ohne Abteilung</SelectItem>
              {departmentOptions.map((department) => (
                <SelectItem key={department.id} value={String(department.id)}>
                  {departmentPath.get(department.id)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(event) => setShowInactive(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Auch inaktive anzeigen
        </label>
      </div>

      {employeesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {employeesQuery.isError && <p className="text-red-600">Mitarbeiter konnten nicht geladen werden.</p>}

      {employeesQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Personalnummer</TableHead>
              <TableHead>Standort</TableHead>
              <TableHead>Abteilung</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Berechtigung</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {employeesQuery.data.map((employee) => (
              <TableRow key={employee.id} className="cursor-pointer" onClick={() => navigate(`/employees/${employee.id}`)}>
                <TableCell>
                  {employee.last_name}, {employee.first_name}
                  {employee.employment_status && employee.employment_status !== 'ACTIVE' && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                      {EMPLOYMENT_STATUS_LABELS[employee.employment_status]}
                    </span>
                  )}
                </TableCell>
                <TableCell>{employee.employee_number}</TableCell>
                <TableCell>{locationNameById.get(employee.location_id) ?? '–'}</TableCell>
                <TableCell title={employee.department_id ? departmentPath.get(employee.department_id) : undefined}>
                  {employee.department_id ? (departmentNameById.get(employee.department_id) ?? '–') : <span className="text-slate-400">–</span>}
                </TableCell>
                <TableCell>
                  <Badge variant={employee.active ? 'success' : 'default'}>
                    {employee.active ? 'Aktiv' : 'Inaktiv'}
                  </Badge>
                </TableCell>
                <TableCell>
                  {employee.hr_role ? (
                    <Badge variant={HR_ROLE_BADGE_VARIANT[employee.hr_role]}>
                      {HR_ROLE_LABELS[employee.hr_role]}
                    </Badge>
                  ) : (
                    <span className="text-slate-400">–</span>
                  )}
                </TableCell>
                <TableCell>
                  {isFullHr && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation()
                        navigate(`/employees/${employee.id}?reiter=einstellungen`)
                      }}
                    >
                      Bearbeiten
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {employeesQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-slate-500">
                  Keine Mitarbeiter gefunden.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <EmployeeFormDialog open={dialogOpen} onOpenChange={setDialogOpen} locations={locations} />
    </div>
  )
}
