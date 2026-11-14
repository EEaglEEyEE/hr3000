import type { Device, DevicePresence, DevicePresenceList } from '../../api/queries/devices'

/** Zeitstempel des Servers (UTC ohne Zeitzonen-Angabe) als Datum in der Zeitzone des Browsers. */
function parseUtc(iso: string): Date {
  return new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
}

export function formatLastSeen(iso: string | null | undefined): string {
  if (!iso) return 'Noch nie verbunden'
  return parseUtc(iso).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

function punches(count: number): string {
  return count === 1 ? '1 Stempelung' : `${count} Stempelungen`
}

function Dot({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${className}`} />
}

/** Zeile über der Tabelle: wie viele Tablets gerade online sind und von wann die Auskunft stammt. */
export function PresenceSummary({ presence, failed, devices }: { presence: DevicePresenceList | undefined; failed: boolean; devices: Device[] }) {
  if (failed && !presence) {
    return (
      <p role="status" className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        Der Live-Status ist gerade nicht abrufbar. Angezeigt wird, wann sich jedes Tablet zuletzt gemeldet hat.
      </p>
    )
  }
  if (!presence) return null
  const paired = new Set(devices.filter((device) => device.bound_at).map((device) => device.id))
  const rows = presence.devices.filter((row) => paired.has(row.device_id))
  if (rows.length === 0) return null
  const online = rows.filter((row) => row.state === 'ONLINE').length
  const checking = rows.filter((row) => row.state === 'CHECKING').length
  return (
    <div role="status" aria-label="Live-Status" className="flex flex-col gap-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-slate-800">
        <Dot className={failed ? 'bg-amber-500' : 'animate-pulse bg-emerald-500'} />
        <span className="font-medium">
          {online} von {rows.length} {rows.length === 1 ? 'Tablet' : 'Tablets'} online
        </span>
        {checking > 0 && <span className="text-slate-600">· {checking === 1 ? '1 wird' : `${checking} werden`} noch abgefragt</span>}
        <span className="text-slate-500">
          · Stand {parseUtc(presence.checked_at).toLocaleTimeString('de-DE')} Uhr
          {failed && ' (letzte Abfrage fehlgeschlagen)'}
        </span>
      </p>
      <p className="text-xs text-slate-500">
        Solange diese Seite offen ist, melden sich die Tablets alle {presence.heartbeat_seconds} Sekunden, sonst alle 15 Minuten.
        Nach dem Öffnen kann es bis zu einer Minute dauern, bis jedes Tablet geantwortet hat.
      </p>
    </div>
  )
}

function QueueNote({ row, live }: { row: DevicePresence; live: boolean }) {
  const queued = row.queued_punches ?? 0
  const failed = row.failed_punches ?? 0
  if (queued === 0) return null
  return (
    <span className="mt-0.5 block text-xs font-medium text-amber-700">
      {live
        ? `${punches(queued)} ${queued === 1 ? 'wartet' : 'warten'} am Tablet auf die Übertragung`
        : `Bei der letzten Meldung ${queued === 1 ? 'wartete' : 'warteten'} dort ${punches(queued)} auf die Übertragung`}
      {failed > 0 && <span className="block text-red-600">davon {failed} vom Server abgelehnt – am Tablet prüfen</span>}
    </span>
  )
}

/** Zelle „Status“ eines Tablets. Ohne Live-Auskunft (lädt noch, Abfrage gescheitert) wie bisher nur der
 * letzte Kontakt. */
export function PresenceCell({ device, row }: { device: Device; row: DevicePresence | undefined }) {
  if (!device.bound_at) {
    return <span className="text-slate-400">Kein Gerät gekoppelt</span>
  }
  if (!row) {
    return <span className="text-slate-500">Zuletzt gemeldet: {formatLastSeen(device.last_seen)}</span>
  }
  const lastSeen = row.last_seen ? `zuletzt gemeldet ${formatLastSeen(row.last_seen)}` : 'noch nie gemeldet'
  if (row.state === 'ONLINE') {
    return (
      <div>
        <span className="flex items-center gap-2 font-medium text-emerald-700">
          <Dot className="bg-emerald-500" />
          Online
        </span>
        <QueueNote row={row} live />
      </div>
    )
  }
  if (row.state === 'CHECKING') {
    return (
      <div>
        <span className="flex items-center gap-2 text-slate-600">
          <Dot className="animate-pulse bg-slate-400" />
          Wird abgefragt …
        </span>
        <span className="mt-0.5 block text-xs text-slate-500">{lastSeen}</span>
      </div>
    )
  }
  return (
    <div>
      {row.screen_off ? (
        <span className="flex items-center gap-2 font-medium text-slate-600" title="Außerhalb der Bildschirmzeiten hält das Tablet den Bildschirm nicht wach und schläft – das ist kein Ausfall.">
          <Dot className="bg-slate-400" />
          Offline – außerhalb der Bildschirmzeiten
        </span>
      ) : (
        <span className="flex items-center gap-2 font-medium text-red-700">
          <Dot className="bg-red-500" />
          Offline
        </span>
      )}
      <span className="mt-0.5 block text-xs text-slate-500">{lastSeen}</span>
      <QueueNote row={row} live={false} />
    </div>
  )
}
