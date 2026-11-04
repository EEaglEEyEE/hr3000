import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useChecklistTemplatesQuery,
  useDeleteChecklistMutation,
  useEmployeeChecklistsQuery,
  useStartChecklistMutation,
  useUpdateChecklistItemMutation,
} from '../../api/queries/checklists'
import { formatDate } from '../../lib/format'
import { CHECKLIST_KIND_LABELS, CHECKLIST_ROLE_LABELS } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

export function EmployeeChecklistsTab({ employeeId }: { employeeId: number }) {
  const checklistsQuery = useEmployeeChecklistsQuery(employeeId)
  const templatesQuery = useChecklistTemplatesQuery()
  const start = useStartChecklistMutation(employeeId)
  const update = useUpdateChecklistItemMutation()
  const remove = useDeleteChecklistMutation()
  const [templateId, setTemplateId] = useState('')
  const [anchorDate, setAnchorDate] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen.')
    }
  }

  const templates = templatesQuery.data ?? []
  const today = new Date().toISOString().slice(0, 10)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-72">
          <Select value={templateId} onValueChange={setTemplateId}>
            <SelectTrigger>
              <SelectValue placeholder={templates.length ? 'Vorlage wählen…' : 'Keine Vorlagen (siehe „Checklisten“)'} />
            </SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.id} value={String(t.id)}>
                  {CHECKLIST_KIND_LABELS[t.kind]}: {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-500" htmlFor="anchor">Stichtag (leer = Eintritt/Austritt)</label>
          <Input id="anchor" type="date" className="w-44" value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} />
        </div>
        <Button
          disabled={!templateId || start.isPending}
          onClick={() => void run(() => start.mutateAsync({ templateId: Number(templateId), anchorDate }))}
        >
          Checkliste starten
        </Button>
      </div>
      {message && <p className="text-sm text-red-600">{message}</p>}
      {checklistsQuery.data?.length === 0 && <p className="text-slate-500">Noch keine Checklisten für diesen Mitarbeiter.</p>}
      {checklistsQuery.data?.map((checklist) => {
        const doneCount = checklist.items.filter((i) => i.done).length
        return (
          <section key={checklist.id} className="rounded-md border border-slate-200 bg-white">
            <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div>
                <p className="font-medium text-slate-900">
                  {checklist.name} <Badge>{CHECKLIST_KIND_LABELS[checklist.kind]}</Badge>
                </p>
                <p className="text-xs text-slate-500">
                  Stichtag {formatDate(checklist.anchor_date)} · {doneCount} von {checklist.items.length} erledigt
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                title="Checkliste löschen"
                onClick={() => {
                  if (window.confirm('Checkliste wirklich löschen?')) void run(() => remove.mutateAsync(checklist.id))
                }}
              >
                <Trash2 className="h-4 w-4 text-red-600" />
              </Button>
            </header>
            <ul className="divide-y divide-slate-100">
              {checklist.items.map((item) => (
                <li key={item.id} className="flex items-start gap-3 px-4 py-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={item.done}
                    onChange={(e) => void run(() => update.mutateAsync({ checklistId: checklist.id, itemId: item.id, done: e.target.checked }))}
                  />
                  <div className="flex-1">
                    <p className={item.done ? 'text-slate-400 line-through' : 'text-slate-900'}>{item.title}</p>
                    <p className="text-xs text-slate-500">
                      {CHECKLIST_ROLE_LABELS[item.responsible]} · fällig {formatDate(item.due_date)}
                      {!item.done && item.due_date < today && <span className="ml-1 font-medium text-red-600">überfällig</span>}
                      {item.note && ` · ${item.note}`}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
