import { useRef, useState, type FormEvent } from 'react'
import { Download, Lock, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  downloadDocument,
  useDeleteDocumentMutation,
  useDocumentsQuery,
  useUpdateDocumentMutation,
  useUploadDocumentMutation,
  type DocumentCategory,
} from '../../api/documents'
import { formatDate } from '../../lib/format'
import { DOCUMENT_CATEGORY_LABELS } from '../../lib/labels'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'

const MAX_BYTES = 15 * 1024 * 1024
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.docx,.xlsx'

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status !== 422 ? err.message : fallback
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toLocaleString('de-DE', { maximumFractionDigits: 1 })} MB`
}

/** Personalakte. readOnly = Mitarbeiter-Sicht ("Mein Bereich"): nur Ansehen/Herunterladen der
 * für ihn freigegebenen Dokumente. */
export function DocumentsTab({
  employeeId,
  readOnly = false,
  isAdmin = false,
}: {
  employeeId: number
  readOnly?: boolean
  isAdmin?: boolean
}) {
  const documentsQuery = useDocumentsQuery(employeeId)
  const deleteDocument = useDeleteDocumentMutation(employeeId)
  const updateDocument = useUpdateDocumentMutation(employeeId)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>, fallback: string) {
    setActionError(null)
    try {
      await action()
    } catch (err) {
      setActionError(errorMessage(err, fallback))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {!readOnly && (
        <div>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Dokument hochladen
          </Button>
        </div>
      )}
      {documentsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {documentsQuery.isError && <p className="text-red-600">Dokumente konnten nicht geladen werden.</p>}
      {actionError && <p className="text-sm text-red-600">{actionError}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Titel</TableHead>
            <TableHead>Kategorie</TableHead>
            <TableHead>Datei</TableHead>
            <TableHead>Hochgeladen</TableHead>
            {!readOnly && <TableHead>Sichtbarkeit</TableHead>}
            {!readOnly && <TableHead>Aufbewahrung bis</TableHead>}
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {documentsQuery.data?.map((doc) => (
            <TableRow key={doc.id}>
              <TableCell className="font-medium">{doc.title}</TableCell>
              <TableCell>{DOCUMENT_CATEGORY_LABELS[doc.category]}</TableCell>
              <TableCell className="text-slate-500">
                {doc.original_filename} · {formatSize(doc.size_bytes)}
              </TableCell>
              <TableCell>{formatDate(doc.created_at.slice(0, 10))}</TableCell>
              {!readOnly && (
                <TableCell>
                  {doc.confidential ? (
                    <Badge variant="danger">
                      <Lock className="mr-1 h-3 w-3" />
                      Vertraulich
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      className="text-left"
                      title="Sichtbarkeit für den Mitarbeiter umschalten"
                      onClick={() =>
                        void run(
                          () => updateDocument.mutateAsync({ documentId: doc.id, payload: { employee_visible: !doc.employee_visible, clear_retention_until: false } }),
                          'Änderung fehlgeschlagen.',
                        )
                      }
                    >
                      <Badge variant={doc.employee_visible ? 'success' : 'default'}>
                        {doc.employee_visible ? 'Mitarbeiter sieht es' : 'Nur HR'}
                      </Badge>
                    </button>
                  )}
                </TableCell>
              )}
              {!readOnly && <TableCell>{doc.retention_until ? formatDate(doc.retention_until) : '–'}</TableCell>}
              <TableCell className="whitespace-nowrap text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  title="Herunterladen"
                  onClick={() => void run(() => downloadDocument(employeeId, doc), 'Download fehlgeschlagen.')}
                >
                  <Download className="h-4 w-4" />
                </Button>
                {!readOnly && (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Löschen"
                    onClick={() => {
                      if (!window.confirm(`Dokument "${doc.title}" wirklich löschen?`)) return
                      void run(() => deleteDocument.mutateAsync(doc.id), 'Löschen fehlgeschlagen.')
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
          {documentsQuery.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={readOnly ? 5 : 7} className="text-center text-slate-500">
                Keine Dokumente vorhanden.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {!readOnly && <UploadDialog open={dialogOpen} onOpenChange={setDialogOpen} employeeId={employeeId} isAdmin={isAdmin} />}
    </div>
  )
}

function UploadDialog({
  open,
  onOpenChange,
  employeeId,
  isAdmin,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
  isAdmin: boolean
}) {
  const upload = useUploadDocumentMutation(employeeId)
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<DocumentCategory>('OTHER')
  const [employeeVisible, setEmployeeVisible] = useState(false)
  const [confidential, setConfidential] = useState(false)
  const [retentionUntil, setRetentionUntil] = useState('')
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setFile(null)
    setTitle('')
    setCategory('OTHER')
    setEmployeeVisible(false)
    setConfidential(false)
    setRetentionUntil('')
    setError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  function handleOpenChange(next: boolean) {
    if (!next) reset()
    onOpenChange(next)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!file) {
      setError('Bitte eine Datei auswählen.')
      return
    }
    if (file.size > MAX_BYTES) {
      setError('Die Datei ist größer als 15 MB.')
      return
    }
    try {
      await upload.mutateAsync({
        file,
        category,
        title: title.trim() || file.name,
        employeeVisible: employeeVisible && !confidential,
        confidential,
        retentionUntil,
      })
      handleOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, 'Upload fehlgeschlagen. Erlaubt sind PDF, PNG, JPEG, DOCX und XLSX bis 15 MB.'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Dokument hochladen</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc_file">Datei (PDF, PNG, JPEG, DOCX, XLSX; max. 15 MB)</Label>
            <Input
              id="doc_file"
              type="file"
              accept={ACCEPT}
              ref={fileInput}
              onChange={(e) => {
                const selected = e.target.files?.[0] ?? null
                setFile(selected)
                if (selected && !title) setTitle(selected.name.replace(/\.[^.]+$/, ''))
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc_title">Titel</Label>
            <Input id="doc_title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Kategorie</Label>
              <Select value={category} onValueChange={(value) => setCategory(value as DocumentCategory)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(DOCUMENT_CATEGORY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="doc_retention">Aufbewahren bis (optional)</Label>
              <Input id="doc_retention" type="date" value={retentionUntil} onChange={(e) => setRetentionUntil(e.target.value)} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={employeeVisible && !confidential}
              disabled={confidential}
              onChange={(e) => setEmployeeVisible(e.target.checked)}
            />
            Für den Mitarbeiter in „Mein Bereich“ sichtbar
          </label>
          {isAdmin && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={confidential} onChange={(e) => setConfidential(e.target.checked)} />
              Vertraulich (nur Administratoren, z. B. Abmahnungen)
            </label>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={upload.isPending}>
              {upload.isPending ? 'Lädt hoch…' : 'Hochladen'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
