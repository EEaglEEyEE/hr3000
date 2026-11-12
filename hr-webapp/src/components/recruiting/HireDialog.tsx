import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { useChecklistTemplatesQuery } from '../../api/queries/checklists'
import { useDepartmentsQuery } from '../../api/queries/departments'
import { useLocationsQuery } from '../../api/queries/locations'
import { useApplicationActions, type ApplicationDetail, type HireRequest, type HireResult } from '../../api/queries/recruiting'
import { DOCUMENT_CATEGORY_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { SELECT_CLASS } from './labels'

/** „Als Mitarbeiter übernehmen“: legt den Mitarbeiter an, übernimmt Anhänge in die Personalakte und
 * startet auf Wunsch die Onboarding-Checkliste. */
export function HireDialog({
  application,
  departmentId,
  locationId,
  onClose,
}: {
  application: ApplicationDetail
  departmentId: number | null | undefined
  locationId: number | null | undefined
  onClose: () => void
}) {
  const locations = useLocationsQuery()
  const departments = useDepartmentsQuery()
  const templates = useChecklistTemplatesQuery()
  const { hire } = useApplicationActions(application.id)
  const [form, setForm] = useState<HireRequest>({
    employee_number: '',
    first_name: application.first_name,
    last_name: application.last_name,
    private_email: application.email,
    location_id: locationId ?? 0,
    department_id: departmentId ?? null,
    hire_date: '',
    position: null,
    attachment_ids: application.attachments.map((attachment) => attachment.id),
    document_category: 'OTHER',
    checklist_template_id: null,
  })
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<HireResult | null>(null)
  const set = <K extends keyof HireRequest>(key: K, value: HireRequest[K]) => setForm((current) => ({ ...current, [key]: value }))
  const selected = form.attachment_ids ?? []
  const onboarding = (templates.data ?? []).filter((template) => template.kind === 'ONBOARDING')
  const locationValue = form.location_id || (locations.data?.[0]?.id ?? 0)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      setResult(await hire.mutateAsync({ ...form, location_id: locationValue, employee_number: form.employee_number.trim() }))
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 422 ? err.message : 'Übernahme fehlgeschlagen – bitte Eingaben prüfen.')
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Als Mitarbeiter übernehmen</DialogTitle>
        </DialogHeader>
        {result ? (
          <div className="flex flex-col gap-3 text-sm text-slate-700">
            <p>
              Mitarbeiter angelegt
              {result.documents_copied > 0 && `, ${result.documents_copied} Dokument(e) in die Personalakte übernommen`}
              {result.checklist_started && ', Onboarding-Checkliste gestartet'}.
            </p>
            <DialogFooter>
              <Link to={`/employees/${result.employee_id}`} className="text-sm underline">
                Zum Mitarbeiter
              </Link>
              <Button type="button" onClick={onClose}>
                Schließen
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form className="flex flex-col gap-3" onSubmit={submit}>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-first">Vorname</Label>
                <Input id="hire-first" required maxLength={100} value={form.first_name ?? ''} onChange={(e) => set('first_name', e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-last">Nachname</Label>
                <Input id="hire-last" required maxLength={100} value={form.last_name ?? ''} onChange={(e) => set('last_name', e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-number">Personalnummer</Label>
                <Input id="hire-number" required maxLength={50} value={form.employee_number} onChange={(e) => set('employee_number', e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-date">Anstelldatum</Label>
                <Input id="hire-date" type="date" required value={form.hire_date} onChange={(e) => set('hire_date', e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-email">E-Mail (privat)</Label>
                <Input id="hire-email" type="email" maxLength={255} value={form.private_email ?? ''} onChange={(e) => set('private_email', e.target.value || null)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-position">Position (optional)</Label>
                <Input id="hire-position" maxLength={150} value={form.position ?? ''} onChange={(e) => set('position', e.target.value || null)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-location">Standort</Label>
                <select id="hire-location" required className={SELECT_CLASS} value={locationValue || ''} onChange={(e) => set('location_id', Number(e.target.value))}>
                  {(locations.data ?? []).map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="hire-department">Abteilung</Label>
                <select
                  id="hire-department"
                  className={SELECT_CLASS}
                  value={form.department_id ?? ''}
                  onChange={(e) => set('department_id', e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Keine</option>
                  {(departments.data ?? []).map((department) => (
                    <option key={department.id} value={department.id}>
                      {department.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {application.attachments.length > 0 && (
              <fieldset className="flex flex-col gap-1">
                <legend className="text-sm font-medium text-slate-800">Anhänge in die Personalakte übernehmen</legend>
                {application.attachments.map((attachment) => (
                  <label key={attachment.id} className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={selected.includes(attachment.id)}
                      onChange={(e) =>
                        set('attachment_ids', e.target.checked ? [...selected, attachment.id] : selected.filter((id) => id !== attachment.id))
                      }
                    />
                    {attachment.original_filename}
                  </label>
                ))}
                <div className="mt-1 flex flex-col gap-1">
                  <Label htmlFor="hire-category">Dokumentkategorie</Label>
                  <select
                    id="hire-category"
                    className={SELECT_CLASS}
                    value={form.document_category}
                    onChange={(e) => set('document_category', e.target.value as HireRequest['document_category'])}
                  >
                    {Object.entries(DOCUMENT_CATEGORY_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              </fieldset>
            )}
            <div className="flex flex-col gap-1">
              <Label htmlFor="hire-checklist">Onboarding-Checkliste starten</Label>
              <select
                id="hire-checklist"
                className={SELECT_CLASS}
                value={form.checklist_template_id ?? ''}
                onChange={(e) => set('checklist_template_id', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Keine</option>
                {onboarding.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={hire.isPending}>
                Mitarbeiter anlegen
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
