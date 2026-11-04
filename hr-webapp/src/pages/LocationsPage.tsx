import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useLocationsQuery, type Location } from '../api/queries/locations'
import { LocationFormDialog } from '../components/locations/LocationFormDialog'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

export function LocationsPage() {
  const locationsQuery = useLocationsQuery()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingLocation, setEditingLocation] = useState<Location | undefined>(undefined)

  function openCreateDialog() {
    setEditingLocation(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(location: Location) {
    setEditingLocation(location)
    setDialogOpen(true)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Standorte</h1>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4" />
          Neuer Standort
        </Button>
      </div>

      {locationsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {locationsQuery.isError && <p className="text-red-600">Standorte konnten nicht geladen werden.</p>}

      {locationsQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Zeitzone</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {locationsQuery.data.map((location) => (
              <TableRow key={location.id}>
                <TableCell>{location.name}</TableCell>
                <TableCell>{location.timezone}</TableCell>
                <TableCell className="text-right">
                  <Button variant="outline" size="sm" onClick={() => openEditDialog(location)}>
                    Bearbeiten
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {locationsQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-slate-500">
                  Noch keine Standorte angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <LocationFormDialog open={dialogOpen} onOpenChange={setDialogOpen} location={editingLocation} />
    </div>
  )
}
