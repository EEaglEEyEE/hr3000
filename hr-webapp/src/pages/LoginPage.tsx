import { useCallback, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { enableTwoFactorAtLogin, loginTwoFactor, requestPasswordReset, setupTwoFactorAtLogin, type TwoFactorEnabled } from '../api/auth'
import { ApiError } from '../api/client'
import { useBrandingQuery } from '../api/queries/branding'
import { useAuth, type TwoFactorStep } from '../auth/AuthContext'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { BrandLogo } from '../components/layout/BrandLogo'
import { TwoFactorSetup } from '../components/account/TwoFactorSetup'
import { Label } from '../components/ui/label'

function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === 'EMAIL_NOT_VERIFIED') return error.message
  if (error instanceof ApiError && error.status === 429) return 'Zu viele Fehlversuche. Bitte warte ein paar Minuten.'
  return 'E-Mail oder Passwort falsch.'
}

export function LoginPage() {
  const { login, updateTokens } = useAuth()
  const navigate = useNavigate()
  const branding = useBrandingQuery().data
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [forgotSent, setForgotSent] = useState<string | null>(null)
  const [forgotError, setForgotError] = useState<string | null>(null)
  const [twoFactor, setTwoFactor] = useState<TwoFactorStep | null>(null)
  const [code, setCode] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      const step = await login(email, password)
      if (step) {
        setTwoFactor(step)
        setCode('')
        return
      }
      // Der Zugangsbereich (HR-Webapp vs. Mein Bereich) richtet sich nach den
      // hinterlegten Berechtigungen – ProtectedRoute leitet beim nächsten
      // Render automatisch an die richtige Stelle weiter.
      navigate('/', { replace: true })
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!twoFactor) return
    setError(null)
    setIsSubmitting(true)
    try {
      const tokens = await loginTwoFactor(twoFactor.challengeToken, code.trim())
      updateTokens(tokens.access_token, tokens.refresh_token)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setTwoFactor(null)
        setError('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.')
      } else if (err instanceof ApiError && err.status === 429) setError('Zu viele Fehlversuche. Bitte warte 15 Minuten.')
      else setError('Der Code stimmt nicht.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const challengeToken = twoFactor?.challengeToken ?? ''
  const startSetup = useCallback(() => setupTwoFactorAtLogin(challengeToken), [challengeToken])
  const finishSetup = useCallback((value: string) => enableTwoFactorAtLogin(challengeToken, value), [challengeToken])
  function handleSetupDone(result: TwoFactorEnabled) {
    updateTokens(result.access_token, result.refresh_token)
    navigate('/', { replace: true })
  }

  async function handleForgot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setForgotError(null)
    setIsSubmitting(true)
    try {
      const answer = await requestPasswordReset(email)
      setForgotSent(answer.detail)
    } catch (err) {
      setForgotError(
        err instanceof ApiError && err.status === 429
          ? 'Zu viele Anfragen. Bitte versuch es später erneut.'
          : 'Das hat nicht geklappt. Bitte prüf die E-Mail-Adresse.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const resetAvailable = branding?.password_reset_available === true

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <BrandLogo size="lg" />
          <CardTitle className="mt-3">
            {twoFactor?.kind === 'setup'
              ? 'Zwei-Faktor-Anmeldung einrichten'
              : twoFactor
                ? 'Bestätigungscode'
                : forgotOpen
                  ? 'Passwort vergessen'
                  : 'Anmelden'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {twoFactor?.kind === 'setup' ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-slate-600">Deine Firma schreibt für deine Rolle eine Zwei-Faktor-Anmeldung vor.</p>
              <TwoFactorSetup start={startSetup} enable={finishSetup} onDone={handleSetupDone} />
            </div>
          ) : twoFactor ? (
            <form className="flex flex-col gap-4" onSubmit={handleCode}>
              <p className="text-sm text-slate-600">
                Gib den 6-stelligen Code aus deiner Authenticator-App ein. Ohne Handy geht auch ein
                Wiederherstellungscode.
              </p>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="totp-code">Code</Label>
                <Input
                  id="totp-code"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  maxLength={20}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <Button type="submit" disabled={isSubmitting || code.trim().length < 6}>
                {isSubmitting ? 'Prüfe…' : 'Anmelden'}
              </Button>
              <button
                type="button"
                className="text-sm text-sky-700 hover:underline"
                onClick={() => {
                  setTwoFactor(null)
                  setError(null)
                }}
              >
                Zurück
              </button>
            </form>
          ) : forgotOpen ? (
            <form className="flex flex-col gap-4" onSubmit={handleForgot}>
              {forgotSent ? (
                <p className="text-sm text-slate-700" role="status">
                  {forgotSent} Bitte prüf dein Postfach – der Link gilt eine Stunde.
                </p>
              ) : (
                <>
                  <p className="text-sm text-slate-600">
                    Gib die E-Mail-Adresse deines Logins ein. Wir schicken dir einen Link, mit dem du ein neues
                    Passwort festlegst.
                  </p>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="forgot-email">E-Mail</Label>
                    <Input
                      id="forgot-email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                    />
                  </div>
                  {forgotError && <p className="text-sm text-red-600">{forgotError}</p>}
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting ? 'Sende…' : 'Link schicken'}
                  </Button>
                </>
              )}
              <button
                type="button"
                className="text-sm text-sky-700 hover:underline"
                onClick={() => {
                  setForgotOpen(false)
                  setForgotSent(null)
                  setForgotError(null)
                }}
              >
                Zurück zur Anmeldung
              </button>
            </form>
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">E-Mail</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">Passwort</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? 'Anmelden…' : 'Anmelden'}
              </Button>
              {resetAvailable ? (
                <button
                  type="button"
                  className="text-sm text-sky-700 hover:underline"
                  onClick={() => setForgotOpen(true)}
                >
                  Passwort vergessen?
                </button>
              ) : (
                <p className="text-center text-xs text-slate-500">
                  Passwort vergessen? Bitte wende dich an deine Personalabteilung.
                </p>
              )}
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
