import type { ReactNode } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { useFeaturesQuery } from '../../api/queries/workTimeModel'
import { allowsPage, PAGE_FEATURE_ACCESS } from '../../lib/access'

/** Schützt eine Seite nach der Rechte-Tabelle (lib/access.ts) – dieselben Stufen wie Menü und Backend,
 * bei eigener Rolle zusätzlich nach Bereich. Seiten aus PAGE_FEATURE_ACCESS öffnet zusätzlich ein Schalter
 * (z. B. eigene Berichte für Führungskräfte). Wer die Adresse direkt aufruft, sieht einen Hinweis statt
 * einer halb leeren Seite. */
export function RequireAccess({ path, children }: { path: string; children: ReactNode }) {
  const { isAdmin, isFullHr, canPayroll, perms } = useAuth()
  const flags = { isAdmin, isFullHr, canPayroll, perms }
  const needsFeature = !allowsPage(path, flags) && PAGE_FEATURE_ACCESS[path] !== undefined
  const features = useFeaturesQuery(needsFeature)
  if (allowsPage(path, flags)) return <>{children}</>
  if (needsFeature && features.isLoading) return <p className="text-slate-500">Lädt…</p>
  if (needsFeature && allowsPage(path, flags, features.data)) return <>{children}</>
  return <p className="text-slate-500">Für diese Seite fehlt die Berechtigung.</p>
}

