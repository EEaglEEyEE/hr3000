import { useId, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

export interface MetricPoint {
  at: Date
  value: number | null
  /** Zusatz im Tooltip, z. B. „Spitze 85 %“ */
  detail?: string
}

interface MetricChartProps {
  title: string
  points: MetricPoint[]
  start: Date
  end: Date
  /** Abschnittsbreite – größere Abstände zwischen zwei Punkten werden als Lücke gezeichnet. */
  bucketMinutes: number
  /** Messabstand; bei großem Abstand werden Abschnitte ohne eigenen Messwert überbrückt. */
  intervalSeconds?: number
  /** Feste Obergrenze (z. B. 100 für Prozent); ohne Angabe aus den Werten. */
  yMax?: number
  /** Waagerechte Bezugslinie, z. B. die Zahl der CPU-Kerne bei der Last. */
  reference?: { value: number; label: string }
  format: (value: number) => string
  /** Kurze oder lange Zeitangabe an der x-Achse (24 Std. → Uhrzeit, sonst Datum). */
  timeLabel: (date: Date) => string
  tooltipTime: (date: Date) => string
}

// Zeichenfläche im viewBox-Maßstab; die Grafik skaliert gleichmäßig mit der Breite.
const W = 600
const H = 180
const M = { top: 12, right: 44, bottom: 24, left: 40 }
const PLOT_W = W - M.left - M.right
const PLOT_H = H - M.top - M.bottom

function niceMax(value: number): number {
  if (value <= 0) return 1
  const exponent = 10 ** Math.floor(Math.log10(value))
  const fraction = value / exponent
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10
  return nice * exponent
}

/** Einreihige Liniengrafik (eine Kennzahl, eine Achse) mit Fadenkreuz-Tooltip und Tabellenansicht. */
export function MetricChart({
  title,
  points,
  start,
  end,
  bucketMinutes,
  intervalSeconds = 60,
  yMax,
  reference,
  format,
  timeLabel,
  tooltipTime,
}: MetricChartProps) {
  const [active, setActive] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const titleId = useId()
  const values = points.map((p) => p.value).filter((v): v is number => v !== null)
  const top = yMax ?? niceMax(Math.max(...values, reference?.value ?? 0, 0.1) * 1.1)
  const span = Math.max(1, end.getTime() - start.getTime())
  const x = (date: Date) => M.left + ((date.getTime() - start.getTime()) / span) * PLOT_W
  const y = (value: number) => M.top + PLOT_H - (Math.min(value, top) / top) * PLOT_H

  // Linie mit Lücken, wo Messwerte fehlen (mehr als 1,5 Abschnitte bzw. 2,5 Messabstände)
  const gapMs = Math.max(bucketMinutes * 60_000 * 1.5, intervalSeconds * 1000 * 2.5)
  const segments: MetricPoint[][] = []
  let previous: MetricPoint | null = null
  for (const point of points) {
    if (point.value === null) {
      previous = null
      continue
    }
    if (previous && point.at.getTime() - previous.at.getTime() <= gapMs) segments[segments.length - 1].push(point)
    else segments.push([point])
    previous = point
  }
  const path = segments
    .filter((segment) => segment.length > 1)
    .map((segment) => segment.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.at).toFixed(1)},${y(p.value!).toFixed(1)}`).join(''))
    .join('')
  // Einzelne Abschnitte zwischen zwei Lücken als Punkt, sonst wären sie unsichtbar
  const singles = segments.filter((segment) => segment.length === 1).map((segment) => segment[0])
  const last = [...points].reverse().find((p) => p.value !== null)
  const ticks = [0, top / 2, top]
  const timeTicks = Array.from({ length: 5 }, (_, i) => new Date(start.getTime() + (span * i) / 4))
  const current = active !== null ? points[active] : null

  function nearest(clientX: number) {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || points.length === 0) return null
    const at = start.getTime() + (((clientX - rect.left) / rect.width) * W - M.left) / PLOT_W * span
    let best = 0
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(points[i].at.getTime() - at) < Math.abs(points[best].at.getTime() - at)) best = i
    }
    return best
  }

  function onKey(event: KeyboardEvent) {
    if (points.length === 0) return
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault()
      const step = event.key === 'ArrowRight' ? 1 : -1
      setActive((i) => Math.max(0, Math.min(points.length - 1, (i ?? points.length - 1) + step)))
    } else if (event.key === 'Escape') {
      setActive(null)
    }
  }

  return (
    <figure className="metric-chart flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4">
      <figcaption id={titleId} className="text-sm font-medium text-slate-800">
        {title}
      </figcaption>
      {values.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">Keine Messwerte im Zeitraum.</p>
      ) : (
        <div className="relative">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="w-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            role="img"
            aria-labelledby={titleId}
            tabIndex={0}
            onKeyDown={onKey}
            onPointerMove={(e: PointerEvent<SVGSVGElement>) => setActive(nearest(e.clientX))}
            onPointerLeave={() => setActive(null)}
            onBlur={() => setActive(null)}
          >
            {ticks.map((tick) => (
              <g key={tick}>
                <line x1={M.left} x2={M.left + PLOT_W} y1={y(tick)} y2={y(tick)} stroke="currentColor" className="text-slate-200" strokeWidth={1} />
                <text x={M.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[11px]">
                  {format(tick)}
                </text>
              </g>
            ))}
            {timeTicks.map((tick, i) => (
              <text
                key={tick.getTime()}
                x={x(tick)}
                y={H - 6}
                textAnchor={i === 0 ? 'start' : i === timeTicks.length - 1 ? 'end' : 'middle'}
                className="fill-slate-500 text-[11px]"
              >
                {timeLabel(tick)}
              </text>
            ))}
            {reference && reference.value <= top && (
              <g>
                <line x1={M.left} x2={M.left + PLOT_W} y1={y(reference.value)} y2={y(reference.value)} stroke="currentColor" className="text-slate-400" strokeWidth={1} />
                <text x={M.left + PLOT_W + 4} y={y(reference.value)} dy="0.32em" className="fill-slate-500 text-[10px]">
                  {reference.label}
                </text>
              </g>
            )}
            <path d={path} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {singles.map((p) => (
              <circle key={p.at.getTime()} cx={x(p.at)} cy={y(p.value!)} r={2.5} fill="var(--series-1)" />
            ))}
            {last && last.value !== null && active === null && (
              <text x={x(last.at) + 6} y={y(last.value)} dy="0.32em" className="fill-slate-700 text-[11px] font-medium">
                {format(last.value)}
              </text>
            )}
            {current && current.value !== null && (
              <g pointerEvents="none">
                <line x1={x(current.at)} x2={x(current.at)} y1={M.top} y2={M.top + PLOT_H} stroke="currentColor" className="text-slate-400" strokeWidth={1} />
                <circle cx={x(current.at)} cy={y(current.value)} r={5} fill="var(--series-1)" stroke="var(--color-white)" strokeWidth={2} />
              </g>
            )}
          </svg>
          {current && (
            <div
              role="status"
              className="pointer-events-none absolute top-0 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs shadow-sm"
              style={{
                left: `${(x(current.at) / W) * 100}%`,
                transform: x(current.at) > W / 2 ? 'translateX(calc(-100% - 8px))' : 'translateX(8px)',
              }}
            >
              <strong className="block text-slate-900">{current.value === null ? '–' : format(current.value)}</strong>
              <span className="block text-slate-500">{tooltipTime(current.at)}</span>
              {current.detail && <span className="block text-slate-500">{current.detail}</span>}
            </div>
          )}
        </div>
      )}
      {values.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-slate-500">Werte als Tabelle</summary>
          <div className="mt-2 max-h-64 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-slate-500">
                  <th className="py-1 font-medium">Zeit</th>
                  <th className="py-1 text-right font-medium">{title}</th>
                </tr>
              </thead>
              <tbody>
                {[...points].reverse().map((point) => (
                  <tr key={point.at.getTime()} className="border-t border-slate-100">
                    <td className="py-1 text-slate-600">{tooltipTime(point.at)}</td>
                    <td className="py-1 text-right text-slate-800">
                      {point.value === null ? '–' : format(point.value)}
                      {point.detail ? ` (${point.detail})` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  )
}
