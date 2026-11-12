import { Link, useLocation } from 'react-router-dom'

/** Auffangseite für Adressen, die es nicht (mehr) gibt – statt einer leeren Seite. */
export function NotFoundPage() {
  const { pathname } = useLocation()
  return (
    <div className="flex max-w-xl flex-col gap-3">
      <h1 className="text-2xl font-semibold text-slate-900">Seite nicht gefunden</h1>
      <p className="text-slate-600">
        Unter <span className="break-all font-mono text-sm text-slate-800">{pathname}</span> gibt es keine Seite. Vielleicht
        ist die Adresse veraltet oder vertippt.
      </p>
      <p>
        <Link className="text-sm text-sky-700 hover:underline" to="/">
          Zur Startseite
        </Link>
      </p>
    </div>
  )
}
