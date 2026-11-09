import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useAbsenceTypeMap, type AbsenceTypeDef } from '../../api/queries/absenceTypes'
import {
  useDeleteAbsenceMutation,
  useEmployeeAbsencesQuery,
  useUploadAbsenceCertificateMutation,
  type Absence,
} from '../../api/queries/absences'
import { ApiError } from '../../api/client'
import { formatDate, formatHoursMinutes } from '../../lib/format'
import { ABSENCE_TYPE_LABELS } from '../../lib/labels'
import { Badge, type BadgeProps } from '../ui/badge'
import { Button } from '../ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { AbsenceFormDialog } from './AbsenceFormDialog'
import { LeaveEntitlementCard } from './LeaveEntitlementCard'

const APPROVAL_STATUS_LABELS: Record<Absence['approval_status'], string> = {
  APPROVED: 'Genehmigt',
  PENDING: 'Ausstehend',
  REJECTED: 'Abgelehnt',
}

const APPROVAL_STATUS_VARIANT: Record<Absence['approval_status'], BadgeProps['variant']> = {
  APPROVED: 'success',
  PENDING: 'warning',
  REJECTED: 'danger',
}

export function AbsencesTab({
  employeeId,
  readOnly = false,
  allowSelfCreate = false,
  entitlementReadOnly = false,
}: {
  employeeId: number
  readOnly?: boolean
  /** Für "Mein Bereich": readOnly bleibt aktiv (kein Bearbeiten/Löschen,
   * beides weiterhin HR-only im Backend), aber ein eigener Urlaubsantrag
   * darf gestellt werden – siehe app/api/absences.py create_absence. */
  allowSelfCreate?: boolean
  /** Supervisor: Abwesenheiten pflegen ja, Urlaubsanspruch ändern nein. */
  entitlementReadOnly?: boolean
}) {
  const absencesQuery = useEmployeeAbsencesQuery(employeeId)
  const absenceTypes = useAbsenceTypeMap()
  const deleteAbsence = useDeleteAbsenceMutation(employeeId)
  const uploadCertificate = useUploadAbsenceCertificateMutation(employeeId)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingAbsence, setEditingAbsence] = useState<Absence | undefined>(undefined)

  const canCreate = !readOnly || allowSelfCreate
  const canEditOrDelete = !readOnly

  function openCreateDialog() {
    setEditingAbsence(undefined)
    setDialogOpen(true)
  }

  function openEditDialog(absence: Absence) {
    if (!canEditOrDelete) return
    setEditingAbsence(absence)
    setDialogOpen(true)
  }

  if (absencesQuery.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (absencesQuery.isError) return <p className="text-red-600">Abwesenheiten konnten nicht geladen werden.</p>

  return (
    <div className="flex flex-col gap-4">
      <LeaveEntitlementCard employeeId={employeeId} readOnly={readOnly || entitlementReadOnly} />

      {canCreate && (
        <div>
          <Button onClick={openCreateDialog}>
            <Plus className="h-4 w-4" />
            Neue Abwesenheit
          </Button>
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Art</TableHead>
            <TableHead>Von</TableHead>
            <TableHead>Bis</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Notiz</TableHead>
            {canEditOrDelete && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {absencesQuery.data?.map((absence) => (
            <TableRow
              key={absence.id}
              className={canEditOrDelete ? 'cursor-pointer' : undefined}
              onClick={() => openEditDialog(absence)}
            >
              <TableCell>
                <AbsenceTypeLabel absence={absence} type={absenceTypes.get(absence.absence_type_id ?? -1)} />
                <CertificateCell
                  absence={absence}
                  type={absenceTypes.get(absence.absence_type_id ?? -1)}
                  uploading={uploadCertificate.isPending}
                  onUpload={(file) => {
                    setUploadError(null)
                    uploadCertificate.mutate(
                      { absenceId: absence.id, file },
                      { onError: (err) => setUploadError(err instanceof ApiError ? err.message : 'Upload fehlgeschlagen.') },
                    )
                  }}
                />
              </TableCell>
              <TableCell>{formatDate(absence.date_from)}</TableCell>
              <TableCell>{formatDate(absence.date_to)}</TableCell>
              <TableCell>
                <Badge variant={APPROVAL_STATUS_VARIANT[absence.approval_status]}>
                  {APPROVAL_STATUS_LABELS[absence.approval_status]}
                </Badge>
                {absence.waiting_for && <span className="block text-xs text-slate-500">bei {absence.waiting_for}</span>}
              </TableCell>
              <TableCell>
                {absence.note ?? (absence.substitute_name ? '' : '–')}
                {absence.substitute_name && (
                  <span className="block text-xs text-slate-500">Vertretung: {absence.substitute_name}</span>
                )}
              </TableCell>
              {canEditOrDelete && (
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(event) => {
                      event.stopPropagation()
                      deleteAbsence.mutate(absence.id)
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-red-600" />
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
          {absencesQuery.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={canEditOrDelete ? 6 : 5} className="text-center text-slate-500">
                Keine Abwesenheiten erfasst.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}

      {canCreate && (
        <AbsenceFormDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          employeeId={employeeId}
          absence={editingAbsence}
          selfService={readOnly && allowSelfCreate}
        />
      )}
    </div>
  )
}

/** Nachweis: vorhanden (liegt unter „Dokumente“) oder hochladen – bei Arten mit „Nachweis ab Tag“. */
function CertificateCell({
  absence,
  type,
  uploading,
  onUpload,
}: {
  absence: Absence
  type?: AbsenceTypeDef
  uploading: boolean
  onUpload: (file: File) => void
}) {
  if (absence.certificate_document_id != null) {
    return <span className="mt-1 block text-xs text-emerald-700">Nachweis hochgeladen (siehe „Dokumente“)</span>
  }
  if (type?.certificate_from_day == null) return null
  return (
    <label className="mt-1 block cursor-pointer text-xs text-sky-700 underline" onClick={(event) => event.stopPropagation()}>
      {uploading ? 'Lädt hoch…' : 'Nachweis hochladen'}
      <input
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        className="sr-only"
        aria-label={`Nachweis hochladen für ${type.name} ab ${formatDate(absence.date_from)}`}
        disabled={uploading}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onUpload(file)
          event.target.value = ''
        }}
      />
    </label>
  )
}

/** Name + Farbe der Abwesenheitsart, mit Hinweis, wenn ein Nachweis fällig ist. */
function AbsenceTypeLabel({ absence, type }: { absence: Absence; type?: AbsenceTypeDef }) {
  const days = Math.round((Date.parse(absence.date_to) - Date.parse(absence.date_from)) / 86_400_000) + 1
  const needsCertificate = type?.certificate_from_day != null && days >= type.certificate_from_day
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: type?.color ?? '#94a3b8' }} />
      {type?.name ?? ABSENCE_TYPE_LABELS[absence.type]}
      {absence.half_day && (
        <Badge variant="info" className="whitespace-nowrap">
          ½ Tag
        </Badge>
      )}
      {absence.duration_minutes != null && (
        <Badge variant="info" className="whitespace-nowrap">
          {formatHoursMinutes(absence.duration_minutes)} Std.
        </Badge>
      )}
      {needsCertificate && (
        <Badge variant="warning" title={`Nachweis ab dem ${type?.certificate_from_day}. Tag`}>
          Nachweis nötig
        </Badge>
      )}
    </span>
  )
}
