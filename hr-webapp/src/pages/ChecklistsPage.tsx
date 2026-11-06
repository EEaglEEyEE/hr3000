import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  useChecklistTemplatesQuery,
  useCreateDefaultTemplatesMutation,
  useCreateTemplateMutation,
  useDeleteTemplateMutation,
  useOpenChecklistItemsQuery,
  useUpdateChecklistItemMutation,
  type ChecklistRole,
  type TemplateItemInput,
} from '../api/queries/checklists'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { formatDate } from '../lib/format'
import { CHECKLIST_KIND_LABELS, CHECKLIST_ROLE_LABELS } from '../lib/labels'

export function ChecklistsPage() {
  const openItems = useOpenChecklistItemsQuery()
  const templates = useChecklistTemplatesQuery()
  const update = useUpdateChecklistItemMutation()
  const createDefaults = useCreateDefaultTemplatesMutation()
  const removeTemplate = useDeleteTemplateMutation()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Aktion fehlgeschlagen.')
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <h1 className="text-lg font-semibold text-slate-900">Offene Aufgaben (On-/Offboarding)</h1>
        <p className="text-sm text-slate-500">
          Checklisten werden am Mitarbeiter gestartet (Reiter „Personalakte“ → „Checklisten“). Hier siehst du alle offenen Aufgaben nach Fälligkeit.
        </p>
        {message && <p className="text-sm text-red-600">{message}</p>}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead />
              <TableHead>Aufgabe</TableHead>
              <TableHead>Mitarbeiter</TableHead>
              <TableHead>Zuständig</TableHead>
              <TableHead>Fällig</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {openItems.data?.map((item) => (
              <TableRow key={item.item_id}>
                <TableCell>
                  <input
                    type="checkbox"
                    title="Als erledigt markieren"
                    onChange={() => void run(() => update.mutateAsync({ checklistId: item.checklist_id, itemId: item.item_id, done: true }))}
                  />
                </TableCell>
                <TableCell>
                  {item.title} <Badge>{CHECKLIST_KIND_LABELS[item.kind]}</Badge>
                </TableCell>
                <TableCell>
                  <Link className="text-sky-700 hover:underline" to={`/employees/${item.employee_id}`}>
                    {item.last_name}, {item.first_name}
                  </Link>
                </TableCell>
                <TableCell>{CHECKLIST_ROLE_LABELS[item.responsible]}</TableCell>
                <TableCell>
                  {formatDate(item.due_date)} {item.overdue && <Badge variant="danger">überfällig</Badge>}
                </TableCell>
              </TableRow>
            ))}
            {openItems.data?.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-slate-500">
                  Keine offenen Aufgaben.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-900">Vorlagen</h2>
          <div className="flex flex-wrap gap-2">
            {(templates.data?.length ?? 0) === 0 && (
              <Button variant="outline" onClick={() => void run(() => createDefaults.mutateAsync())}>
                Standardvorlagen anlegen
              </Button>
            )}
            <Button onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4" />
              Neue Vorlage
            </Button>
          </div>
        </div>
        {templates.data?.map((template) => (
          <div key={template.id} className="rounded-md border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-slate-900">
                {template.name} <Badge>{CHECKLIST_KIND_LABELS[template.kind]}</Badge>
              </p>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  if (window.confirm(`Vorlage "${template.name}" löschen? Bereits gestartete Checklisten bleiben bestehen.`)) {
                    void run(() => removeTemplate.mutateAsync(template.id))
                  }
                }}
              >
                <Trash2 className="h-4 w-4 text-red-600" />
              </Button>
            </div>
            <ol className="mt-2 list-decimal pl-5 text-sm text-slate-700">
              {template.items.map((item) => (
                <li key={item.id}>
                  {item.title}{' '}
                  <span className="text-xs text-slate-500">
                    ({CHECKLIST_ROLE_LABELS[item.responsible]}, {item.due_offset_days >= 0 ? '+' : ''}
                    {item.due_offset_days} Tage)
                  </span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </section>
      <TemplateDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}

function TemplateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreateTemplateMutation()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'ONBOARDING' | 'OFFBOARDING'>('ONBOARDING')
  const [items, setItems] = useState<TemplateItemInput[]>([{ title: '', responsible: 'HR', due_offset_days: 0 }])
  const [error, setError] = useState<string | null>(null)

  function patchItem(index: number, patch: Partial<TemplateItemInput>) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const filled = items.filter((item) => item.title.trim())
    if (filled.length === 0) {
      setError('Mindestens eine Aufgabe angeben.')
      return
    }
    try {
      await create.mutateAsync({ kind, name: name.trim(), items: filled.map((i) => ({ ...i, title: i.title.trim() })) })
      setName('')
      setItems([{ title: '', responsible: 'HR', due_offset_days: 0 }])
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Bitte Angaben prüfen (Titel max. 200 Zeichen).')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Neue Checklisten-Vorlage</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tpl_name">Name</Label>
              <Input id="tpl_name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Art</Label>
              <Select value={kind} onValueChange={(value) => setKind(value as typeof kind)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CHECKLIST_KIND_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Aufgaben (Fälligkeit in Tagen relativ zum Ein-/Austrittsdatum)</Label>
            {items.map((item, index) => (
              <div key={index} className="grid grid-cols-[1fr_8rem_5rem_2rem] gap-2">
                <Input placeholder="Aufgabe" maxLength={200} value={item.title} onChange={(e) => patchItem(index, { title: e.target.value })} />
                <Select value={item.responsible} onValueChange={(value) => patchItem(index, { responsible: value as ChecklistRole })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(CHECKLIST_ROLE_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="number"
                  min={-365}
                  max={365}
                  value={item.due_offset_days}
                  onChange={(e) => patchItem(index, { due_offset_days: Number(e.target.value) || 0 })}
                />
                <Button type="button" variant="ghost" size="icon" onClick={() => setItems((c) => c.filter((_, i) => i !== index))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <div>
              <Button type="button" variant="outline" size="sm" onClick={() => setItems((c) => [...c, { title: '', responsible: 'HR', due_offset_days: 0 }])}>
                <Plus className="h-4 w-4" />
                Aufgabe
              </Button>
            </div>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
