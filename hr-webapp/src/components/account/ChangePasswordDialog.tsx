import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { KeyRound } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useChangePasswordMutation } from '../../api/queries/account'
import { useAuth } from '../../auth/AuthContext'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

const MIN_LENGTH = 10

/** Eigenes Passwort ändern (alle Konten). Danach enden alle anderen Sitzungen dieses Kontos;
 * diese Sitzung bekommt neue Tokens. */
export function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { updateTokens } = useAuth()
  const mutation = useChangePasswordMutation()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!open) return
    setCurrent('')
    setNext('')
    setRepeat('')
    setError(null)
    setDone(false)
    mutation.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (next.length < MIN_LENGTH) return setError(`Das neue Passwort muss mindestens ${MIN_LENGTH} Zeichen haben.`)
    if (new TextEncoder().encode(next).length > 72) return setError('Das neue Passwort ist zu lang.')
    if (next !== repeat) return setError('Die neuen Passwörter stimmen nicht überein.')
    mutation.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: (tokens) => {
          updateTokens(tokens.access_token, tokens.refresh_token)
          setDone(true)
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 429) setError('Zu viele Fehlversuche. Bitte warte 15 Minuten.')
          else setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt.')
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Passwort ändern</DialogTitle>
        </DialogHeader>
        {done ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-slate-700">
              Dein Passwort ist geändert. Auf anderen Geräten musst du dich neu anmelden.
            </p>
            <DialogFooter>
              <Button type="button" onClick={() => onOpenChange(false)}>
                Schließen
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pw-current">Aktuelles Passwort</Label>
              <Input
                id="pw-current"
                type="password"
                autoComplete="current-password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pw-new">Neues Passwort</Label>
              <Input
                id="pw-new"
                type="password"
                autoComplete="new-password"
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
              <span className="text-xs text-slate-500">Mindestens {MIN_LENGTH} Zeichen.</span>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pw-repeat">Neues Passwort wiederholen</Label>
              <Input
                id="pw-repeat"
                type="password"
                autoComplete="new-password"
                required
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
              />
            </div>
            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? 'Speichere…' : 'Passwort ändern'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Auslöser "Passwort ändern" samt Dialog – Aussehen bestimmt die jeweilige Stelle (className, children). */
export function ChangePasswordButton({
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
            <KeyRound className="h-4 w-4 shrink-0" />
            Passwort ändern
          </>
        )}
      </button>
      <ChangePasswordDialog open={open} onOpenChange={setOpen} />
    </>
  )
}
