import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, apiClient, unwrap } from '../../api/client'
import { useUpdateSettingsMutation, type Settings } from '../../api/queries/settings'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

type Security = 'NONE' | 'STARTTLS' | 'SSL'

const SECURITY_LABELS: Record<Security, string> = {
  STARTTLS: 'STARTTLS (Port 587)',
  SSL: 'SSL/TLS (Port 465)',
  NONE: 'Unverschlüsselt (nicht empfohlen)',
}
const DEFAULT_PORTS: Record<Security, number> = { STARTTLS: 587, SSL: 465, NONE: 25 }

export function SmtpSettingsCard({ settings }: { settings: Settings }) {
  const updateSettings = useUpdateSettingsMutation()

  const [host, setHost] = useState('')
  const [port, setPort] = useState('587')
  const [security, setSecurity] = useState<Security>('STARTTLS')
  const [user, setUser] = useState('')
  const [password, setPassword] = useState('')
  const [from, setFrom] = useState('')
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    setHost(settings.smtp_host ?? '')
    setPort(String(settings.smtp_port))
    setSecurity(settings.smtp_security)
    setUser(settings.smtp_user ?? '')
    setFrom(settings.smtp_from ?? '')
    setPassword('')
    // Nur bei geänderten SMTP-Werten neu füllen – ein Refetch nach dem Umschalten der
    // Benachrichtigungen darf ungespeicherte Eingaben im Formular nicht zurücksetzen.
  }, [settings.smtp_host, settings.smtp_port, settings.smtp_security, settings.smtp_user, settings.smtp_from])

  function changeSecurity(value: string) {
    const next = value as Security
    // Port mitziehen, solange der Admin keinen eigenen eingetragen hat.
    if (Number(port) === DEFAULT_PORTS[security]) setPort(String(DEFAULT_PORTS[next]))
    setSecurity(next)
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage(null)
    try {
      await updateSettings.mutateAsync({
        smtp_host: host.trim(),
        smtp_port: Number(port),
        smtp_security: security,
        smtp_user: user.trim(),
        smtp_from: from.trim(),
        // Leer lassen = Passwort unverändert (undefined wird nicht gesendet).
        ...(password ? { smtp_password: password } : {}),
      })
      setPassword('')
      setMessage({ kind: 'ok', text: 'SMTP-Einstellungen gespeichert.' })
    } catch (err) {
      setMessage({
        kind: 'error',
        text:
          err instanceof ApiError && err.status !== 422
            ? err.message
            : 'Bitte Host, Port (1–65535) und eine gültige Absender-Adresse prüfen.',
      })
    }
  }

  async function handleClearPassword() {
    setMessage(null)
    try {
      await updateSettings.mutateAsync({ smtp_password: '' })
      setMessage({ kind: 'ok', text: 'Gespeichertes Passwort entfernt.' })
    } catch {
      setMessage({ kind: 'error', text: 'Passwort konnte nicht entfernt werden.' })
    }
  }

  async function handleTest() {
    setMessage(null)
    setTesting(true)
    try {
      const result = unwrap(await apiClient.POST('/settings/smtp-test', { body: {} }))
      setMessage({ kind: 'ok', text: `Testmail an ${result.sent_to} gesendet.` })
    } catch (err) {
      setMessage({ kind: 'error', text: err instanceof ApiError ? err.message : 'Testmail fehlgeschlagen.' })
    } finally {
      setTesting(false)
    }
  }

  const usingPlatform = !settings.smtp_host

  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <p className="text-sm font-medium text-slate-800">E-Mail-Versand (SMTP)</p>
      <p className="mb-3 text-sm text-slate-500">
        Eigener SMTP-Server für Benachrichtigungen und Zugangsdaten-Mails. Ohne Eintrag wird – falls
        vorhanden – der Server der Plattform verwendet.
        {usingPlatform && ' Aktuell: Plattform-Server.'}
      </p>

      <label className="mb-4 flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 rounded border-slate-300"
          checked={settings.email_notifications_enabled}
          disabled={updateSettings.isPending}
          onChange={(event) => updateSettings.mutate({ email_notifications_enabled: event.target.checked })}
        />
        <span>
          <span className="block text-sm font-medium text-slate-800">Benachrichtigungen auch per E-Mail</span>
          <span className="block text-sm text-slate-500">
            Urlaubsanträge, Entscheidungen und die tägliche „Zu klären“-Zusammenfassung zusätzlich zur
            Glocke an die Login-Adresse senden.
          </span>
        </span>
      </label>

      <form className="flex flex-col gap-3" onSubmit={handleSave}>
        <div className="grid grid-cols-[1fr_6rem] gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="smtp_host">Server</Label>
            <Input
              id="smtp_host"
              placeholder="z.B. smtp.firma.de (leer = Plattform-Server)"
              value={host}
              onChange={(event) => setHost(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="smtp_port">Port</Label>
            <Input
              id="smtp_port"
              inputMode="numeric"
              value={port}
              onChange={(event) => setPort(event.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Verschlüsselung</Label>
          <Select value={security} onValueChange={changeSecurity}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(SECURITY_LABELS) as Security[]).map((value) => (
                <SelectItem key={value} value={value}>
                  {SECURITY_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="smtp_user">Benutzername</Label>
            <Input
              id="smtp_user"
              autoComplete="off"
              value={user}
              onChange={(event) => setUser(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="smtp_password">Passwort</Label>
            <Input
              id="smtp_password"
              type="password"
              autoComplete="new-password"
              placeholder={settings.smtp_password_set ? '•••••••• (gespeichert)' : ''}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="smtp_from">Absender-Adresse</Label>
          <Input
            id="smtp_from"
            type="email"
            placeholder="z.B. hr@firma.de"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </div>

        {message && (
          <p className={message.kind === 'ok' ? 'text-sm text-emerald-600' : 'text-sm text-red-600'}>
            {message.text}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={updateSettings.isPending}>
            Speichern
          </Button>
          <Button type="button" variant="outline" disabled={testing} onClick={handleTest}>
            {testing ? 'Sende…' : 'Testmail an mich senden'}
          </Button>
          {settings.smtp_password_set && (
            <Button type="button" variant="ghost" onClick={handleClearPassword}>
              Gespeichertes Passwort entfernen
            </Button>
          )}
        </div>
        <p className="text-xs text-slate-500">
          Das Passwort wird verschlüsselt gespeichert und nie wieder angezeigt. Server in internen
          Netzen sind aus Sicherheitsgründen nicht zulässig.
        </p>
      </form>
    </div>
  )
}
