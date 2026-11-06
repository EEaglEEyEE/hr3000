import { useState, type FormEvent } from 'react'
import { Pencil, Plus, Trash2, Wand2 } from 'lucide-react'
import {
  type Holiday,
  useCreateHolidayMutation,
  useDeleteHolidayMutation,
  useHolidaysQuery,
  useImportHolidaysMutation,
} from '../api/queries/holidays'
import { useLocationsQuery } from '../api/queries/locations'
import { useSettingsQuery, type Bundesland } from '../api/queries/settings'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { formatDate } from '../lib/format'
import { BUNDESLAND_LABELS } from '../lib/labels'
import { HolidayEditDialog } from '../components/holidays/HolidayEditDialog'
import { LocationMultiSelect } from '../components/holidays/LocationMultiSelect'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

const USE_DEFAULT = '__default__'
const ALL_LOCATIONS = '__all__'

export function HolidaysPage() {
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [viewLocation, setViewLocation] = useState(ALL_LOCATIONS)
  const locationsQuery = useLocationsQuery()
  const locations = locationsQuery.data ?? []
  const locationNameById = new Map(locations.map((location) => [location.id, location.name]))
  const holidaysQuery = useHolidaysQuery(
    year,
    viewLocation === ALL_LOCATIONS ? undefined : Number(viewLocation),
  )
  const createHoliday = useCreateHolidayMutation()
  const deleteHoliday = useDeleteHolidayMutation()
  const importHolidays = useImportHolidaysMutation()
  const { isAdmin } = useAuth()
  const settingsQuery = useSettingsQuery(isAdmin)

  const [date, setDate] = useState('')
  const [name, setName] = useState('')
  const [createLocationIds, setCreateLocationIds] = useState<number[]>([])
  const [editingHoliday, setEditingHoliday] = useState<Holiday | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [importBundesland, setImportBundesland] = useState(USE_DEFAULT)
  const [importLocation, setImportLocation] = useState(ALL_LOCATIONS)
  const [importResult, setImportResult] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await createHoliday.mutateAsync({
        date,
        name,
        location_ids: createLocationIds,
      })
      setDate('')
      setName('')
      setCreateLocationIds([])
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'HOLIDAY_DATE_TAKEN'
          ? 'Für dieses Datum existiert für mindestens einen dieser Standorte bereits ein Feiertag.'
          : 'Speichern fehlgeschlagen.',
      )
    }
  }

  async function handleImport() {
    setImportError(null)
    setImportResult(null)
    try {
      const result = await importHolidays.mutateAsync({
        year,
        location_id: importLocation === ALL_LOCATIONS ? undefined : Number(importLocation),
        ...(importBundesland === USE_DEFAULT ? {} : { bundesland: importBundesland as Bundesland }),
      })
      setImportResult(
        `${result.imported.length} Feiertage importiert` +
          (result.skipped_existing > 0 ? `, ${result.skipped_existing} bereits vorhanden` : '') +
          '.',
      )
    } catch (err) {
      setImportError(
        err instanceof ApiError && err.code === 'BUNDESLAND_REQUIRED'
          ? 'Kein Bundesland ausgewählt und kein Standard-Bundesland in den Einstellungen hinterlegt.'
          : 'Import fehlgeschlagen.',
      )
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Feiertage</h1>
          <p className="text-sm text-slate-500">
            Werkskalender: An diesen Tagen entfällt für alle Mitarbeiter das Soll, genau wie an einem
            Abwesenheitstag.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setYear(year - 1)}>
            {year - 1}
          </Button>
          <span className="font-medium text-slate-900">{year}</span>
          <Button variant="outline" size="sm" onClick={() => setYear(year + 1)}>
            {year + 1}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 max-w-xs">
        <Label>Standort-Ansicht</Label>
        <Select value={viewLocation} onValueChange={setViewLocation}>
          <SelectTrigger>
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
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-1.5">
          <Label>Standort</Label>
          <Select value={importLocation} onValueChange={setImportLocation}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_LOCATIONS}>Alle Standorte (standortübergreifend)</SelectItem>
              {locations.map((location) => (
                <SelectItem key={location.id} value={String(location.id)}>
                  {location.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Bundesland</Label>
          <Select value={importBundesland} onValueChange={setImportBundesland}>
            <SelectTrigger className="w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={USE_DEFAULT}>
                {importLocation !== ALL_LOCATIONS
                  ? 'Bundesland des Standorts (bzw. Standard)'
                  : 'Standard-Bundesland'}{' '}
                {settingsQuery.data?.default_bundesland
                  ? `(Fallback: ${BUNDESLAND_LABELS[settingsQuery.data.default_bundesland]})`
                  : ''}
              </SelectItem>
              {Object.entries(BUNDESLAND_LABELS).map(([code, label]) => (
                <SelectItem key={code} value={code}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button type="button" variant="outline" disabled={importHolidays.isPending} onClick={handleImport}>
          <Wand2 className="h-4 w-4" />
          {importHolidays.isPending ? 'Importiere…' : `Feiertage ${year} automatisch importieren`}
        </Button>
        {importResult && <p className="text-sm text-emerald-600">{importResult}</p>}
        {importError && <p className="text-sm text-red-600">{importError}</p>}
      </div>

      {holidaysQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {holidaysQuery.isError && <p className="text-red-600">Feiertage konnten nicht geladen werden.</p>}

      {holidaysQuery.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Datum</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Standort</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {holidaysQuery.data.map((holiday) => (
              <TableRow key={holiday.id}>
                <TableCell>{formatDate(holiday.date)}</TableCell>
                <TableCell>{holiday.name}</TableCell>
                <TableCell>
                  {holiday.location_ids.length === 0 ? (
                    <Badge variant="info">Alle Standorte</Badge>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {holiday.location_ids.map((locationId) => (
                        <Badge key={locationId}>{locationNameById.get(locationId) ?? '–'}</Badge>
                      ))}
                    </div>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <Button variant="ghost" size="icon" title="Bearbeiten" onClick={() => setEditingHoliday(holiday)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" title="Löschen" onClick={() => {
                      if (window.confirm(`Feiertag "${holiday.name}" (${formatDate(holiday.date)}) wirklich löschen?`)) {
                        deleteHoliday.mutate(holiday.id)
                      }
                    }}>
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {holidaysQuery.data.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-slate-500">
                  Noch keine Feiertage für {year} angelegt.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <form className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white p-4" onSubmit={handleCreate}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="date">Datum</Label>
          <Input
            id="date"
            type="date"
            required
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            required
            placeholder="z.B. 1. Weihnachtstag"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Gilt für</Label>
          <LocationMultiSelect locations={locations} value={createLocationIds} onChange={setCreateLocationIds} />
        </div>
        <Button type="submit" disabled={createHoliday.isPending}>
          <Plus className="h-4 w-4" />
          Feiertag hinzufügen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <HolidayEditDialog
        holiday={editingHoliday}
        locations={locations}
        onOpenChange={(open) => !open && setEditingHoliday(undefined)}
      />
    </div>
  )
}
