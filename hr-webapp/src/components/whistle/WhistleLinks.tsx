import { Link } from 'react-router-dom'
import { useWhistleStatusQuery } from '../../api/queries/whistle'

/** Links in „Mein Bereich“: Hinweis abgeben (öffentliche Seite) und – für Beauftragte – „Hinweise“. */
export function WhistleLinks() {
  const status = useWhistleStatusQuery().data
  if (!status?.enabled) return null
  return (
    <>
      {/* Neuer Tab ohne Verweis: die Meldeseite soll nicht wissen, woher jemand kommt */}
      <a href="/hinweis" target="_blank" rel="noopener noreferrer" className="text-sm text-sky-700 hover:underline">
        Hinweis abgeben
      </a>
      {status.officer && (
        <Link to="/hinweise" className="text-sm text-sky-700 hover:underline">
          Hinweise bearbeiten
        </Link>
      )}
    </>
  )
}
