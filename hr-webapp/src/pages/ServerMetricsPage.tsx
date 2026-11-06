import { useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { useServerMetricsQuery, type ServerMetricsRange } from '../api/queries/serverMetrics'
import { MetricChart, type MetricPoint } from '../components/platform/MetricChart'
import { Button } from '../components/ui/button'

const RANGES: { value: ServerMetricsRange; label: string; hours: number }[] = [
  { value: '24h', label: '24 Std.', hours: 24 },
  { value: '7d', label: '7 Tage', hours: 24 * 7 },
  { value: '30d', label: '30 Tage', hours: 24 * 30 },
]

const GB = 1024 ** 3
const number = (value: number, digits = 0) =>
  value.toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const percent = (value: number) => `${number(value)} %`
const gigabytes = (bytes: number) => `${number(bytes / GB, bytes / GB < 10 ? 1 : 0)} GB`

function uptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return days > 0 ? `${days} Tage ${hours} Std.` : `${hours} Std. ${Math.floor((seconds % 3600) / 60)} Min.`
}

/** Kachel mit aktuellem Wert; ab 90 % Hinweis „hoch“ mit Symbol (nie Farbe allein). */
function Tile({ label, value, sub, high }: { label: string; value: string; sub?: ReactNode; high?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-slate-200 bg-white p-4">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-2xl font-semibold text-slate-900">{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
      {high && (
        <span className="mt-1 flex items-center gap-1 text-xs font-medium text-amber-700">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          hoch
        </span>
      )}
    </div>
  )
}

/** Super-Admin → „Server“: Auslastung des ganzen Servers mit Verlauf (gemessen jede Minute). */
export function ServerMetricsPage() {
  const [range, setRange] = useState<ServerMetricsRange>('24h')
  const query = useServerMetricsQuery(range)
  const data = query.data
  const hours = RANGES.find((r) => r.value === range)!.hours
  // Achse bis jetzt – der Verlauf endet beim letzten Abruf (jede Minute neu).
  const end = new Date(query.dataUpdatedAt || Date.now())
  const start = new Date(end.getTime() - hours * 3_600_000)
  const short = range === '24h'
  const timeLabel = (date: Date) =>
    short
      ? date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
      : date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  const tooltipTime = (date: Date) =>
    date.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

  const points = (data?.points ?? []).map((p) => ({ ...p, date: new Date(p.at) }))
  const series = (pick: (p: (typeof points)[number]) => number | null, detail?: (p: (typeof points)[number]) => string | undefined): MetricPoint[] =>
    points.map((p) => ({ at: p.date, value: pick(p), detail: detail?.(p) }))
  const current = data?.current
  const memoryPercent =
    current?.memory_used_bytes != null && current.memory_total_bytes ? (current.memory_used_bytes * 100) / current.memory_total_bytes : null
  const diskPercent =
    current?.disk_used_bytes != null && current.disk_total_bytes ? (current.disk_used_bytes * 100) / current.disk_total_bytes : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Server</h1>
          <p className="text-sm text-slate-500">
            Auslastung des ganzen Servers – alle Firmen und die Testumgebung zusammen. Gemessen wird jede Minute
            {data ? `, der Verlauf bleibt ${data.retention_days} Tage` : ''}.
          </p>
        </div>
        <div className="flex gap-1" role="group" aria-label="Zeitraum">
          {RANGES.map((r) => (
            <Button
              key={r.value}
              size="sm"
              variant={range === r.value ? 'default' : 'outline'}
              aria-pressed={range === r.value}
              onClick={() => setRange(r.value)}
            >
              {r.label}
            </Button>
          ))}
        </div>
      </div>

      {query.isLoading && <p className="text-slate-500">Lädt…</p>}
      {query.isError && <p className="text-red-600">Die Auslastung konnte nicht geladen werden.</p>}
      {data && data.interval_seconds === 0 && (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Die Messung ist abgeschaltet (SERVER_METRICS_INTERVAL_SECONDS=0) – es kommen keine neuen Werte hinzu.
        </p>
      )}

      {data && !current && (
        <p className="rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Dieser Server liefert keine Messwerte (kein /proc, z. B. bei lokaler Entwicklung auf macOS).
        </p>
      )}

      {current && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          <Tile
            label="CPU"
            value={current.cpu_percent != null ? percent(current.cpu_percent) : '–'}
            sub={current.cpu_count ? `${current.cpu_count} Kerne` : undefined}
            high={(current.cpu_percent ?? 0) >= 90}
          />
          <Tile
            label="Arbeitsspeicher"
            value={memoryPercent != null ? percent(memoryPercent) : '–'}
            sub={
              current.memory_used_bytes != null && current.memory_total_bytes
                ? `${gigabytes(current.memory_used_bytes)} von ${gigabytes(current.memory_total_bytes)}`
                : undefined
            }
            high={(memoryPercent ?? 0) >= 90}
          />
          <Tile
            label="Datenträger"
            value={diskPercent != null ? percent(diskPercent) : '–'}
            sub={
              current.disk_used_bytes != null && current.disk_total_bytes
                ? `${gigabytes(current.disk_used_bytes)} von ${gigabytes(current.disk_total_bytes)}`
                : undefined
            }
            high={(diskPercent ?? 0) >= 90}
          />
          <Tile
            label="Last (1 Min.)"
            value={current.load_1 != null ? number(current.load_1, 2) : '–'}
            sub={
              current.load_5 != null && current.load_15 != null
                ? `5 Min. ${number(current.load_5, 2)} · 15 Min. ${number(current.load_15, 2)}`
                : undefined
            }
            high={current.cpu_count != null && (current.load_1 ?? 0) >= current.cpu_count}
          />
          <Tile label="Läuft seit" value={current.uptime_seconds != null ? uptime(current.uptime_seconds) : '–'} />
        </div>
      )}

      {data && (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <MetricChart
            title="CPU (%)"
            points={series(
              (p) => p.cpu_percent,
              (p) => (p.cpu_max_percent != null ? `Spitze ${percent(p.cpu_max_percent)}` : undefined),
            )}
            start={start}
            end={end}
            bucketMinutes={data.bucket_minutes}
            intervalSeconds={data.interval_seconds}
            yMax={100}
            format={percent}
            timeLabel={timeLabel}
            tooltipTime={tooltipTime}
          />
          <MetricChart
            title="Arbeitsspeicher (%)"
            points={series((p) => p.memory_percent)}
            start={start}
            end={end}
            bucketMinutes={data.bucket_minutes}
            intervalSeconds={data.interval_seconds}
            yMax={100}
            format={percent}
            timeLabel={timeLabel}
            tooltipTime={tooltipTime}
          />
          <MetricChart
            title="Datenträger (%)"
            points={series((p) => p.disk_percent)}
            start={start}
            end={end}
            bucketMinutes={data.bucket_minutes}
            intervalSeconds={data.interval_seconds}
            yMax={100}
            format={percent}
            timeLabel={timeLabel}
            tooltipTime={tooltipTime}
          />
          <MetricChart
            title="Last (1 Min.)"
            points={series((p) => p.load_1)}
            start={start}
            end={end}
            bucketMinutes={data.bucket_minutes}
            intervalSeconds={data.interval_seconds}
            reference={current?.cpu_count ? { value: current.cpu_count, label: `${current.cpu_count} Kerne` } : undefined}
            format={(value) => number(value, value < 10 ? 1 : 0)}
            timeLabel={timeLabel}
            tooltipTime={tooltipTime}
          />
        </div>
      )}
      {data && data.points.length > 0 && (
        <p className="text-xs text-slate-500">
          Je Punkt der Mittelwert aus {data.bucket_minutes >= 60 ? `${data.bucket_minutes / 60} Std.` : `${data.bucket_minutes} Min.`}{' '}
          (CPU im Tooltip zusätzlich mit Spitzenwert). Lücken: keine Messwerte, z. B. während eines Neustarts.
        </p>
      )}
    </div>
  )
}
