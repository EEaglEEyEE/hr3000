import { useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { useBrandingQuery, useDeleteLogoMutation, useUploadLogoMutation } from '../../api/queries/branding'
import { Button } from '../ui/button'

/** Firmenlogo hochladen (nur Anzeige in Web-App, Tablet und Berichten – kein Favicon/App-Icon). */
export function LogoSettingsCard() {
  const brandingQuery = useBrandingQuery()
  const upload = useUploadLogoMutation()
  const remove = useDeleteLogoMutation()
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const logo = brandingQuery.data?.logo_data_url

  async function handleFile(file: File | undefined) {
    if (!file) return
    setError(null)
    if (file.size > 256 * 1024) {
      setError('Das Logo darf höchstens 256 KB groß sein.')
      return
    }
    try {
      await upload.mutateAsync(file)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload fehlgeschlagen.')
    } finally {
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <p className="text-sm font-medium text-slate-800">Firmenlogo</p>
      <p className="mb-3 text-sm text-slate-500">
        Erscheint in der Web-App, auf dem Tablet und in den Monatsberichten (zusätzlich zum HR3000-Logo). PNG, JPEG oder
        WebP, max. 256 KB, am besten mit transparentem Hintergrund. Favicon und App-Icon bleiben das HR3000-Logo.
      </p>
      <div className="flex items-center gap-4">
        <div className="flex h-16 w-48 items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50">
          {logo ? <img src={logo} alt="Firmenlogo" className="max-h-14 max-w-44 object-contain" /> : <span className="text-xs text-slate-400">Kein Logo</span>}
        </div>
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => void handleFile(e.target.files?.[0])} />
        <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
          {upload.isPending ? 'Lädt hoch…' : logo ? 'Ersetzen' : 'Hochladen'}
        </Button>
        {logo && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (window.confirm('Firmenlogo entfernen?')) void remove.mutateAsync().catch(() => setError('Entfernen fehlgeschlagen.'))
            }}
          >
            Entfernen
          </Button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  )
}
