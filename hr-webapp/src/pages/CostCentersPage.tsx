import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  useCostCentersQuery,
  useCreateCostCenterMutation,
  useDeleteCostCenterMutation,
  useUpdateCostCenterMutation,
} from '../api/queries/personalData'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'

/** Kostenstellen der Firma; am Mitarbeiter (Personalakte → „Stammdaten“) prozentual aufteilbar. */
export function CostCentersPage() {
  const query = useCostCentersQuery(true)
  const create = useCreateCostCenterMutation()
  const update = useUpdateCostCenterMutation()
  const remove = useDeleteCostCenterMutation()
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const onError = (err: Error) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    create.mutate(
      { code, name },
      {
        onSuccess: () => {
          setCode('')
          setName('')
        },
        onError,
      },
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Kostenstellen</h1>
      <p className="text-sm text-slate-500">
        Am Mitarbeiter unter „Personalakte“ → „Stammdaten“ zuordnen, auch anteilig (zusammen 100 %). Benutzte
        Kostenstellen archivieren statt löschen.
      </p>
      <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cc-code">Nummer</Label>
          <Input id="cc-code" className="w-32" required maxLength={20} value={code} onChange={(e) => setCode(e.target.value)} />
        </div>
        <div className="flex max-w-full flex-col gap-1.5">
          <Label htmlFor="cc-name">Bezeichnung</Label>
          <Input id="cc-name" className="w-64 max-w-full" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button type="submit" disabled={create.isPending}>
          Hinzufügen
        </Button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {(query.data ?? []).length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nummer</TableHead>
              <TableHead>Bezeichnung</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(query.data ?? []).map((costCenter) => (
              <TableRow key={costCenter.id} className={costCenter.archived ? 'text-slate-400' : undefined}>
                <TableCell className="font-mono">{costCenter.code}</TableCell>
                <TableCell>
                  {costCenter.name}
                  {costCenter.archived && ' (archiviert)'}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => update.mutate({ id: costCenter.id, payload: { archived: !costCenter.archived } }, { onError })}
                    >
                      {costCenter.archived ? 'Wiederherstellen' : 'Archivieren'}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => remove.mutate(costCenter.id, { onError })}>
                      Löschen
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
