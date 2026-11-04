import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { confirmPasswordReset } from '../api/auth'
import { ApiError } from '../api/client'
import { BrandLogo } from '../components/layout/BrandLogo'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const MIN_LENGTH = 10

/** Token aus dem E-Mail-Link (#token=…) einmal lesen und aus der Adresszeile/Historie entfernen. */
function takeTokenFromUrl(): string | null {
  const match = window.location.hash.match(/token=([A-Za-z0-9_-]+)/)
  if (match) window.history.replaceState(null, '', window.location.pathname)
  return match ? match[1] : null
}

/** Seite hinter dem Link aus "Passwort vergessen": neues Passwort festlegen. */
export function ResetPasswordPage() {
  const [token] = useState(takeTokenFromUrl)
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (next.length < MIN_LENGTH) return setError(`Das Passwort muss mindestens ${MIN_LENGTH} Zeichen haben.`)
    if (new TextEncoder().encode(next).length > 72) return setError('Das Passwort ist zu lang.')
    if (next !== repeat) return setError('Die Passwörter stimmen nicht überein.')
    setPending(true)
    try {
      await confirmPasswordReset(token ?? '', next)
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Das hat nicht geklappt. Bitte versuch es erneut.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <BrandLogo size="lg" />
          <CardTitle className="mt-3">Neues Passwort</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {done ? (
            <>
              <p className="text-sm text-slate-700" role="status">
                Dein neues Passwort ist gespeichert. Du kannst dich jetzt damit anmelden.
              </p>
              <Link to="/login" className="text-sm font-medium text-sky-700 hover:underline">
                Zur Anmeldung
              </Link>
            </>
          ) : !token ? (
            <>
              <p className="text-sm text-red-600">
                Der Link ist unvollständig. Bitte öffne ihn direkt aus der E-Mail oder fordere einen neuen an.
              </p>
              <Link to="/login" className="text-sm font-medium text-sky-700 hover:underline">
                Zur Anmeldung
              </Link>
            </>
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reset-new">Neues Passwort</Label>
                <Input
                  id="reset-new"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                />
                <span className="text-xs text-slate-500">Mindestens {MIN_LENGTH} Zeichen.</span>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="reset-repeat">Neues Passwort wiederholen</Label>
                <Input
                  id="reset-repeat"
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
              <Button type="submit" disabled={pending}>
                {pending ? 'Speichere…' : 'Passwort speichern'}
              </Button>
              <Link to="/login" className="text-center text-sm text-sky-700 hover:underline">
                Zur Anmeldung
              </Link>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
