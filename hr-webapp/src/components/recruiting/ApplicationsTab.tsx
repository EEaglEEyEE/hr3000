import { useMemo, useState } from 'react'
import { Columns3, List, Plus } from 'lucide-react'
import { useApplicationsQuery, useDueForDeletionQuery, useJobsQuery, type ApplicationItem } from '../../api/queries/recruiting'
import { formatDate } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { ApplicationDialog } from './ApplicationDialog'
import { NewApplicationDialog } from './NewApplicationDialog'
import { SELECT_CLASS, SOURCE_LABELS, STAGES, STAGE_LABELS, STAGE_VARIANT } from './labels'

function Rating({ item }: { item: ApplicationItem }) {
  if (item.average_rating == null) return <span className="text-slate-400">–</span>
  return (
    <span title={`${item.rating_count} Bewertung(en)`}>
      ★ {item.average_rating.toLocaleString('de-DE')} <span className="text-xs text-slate-400">({item.rating_count})</span>
    </span>
  )
}

function ListView({ items, onOpen }: { items: ApplicationItem[]; onOpen: (id: number) => void }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Stelle</TableHead>
            <TableHead>Phase</TableHead>
            <TableHead>Eingang</TableHead>
            <TableHead>Quelle</TableHead>
            <TableHead>Bewertung</TableHead>
            <TableHead>Löschung am</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.id}>
              <TableCell>
                <button type="button" className="font-medium text-slate-900 underline" onClick={() => onOpen(item.id)}>
                  {item.first_name} {item.last_name}
                </button>
                {item.talent_pool && <Badge variant="info" className="ml-2">Talentpool</Badge>}
              </TableCell>
              <TableCell className="text-sm text-slate-600">{item.job_title}</TableCell>
              <TableCell>
                <Badge variant={STAGE_VARIANT[item.stage]}>{STAGE_LABELS[item.stage]}</Badge>
              </TableCell>
              <TableCell>{formatDate(item.created_at)}</TableCell>
              <TableCell className="text-sm text-slate-600">{SOURCE_LABELS[item.source]}</TableCell>
              <TableCell>
                <Rating item={item} />
              </TableCell>
              <TableCell>{item.delete_on ? formatDate(item.delete_on) : '–'}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** Spaltenansicht nach Phase (Desktop nebeneinander, mobil untereinander). */
function BoardView({ items, onOpen }: { items: ApplicationItem[]; onOpen: (id: number) => void }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
      {STAGES.map((stage) => {
        const column = items.filter((item) => item.stage === stage)
        return (
          <section key={stage} aria-label={STAGE_LABELS[stage]} className="flex flex-col gap-2 rounded-md bg-slate-50 p-2">
            <h3 className="flex items-center justify-between text-sm font-semibold text-slate-700">
              {STAGE_LABELS[stage]} <span className="text-xs font-normal text-slate-500">{column.length}</span>
            </h3>
            {column.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onOpen(item.id)}
                className="flex flex-col gap-0.5 rounded-md border border-slate-200 bg-white p-2 text-left text-sm hover:border-slate-400"
              >
                <span className="font-medium text-slate-900">
                  {item.first_name} {item.last_name}
                </span>
                <span className="text-xs text-slate-500">{item.job_title}</span>
                <span className="text-xs text-slate-500">
                  {formatDate(item.created_at)} · <Rating item={item} />
                </span>
              </button>
            ))}
          </section>
        )
      })}
    </div>
  )
}

function DueForDeletion({ onOpen }: { onOpen: (id: number) => void }) {
  const due = useDueForDeletionQuery()
  if (!due.data || due.data.length === 0) return null
  return (
    <div className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
      <p className="text-sm font-medium text-amber-900">Zur Löschung fällig (nächste 30 Tage)</p>
      <p className="text-xs text-amber-800">
        Abgelehnte und zurückgezogene Bewerbungen werden nach Ablauf der Frist automatisch gelöscht. Übrig bleibt nur eine
        anonyme Zählung je Stelle.
      </p>
      <ul className="flex flex-col gap-1 text-sm">
        {due.data.map((item) => (
          <li key={item.id}>
            <button type="button" className="underline" onClick={() => onOpen(item.id)}>
              {item.first_name} {item.last_name}
            </button>{' '}
            ({item.job_title}) – {item.delete_on ? formatDate(item.delete_on) : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Reiter „Bewerbungen“: Liste oder Spalten nach Phase, Filter nach Stelle. */
export function ApplicationsTab({
  canManage,
  canSeeSalary,
  jobId,
  onJobChange,
}: {
  canManage: boolean
  canSeeSalary: boolean
  jobId: number | null
  onJobChange: (jobId: number | null) => void
}) {
  const jobs = useJobsQuery()
  const applications = useApplicationsQuery(jobId ?? undefined)
  const [view, setView] = useState<'list' | 'board'>('board')
  const [openId, setOpenId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const items = applications.data ?? []
  const jobsById = useMemo(() => new Map((jobs.data ?? []).map((job) => [job.id, job])), [jobs.data])
  const openJob = openId !== null ? jobsById.get(items.find((item) => item.id === openId)?.job_id ?? -1) : undefined

  return (
    <div className="flex flex-col gap-3">
      {canManage && <DueForDeletion onOpen={setOpenId} />}
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Stelle"
          className={cn(SELECT_CLASS, 'w-64 max-w-full')}
          value={jobId ?? ''}
          onChange={(e) => onJobChange(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Alle Stellen</option>
          {(jobs.data ?? []).map((job) => (
            <option key={job.id} value={job.id}>
              {job.title}
            </option>
          ))}
        </select>
        <div className="inline-flex rounded-md border border-slate-300" role="group" aria-label="Ansicht">
          <Button variant={view === 'board' ? 'default' : 'ghost'} size="sm" aria-pressed={view === 'board'} onClick={() => setView('board')}>
            <Columns3 className="h-4 w-4" /> Spalten
          </Button>
          <Button variant={view === 'list' ? 'default' : 'ghost'} size="sm" aria-pressed={view === 'list'} onClick={() => setView('list')}>
            <List className="h-4 w-4" /> Liste
          </Button>
        </div>
        {canManage && (jobs.data ?? []).length > 0 && (
          <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> Bewerbung erfassen
          </Button>
        )}
      </div>
      {applications.isLoading && <p className="text-sm text-slate-500">Lädt…</p>}
      {applications.data && items.length === 0 && <p className="text-sm text-slate-500">Keine Bewerbungen.</p>}
      {items.length > 0 && (view === 'list' ? <ListView items={items} onOpen={setOpenId} /> : <BoardView items={items} onOpen={setOpenId} />)}
      {openId !== null && (
        <ApplicationDialog
          applicationId={openId}
          departmentId={openJob?.department_id}
          locationId={openJob?.location_id}
          onClose={() => setOpenId(null)}
        />
      )}
      {creating && (
        <NewApplicationDialog
          jobs={jobs.data ?? []}
          defaultJobId={jobId ?? undefined}
          canSeeSalary={canSeeSalary}
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false)
            setOpenId(created.id)
          }}
        />
      )}
    </div>
  )
}
