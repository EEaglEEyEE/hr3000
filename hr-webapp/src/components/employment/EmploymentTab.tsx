import { useState, type FormEvent } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import {
  useCompensationQuery,
  useContractsQuery,
  useCreateCompensationMutation,
  useCreateContractMutation,
  useDeleteCompensationMutation,
  useDeleteContractMutation,
  type Compensation,
  type Contract,
} from '../../api/queries/employment'
import { formatDate, formatDays, todayIsoDate } from '../../lib/format'
import { CONTRACT_TYPE_LABELS, PAY_TYPE_LABELS } from '../../lib/labels'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { PayComponentsSection } from './PayComponentsSection'

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status !== 422 ? err.message : fallback
}

function formatAmount(compensation: Compensation): string {
  const value = compensation.amount.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${value} ${compensation.currency}${compensation.pay_type === 'HOURLY' ? ' / h' : ' / Monat'}`
}

export function EmploymentTab({ employeeId, isAdmin }: { employeeId: number; isAdmin: boolean }) {
  return (
    <div className="flex flex-col gap-8">
      <ContractSection employeeId={employeeId} />
      {isAdmin && <CompensationSection employeeId={employeeId} />}
      {isAdmin && <PayComponentsSection employeeId={employeeId} />}
    </div>
  )
}

// --- Vertrag ----------------------------------------------------------------------------------

function ContractSection({ employeeId }: { employeeId: number }) {
  const contractsQuery = useContractsQuery(employeeId)
  const deleteContract = useDeleteContractMutation(employeeId)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleDelete(contract: Contract) {
    if (!window.confirm(`Vertrag ab ${formatDate(contract.valid_from)} wirklich löschen?`)) return
    setDeleteError(null)
    try {
      await deleteContract.mutateAsync(contract.id)
    } catch (err) {
      setDeleteError(errorMessage(err, 'Löschen fehlgeschlagen.'))
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-900">Vertragsdaten</h2>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
          Neuer Vertragsabschnitt
        </Button>
      </div>
      {contractsQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {contractsQuery.isError && <p className="text-red-600">Vertragsdaten konnten nicht geladen werden.</p>}
      {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Gültig ab</TableHead>
            <TableHead>Gültig bis</TableHead>
            <TableHead>Vertragsart</TableHead>
            <TableHead>Position</TableHead>
            <TableHead>Probezeit bis</TableHead>
            <TableHead>Befristet bis</TableHead>
            <TableHead>Kündigungsfrist</TableHead>
            <TableHead>Jahresurlaub</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {contractsQuery.data?.map((contract) => (
            <TableRow key={contract.id}>
              <TableCell>{formatDate(contract.valid_from)}</TableCell>
              <TableCell>{contract.valid_to ? formatDate(contract.valid_to) : 'offen'}</TableCell>
              <TableCell>{CONTRACT_TYPE_LABELS[contract.contract_type]}</TableCell>
              <TableCell>{contract.job_title ?? '–'}</TableCell>
              <TableCell>{contract.probation_end ? formatDate(contract.probation_end) : '–'}</TableCell>
              <TableCell>{contract.fixed_term_end ? formatDate(contract.fixed_term_end) : '–'}</TableCell>
              <TableCell>{contract.notice_period ?? '–'}</TableCell>
              <TableCell>
                {contract.annual_vacation_days !== null && contract.annual_vacation_days !== undefined
                  ? `${formatDays(contract.annual_vacation_days)} Tage`
                  : 'Standard'}
              </TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" onClick={() => void handleDelete(contract)}>
                  <Trash2 className="h-4 w-4 text-red-600" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {contractsQuery.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="text-center text-slate-500">
                Noch keine Vertragsdaten hinterlegt.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <ContractDialog open={dialogOpen} onOpenChange={setDialogOpen} employeeId={employeeId} />
    </section>
  )
}

function ContractDialog({
  open,
  onOpenChange,
  employeeId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
}) {
  const createContract = useCreateContractMutation(employeeId)
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [contractType, setContractType] = useState<Contract['contract_type']>('PERMANENT')
  const [jobTitle, setJobTitle] = useState('')
  const [probationEnd, setProbationEnd] = useState('')
  const [fixedTermEnd, setFixedTermEnd] = useState('')
  const [noticePeriod, setNoticePeriod] = useState('')
  const [annualVacation, setAnnualVacation] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    try {
      await createContract.mutateAsync({
        valid_from: validFrom,
        contract_type: contractType,
        job_title: jobTitle.trim() || null,
        probation_end: probationEnd || null,
        fixed_term_end: contractType === 'FIXED_TERM' ? fixedTermEnd || null : null,
        notice_period: noticePeriod.trim() || null,
        annual_vacation_days: annualVacation.trim() === '' ? null : Number(annualVacation),
      })
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, 'Bitte die Datumsangaben prüfen (bei befristeten Verträgen ist ein Befristungsende nötig).'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Neuer Vertragsabschnitt</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500">
          Ein neuer Abschnitt beendet den bisher offenen Abschnitt automatisch am Vortag.
        </p>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="contract_valid_from">Gültig ab</Label>
              <Input id="contract_valid_from" type="date" required value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Vertragsart</Label>
              <Select value={contractType} onValueChange={(value) => setContractType(value as Contract['contract_type'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CONTRACT_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="job_title">Position / Tätigkeit</Label>
            <Input id="job_title" maxLength={150} value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="probation_end">Probezeit bis</Label>
              <Input id="probation_end" type="date" value={probationEnd} onChange={(e) => setProbationEnd(e.target.value)} />
            </div>
            {contractType === 'FIXED_TERM' && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="fixed_term_end">Befristet bis</Label>
                <Input id="fixed_term_end" type="date" required value={fixedTermEnd} onChange={(e) => setFixedTermEnd(e.target.value)} />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="notice_period">Kündigungsfrist</Label>
            <Input id="notice_period" maxLength={100} placeholder="z. B. 4 Wochen zum Monatsende" value={noticePeriod} onChange={(e) => setNoticePeriod(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="annual_vacation_days">Jahresurlaub (Tage, 5-Tage-Woche)</Label>
            <Input
              id="annual_vacation_days"
              type="number"
              min={0}
              max={365}
              step={0.5}
              placeholder="leer = Standard aus den Einstellungen"
              value={annualVacation}
              onChange={(e) => setAnnualVacation(e.target.value)}
            />
            <p className="text-xs text-slate-500">
              Daraus wird der Urlaubsanspruch je Jahr berechnet (Teilzeit und Ein-/Austritt je nach Einstellung).
            </p>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={createContract.isPending}>
              {createContract.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- Vergütung (nur Admin) ---------------------------------------------------------------------

function CompensationSection({ employeeId }: { employeeId: number }) {
  const compensationQuery = useCompensationQuery(employeeId, true)
  const deleteCompensation = useDeleteCompensationMutation(employeeId)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleDelete(compensation: Compensation) {
    if (!window.confirm(`Vergütung ab ${formatDate(compensation.valid_from)} wirklich löschen?`)) return
    setDeleteError(null)
    try {
      await deleteCompensation.mutateAsync(compensation.id)
    } catch (err) {
      setDeleteError(errorMessage(err, 'Löschen fehlgeschlagen.'))
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Vergütung</h2>
          <p className="text-sm text-slate-500">Nur mit „Vergütung &amp; Lohn-Export“ sichtbar; jeder Abruf wird protokolliert.</p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
          Neue Vergütung
        </Button>
      </div>
      {compensationQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {compensationQuery.isError && <p className="text-red-600">Vergütung konnte nicht geladen werden.</p>}
      {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Gültig ab</TableHead>
            <TableHead>Gültig bis</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Betrag</TableHead>
            <TableHead>Notiz</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {compensationQuery.data?.map((compensation) => (
            <TableRow key={compensation.id}>
              <TableCell>{formatDate(compensation.valid_from)}</TableCell>
              <TableCell>{compensation.valid_to ? formatDate(compensation.valid_to) : 'offen'}</TableCell>
              <TableCell>{PAY_TYPE_LABELS[compensation.pay_type]}</TableCell>
              <TableCell>{formatAmount(compensation)}</TableCell>
              <TableCell>{compensation.note ?? '–'}</TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" onClick={() => void handleDelete(compensation)}>
                  <Trash2 className="h-4 w-4 text-red-600" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {compensationQuery.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-slate-500">
                Noch keine Vergütung hinterlegt.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <CompensationDialog open={dialogOpen} onOpenChange={setDialogOpen} employeeId={employeeId} />
    </section>
  )
}

function CompensationDialog({
  open,
  onOpenChange,
  employeeId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  employeeId: number
}) {
  const createCompensation = useCreateCompensationMutation(employeeId)
  const [validFrom, setValidFrom] = useState(todayIsoDate())
  const [payType, setPayType] = useState<Compensation['pay_type']>('HOURLY')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const parsed = Number(amount.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError('Bitte einen Betrag größer 0 angeben.')
      return
    }
    try {
      await createCompensation.mutateAsync({
        valid_from: validFrom,
        pay_type: payType,
        amount: parsed,
        currency: 'EUR',
        note: note.trim() || null,
      })
      setAmount('')
      setNote('')
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, 'Bitte Datum und Betrag prüfen.'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Neue Vergütung</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500">
          Ein neuer Abschnitt beendet den bisher offenen Abschnitt automatisch am Vortag. Korrekturen: Eintrag löschen und neu anlegen.
        </p>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="comp_valid_from">Gültig ab</Label>
              <Input id="comp_valid_from" type="date" required value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Art</Label>
              <Select value={payType} onValueChange={(value) => setPayType(value as Compensation['pay_type'])}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PAY_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="amount">{payType === 'HOURLY' ? 'Stundenlohn (EUR, brutto)' : 'Monatsgehalt (EUR, brutto)'}</Label>
            <Input id="amount" inputMode="decimal" required value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="comp_note">Notiz (optional)</Label>
            <Input id="comp_note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={createCompensation.isPending}>
              {createCompensation.isPending ? 'Speichern…' : 'Speichern'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
