import { useEffect, useState } from 'react'

const CACHE_KEY = 'hr3000-branding'

interface Branding {
  tenant_name: string | null
  logo_data_url: string | null
}

function cached(): Branding | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? (JSON.parse(raw) as Branding) : null
  } catch {
    return null
  }
}

/** HR3000-Logo plus (falls hinterlegt) Firmenlogo des Mandanten. Offline aus dem Cache. */
export function Brand({ compact = false }: { compact?: boolean }) {
  const [branding, setBranding] = useState<Branding | null>(cached)

  useEffect(() => {
    fetch('/api/branding')
      .then((response) => (response.ok ? (response.json() as Promise<Branding>) : null))
      .then((data) => {
        if (!data) return
        setBranding(data)
        try {
          localStorage.setItem(CACHE_KEY, JSON.stringify(data))
        } catch {
          // Speicher voll/gesperrt – Anzeige funktioniert trotzdem.
        }
      })
      .catch(() => undefined)
  }, [])

  return (
    <div className="flex items-center gap-3">
      <img src="/logo.svg" alt="" className={compact ? 'h-8 w-8' : 'h-10 w-10'} />
      <span className="text-lg font-bold tracking-wide text-white">HR3000</span>
      {branding?.logo_data_url && (
        <img
          src={branding.logo_data_url}
          alt={branding.tenant_name ?? ''}
          className="ml-2 max-h-10 max-w-40 rounded bg-white/90 object-contain p-1"
        />
      )}
    </div>
  )
}
