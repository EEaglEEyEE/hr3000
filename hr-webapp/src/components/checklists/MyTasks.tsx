import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiClient, unwrap } from '../../api/client'
import { useUploadOwnDocumentMutation } from '../../api/documents'
import { formatDate } from '../../lib/format'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'

/** „Mein Bereich“: Aufgaben aus On-/Offboarding, für die die Person selbst zuständig ist. */
export function MyTasks({ employeeId }: { employeeId: number }) {
  const queryClient = useQueryClient()
  const items = useQuery({
    queryKey: ['my-checklist-items'],
    queryFn: async () => unwrap(await apiClient.GET('/me/checklist-items')),
  }).data ?? []
  const complete = useMutation({
    mutationFn: async (itemId: number) =>
      unwrap(await apiClient.POST('/me/checklist-items/{item_id}/done', { params: { path: { item_id: itemId } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['my-checklist-items'] }),
  })
  const upload = useUploadOwnDocumentMutation(employeeId)
  const [error, setError] = useState<string | null>(null)
  const onError = (err: unknown) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')

  if (items.length === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Meine Aufgaben</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {items.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2 last:border-0">
            <div>
              <p className="text-sm font-medium text-slate-900">{item.title}</p>
              <p className="text-xs text-slate-500">
                bis {formatDate(item.due_date)}
                {item.description && ` · ${item.description}`}
                {item.action === 'FILL_DATA' && ' · unter „Meine Daten“ → „Änderung vorschlagen“ eintragen'}
              </p>
            </div>
            {item.action === 'UPLOAD_DOCUMENT' && item.action_category_id ? (
              <label className="cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
                Datei hochladen
                <input
                  type="file"
                  className="sr-only"
                  accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx"
                  aria-label={`Datei für ${item.title}`}
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    setError(null)
                    upload.mutate(
                      { file, categoryId: item.action_category_id!, title: item.title, checklistItemId: item.id },
                      { onError },
                    )
                  }}
                />
              </label>
            ) : (
              <Button size="sm" variant="outline" disabled={complete.isPending} onClick={() => complete.mutate(item.id, { onError })}>
                Erledigt
              </Button>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
