import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import type { TwoFactorEnabled } from '../../api/auth'
import { ApiError } from '../../api/client'
import {
  useDisableTwoFactorMutation,
  useEnableTwoFactorMutation,
  useSetupTwoFactorMutation,
  useTwoFactorStatusQuery,
} from '../../api/queries/account'
import { useAuth } from '../../auth/AuthContext'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { TwoFactorSetup } from './TwoFactorSetup'

/** Eigene Zwei-Faktor-Anmeldung: Status, einrichten, abschalten (mit Passwort; nicht, wenn die Firma
 * sie für die eigene Rolle vorschreibt). Ein- und Ausschalten beendet alle anderen Sitzungen. */
export function TwoFactorDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { updateTokens, logout } = useAuth()
  const queryClient = useQueryClient()
  const status = useTwoFactorStatusQuery(open)
  const setup = useSetupTwoFactorMutation()
  const enable = useEnableTwoFactorMutation()
  const disable = useDisableTwoFactorMutation()
  const [settingUp, setSettingUp] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSettingUp(false)
    setPassword('')
    setError(null)
  }, [open])

  const start = useCallback(() => setup.mutateAsync(), [setup])
  const finish = useCallback((code: string) => enable.mutateAsync(code), [enable])

  function handleDone(result: TwoFactorEnabled) {
    updateTokens(result.access_token, result.refresh_token)
    void queryClient.invalidateQueries({ queryKey: ['two-factor'] })
    setSettingUp(false)
  }

  function handleDisable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    disable.mutate(password, {
      // Alle Sitzungen enden – auch diese; mit dem Passwort neu anmelden
      onSuccess: () => logout(),
      onError: (err) => setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.'),
    })
  }

  const data = status.data
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Zwei-Faktor-Anmeldung</DialogTitle>
        </DialogHeader>
        {!data ? (
          <p className="text-sm text-slate-500">Lädt…</p>
        ) : settingUp ? (
          <TwoFactorSetup start={start} enable={finish} onDone={handleDone} />
        ) : data.enabled ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-slate-700">
              Eingerichtet. Bei der Anmeldung fragt HR3000 nach dem Code aus deiner Authenticator-App. Noch{' '}
              {data.recovery_codes_left} Wiederherstellungscodes übrig.
            </p>
            {data.required ? (
              <p className="text-sm text-slate-500">Deine Firma schreibt die Zwei-Faktor-Anmeldung für deine Rolle vor.</p>
            ) : (
              <form className="flex flex-col gap-2" onSubmit={handleDisable}>
                <Label htmlFor="totp-disable-password">Zum Abschalten Passwort eingeben</Label>
                <Input
                  id="totp-disable-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                {error && <p className="text-sm text-red-600">{error}</p>}
                <Button type="submit" variant="outline" disabled={disable.isPending}>
                  Abschalten (danach neu anmelden)
                </Button>
              </form>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-slate-700">
              Schützt dein Konto zusätzlich: Bei der Anmeldung gibst du nach dem Passwort einen Code aus einer
              Authenticator-App auf deinem Handy ein.
            </p>
            {data.required && (
              <p className="text-sm text-amber-700">Deine Firma schreibt sie für deine Rolle vor.</p>
            )}
            <Button type="button" onClick={() => setSettingUp(true)}>
              Einrichten
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Auslöser „Zwei-Faktor-Anmeldung“ samt Dialog – Aussehen bestimmt die jeweilige Stelle. */
export function TwoFactorButton({
  className,
  title,
  children,
}: {
  className?: string
  title?: string
  children?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className={className} title={title} onClick={() => setOpen(true)}>
        {children ?? (
          <>
            <ShieldCheck className="h-4 w-4 shrink-0" />
            Zwei-Faktor-Anmeldung
          </>
        )}
      </button>
      <TwoFactorDialog open={open} onOpenChange={setOpen} />
    </>
  )
}
