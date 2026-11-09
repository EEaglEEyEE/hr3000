import { useState } from 'react'
import { Plus, QrCode, Trash2 } from 'lucide-react'
import { useDeleteDeviceMutation, useDevicesQuery, type Device } from '../api/queries/devices'
import { useLocationsQuery } from '../api/queries/locations'
import { DeviceFormDialog } from '../components/devices/DeviceFormDialog'
import { DeviceQrDialog } from '../components/devices/DeviceQrDialog'
import { MdmDistribution } from '../components/devices/MdmDistribution'
import { PendingEnrollments } from '../components/devices/PendingEnrollments'
import { Button } from '../components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'

function formatLastSeen(iso: string | null): string {
  if (!iso) return 'Noch nie verbunden'
  const withUtc = iso.endsWith('Z') ? iso : `${iso}Z`
  return new Date(withUtc).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

export function DevicesPage() {
  const locationsQuery = useLocationsQuery()
  const devicesQuery = useDevicesQuery()
  const deleteDevice = useDeleteDeviceMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingDevice, setEditingDevice] = useState<Device | undefined>(undefined)
  const [qrDevice, setQrDevice] = useState<Device | undefined>(undefined)

  const locations = locationsQuery.data ?? []
  const locationNameById = new Map(locations.map((location) => [location.id, location.name]))

  function openCreateDialog() {
    setEditingDevice(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(device: Device) {
    setEditingDevice(device)
    setDialogOpen(true)
  }

  function handleDelete(device: Device) {
    if (window.confirm(`Tablet "${device.name}" wirklich entfernen? Es kann sich danach nicht mehr anmelden.`)) {
      deleteDevice.mutate(device.id)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Tablets</h1>
        <Button onClick={openCreateDialog} disabled={locations.length === 0}>
          <Plus className="h-4 w-4" />
          Neues Tablet
        </Button>
      </div>

      {!locationsQuery.isLoading && locations.length === 0 && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Es ist noch kein Standort angelegt. Lege zuerst einen Standort an, um Tablets zu registrieren.
        </p>
      )}

      <PendingEnrollments locations={locations} devices={devicesQuery.data ?? []} />

      <Tabs defaultValue="devices">
        <TabsList>
          <TabsTrigger value="devices">Tablets</TabsTrigger>
          <TabsTrigger value="mdm">Verteilung per MDM</TabsTrigger>
        </TabsList>
        <TabsContent value="devices">
          {devicesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
          {devicesQuery.isError && <p className="text-red-600">Tablets konnten nicht geladen werden.</p>}

          {devicesQuery.data && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Standort</TableHead>
                  <TableHead>Gekoppelt</TableHead>
                  <TableHead>Zuletzt verbunden</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {devicesQuery.data.map((device) => (
                  <TableRow key={device.id}>
                    <TableCell>
                      {device.name}
                      {device.mdm_name && <span className="block text-xs text-slate-500">MDM: {device.mdm_name}</span>}
                    </TableCell>
                    <TableCell>{locationNameById.get(device.location_id) ?? '–'}</TableCell>
                    <TableCell className="text-sm">
                      {device.bound_at ? (
                        <span className="text-slate-600">an ein Tablet seit {formatLastSeen(device.bound_at)}</span>
                      ) : (
                        <span className="text-slate-400">noch kein Tablet</span>
                      )}
                      {device.rejected_at && (
                        <span className="mt-0.5 block text-xs font-medium text-red-600" title="Ein anderes Gerät hat versucht, sich mit diesem Zugang anzumelden">
                          Anderes Gerät abgewiesen: {formatLastSeen(device.rejected_at)}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-slate-500">{formatLastSeen(device.last_seen)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => setQrDevice(device)}>
                          <QrCode className="h-4 w-4" />
                          QR-Code
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => openEditDialog(device)}>
                          Bearbeiten
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => handleDelete(device)}>
                          <Trash2 className="h-4 w-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {devicesQuery.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-slate-500">
                      Keine Tablets registriert.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </TabsContent>
        <TabsContent value="mdm">
          <MdmDistribution locations={locations} />
        </TabsContent>
      </Tabs>

      <DeviceFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        device={editingDevice}
        locations={locations}
      />
      <DeviceQrDialog device={qrDevice} onClose={() => setQrDevice(undefined)} />
    </div>
  )
}
