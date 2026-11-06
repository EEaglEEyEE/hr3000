import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useLocationsQuery } from '../api/queries/locations'
import { useDeleteShiftTemplateMutation, useShiftTemplatesQuery, type ShiftTemplate } from '../api/queries/shiftTemplates'
import { ShiftTemplateFormDialog } from '../components/shiftplanning/ShiftTemplateFormDialog'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

export function ShiftTemplatesPage() {
  const templatesQuery = useShiftTemplatesQuery()
  const locationsQuery = useLocationsQuery()
  const deleteTemplate = useDeleteShiftTemplateMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<ShiftTemplate | undefined>(undefined)

  const locations = locationsQuery.data ?? []
  const locationById = new Map(locations.map((location) => [location.id, location]))

  function openCreateDialog() {
    setEditingTemplate(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(template: ShiftTemplate) {
    setEditingTemplate(template)
    setDialogOpen(true)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Schichtvorlagen</h1>
        <Button onClick={openCreateDialog}>
          <Plus className="h-4 w-4" />
          Neue Schichtvorlage
        </Button>
      </div>

      <p className="text-sm text-slate-500">
        Wiederverwendbare Schichten (z.B. „Frühschicht“) mit Uhrzeiten: im Arbeitszeitmodell eines
        Mitarbeiters als feste Uhrzeiten (Reiter „Arbeitszeit“) oder als Schicht an einzelnen Tagen
        (Schichtplan-Kalender bzw. Reiter „Arbeitszeit“ → „Schichtplanung“). Das Soll pro Schichttag gilt nur an geplanten
        Schichttagen.
      </p>

      {templatesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {templatesQuery.isError && <p className="text-red-600">Vorlagen konnten nicht geladen werden.</p>}

      {templatesQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Zeit</TableHead>
              <TableHead>Soll</TableHead>
              <TableHead>Standort</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {templatesQuery.data.map((template) => (
              <TableRow key={template.id}>
                <TableCell>{template.name}</TableCell>
                <TableCell className="text-slate-500">
                  {template.start_time && template.end_time
                    ? `${template.start_time.slice(0, 5)}–${template.end_time.slice(0, 5)}`
                    : '–'}
                </TableCell>
                <TableCell>
                  {Math.round(template.target_minutes / 6) / 10} h
                  {template.target_period === 'WEEKLY' && ' / Woche'}
                  {template.target_period === 'MONTHLY' && ' / Monat'}
                </TableCell>
                <TableCell className="text-slate-500">
                  {template.location_id ? locationById.get(template.location_id)?.name ?? '–' : 'Alle'}
                </TableCell>
                <TableCell className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => openEditDialog(template)}>
                    Bearbeiten
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={deleteTemplate.isPending}
                    onClick={() => deleteTemplate.mutate(template.id)}
                  >
                    Löschen
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {templatesQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-slate-500">
                  Noch keine Schichtvorlage angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <ShiftTemplateFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        template={editingTemplate}
        locations={locations}
      />
    </div>
  )
}
