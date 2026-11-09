import { useState, type FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { ApiError } from '../api/client'
import {
  useCreateWorkTimeProfileMutation,
  useDeleteWorkTimeProfileMutation,
  useSetWorkTimeProfileModelMutation,
  useUpdateWorkTimeProfileMutation,
  useWorkTimeProfileHistoryQuery,
  useWorkTimeProfilesQuery,
  type WorkTimeProfile,
} from '../api/queries/workTimeProfiles'
import { WorkTimeModelForm, type ModelFormPayload } from '../components/workTimeModel/WorkTimeModelTab'
import { describeVersion, formatRange } from '../components/workTimeModel/modelText'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { formatDate } from '../lib/format'

// Erste Fassung eines Modells gilt „von Anfang an“ (Backend: PROFILE_START).
const PROFILE_START = '2000-01-01'

/** Einstellungen → Arbeitszeitmodelle: Modelle anlegen, ab Stichtag ändern (gilt für alle zugewiesenen
 * Mitarbeiter), umbenennen, archivieren, löschen. Zugewiesen wird am Mitarbeiter (Reiter „Arbeitszeit“). */
export function WorkTimeProfilesPage() {
  const [showArchived, setShowArchived] = useState(false)
  const profilesQuery = useWorkTimeProfilesQuery({ includeArchived: showArchived })
  const createProfile = useCreateWorkTimeProfileMutation()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')

  async function handleCreate(payload: ModelFormPayload) {
    await createProfile.mutateAsync({ ...payload, flex_frame_mode: payload.flex_frame_mode ?? 'TENANT', name: name.trim() })
    setName('')
    setCreating(false)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-slate-900">Arbeitszeitmodelle</h1>
        {!creating && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Neues Arbeitszeitmodell
          </Button>
        )}
      </div>

      <p className="text-sm text-slate-500">
        Ein Modell (z. B. „Vollzeit Büro“) bündelt Soll, Arbeitstage, Pause, Kernzeit, Gleitzeit-Rahmen und die Toleranz
        der Pünktlichkeitsprüfung. Zugewiesen wird es am Mitarbeiter (Reiter „Arbeitszeit“) ab einem Stichtag. Ändert sich
        ein Modell ab einem Stichtag, gilt das für alle zugewiesenen Mitarbeiter – die Zeit davor bleibt, wie sie war.
        Wer eigene Werte braucht, bekommt sie weiter individuell am Mitarbeiter.
      </p>

      {creating && (
        <WorkTimeModelForm
          source={null}
          loadToken="new"
          heading="Neues Arbeitszeitmodell"
          withValidFrom={false}
          withTolerance
          extraValid={name.trim() !== ''}
          pending={createProfile.isPending}
          savedText="Arbeitszeitmodell angelegt."
          onSubmit={(payload) => handleCreate(payload)}
          onCancel={() => setCreating(false)}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="profile-name">Name</Label>
            <Input
              id="profile-name"
              className="w-72 max-w-full"
              maxLength={100}
              placeholder="z. B. Vollzeit Büro"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        </WorkTimeModelForm>
      )}

      {profilesQuery.isLoading && <p className="text-slate-500">Lädt…</p>}
      {profilesQuery.isError && <p className="text-red-600">Arbeitszeitmodelle konnten nicht geladen werden.</p>}
      {profilesQuery.data?.length === 0 && (
        <p className="text-sm text-slate-500">Noch kein Arbeitszeitmodell angelegt.</p>
      )}
      {profilesQuery.data?.map((profile) => (
        <ProfileCard key={profile.id} profile={profile} />
      ))}

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />
        Archivierte Modelle anzeigen
      </label>
    </div>
  )
}

function ProfileCard({ profile }: { profile: WorkTimeProfile }) {
  const setModel = useSetWorkTimeProfileModelMutation()
  const updateProfile = useUpdateWorkTimeProfileMutation()
  const deleteProfile = useDeleteWorkTimeProfileMutation()
  const [changing, setChanging] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const historyQuery = useWorkTimeProfileHistoryQuery(showHistory ? profile.id : null)
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState(profile.name)
  const [error, setError] = useState<string | null>(null)

  async function handleChange(payload: ModelFormPayload, validFrom: string) {
    await setModel.mutateAsync({
      profileId: profile.id,
      payload: { ...payload, flex_frame_mode: payload.flex_frame_mode ?? 'TENANT', valid_from: validFrom },
    })
    setChanging(false)
  }

  async function run(action: () => Promise<unknown>, fallback: string) {
    setError(null)
    try {
      await action()
      return true
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback)
      return false
    }
  }

  async function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const ok = await run(
      () => updateProfile.mutateAsync({ profileId: profile.id, payload: { name: newName.trim() } }),
      'Umbenennen fehlgeschlagen.',
    )
    if (ok) setRenaming(false)
  }

  function handleDelete() {
    if (!window.confirm(`Arbeitszeitmodell „${profile.name}“ löschen?`)) return
    void run(() => deleteProfile.mutateAsync(profile.id), 'Löschen fehlgeschlagen.')
  }

  return (
    <section
      aria-label={profile.name}
      className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-700"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        {renaming ? (
          <form className="flex flex-wrap items-center gap-2" onSubmit={handleRename}>
            <Input
              aria-label="Neuer Name"
              className="w-64"
              maxLength={100}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
            />
            <Button type="submit" size="sm" disabled={!newName.trim() || updateProfile.isPending}>
              Übernehmen
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setRenaming(false)}>
              Abbrechen
            </Button>
          </form>
        ) : (
          <p className="text-base font-medium text-slate-900">
            {profile.name}
            {profile.archived && (
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">archiviert</span>
            )}
          </p>
        )}
        {profile.valid_from !== PROFILE_START && <p className="text-slate-500">seit {formatDate(profile.valid_from)}</p>}
      </div>
      <p>{describeVersion(profile)}</p>
      <p className="text-slate-500">
        {profile.employee_count === 0
          ? 'Derzeit keinem Mitarbeiter zugewiesen.'
          : `Zugewiesen (heute oder später): ${profile.employees.join(', ')}`}
      </p>
      {error && <p className="text-red-600">{error}</p>}

      <div className="flex flex-wrap gap-1">
        {!profile.archived && (
          <Button size="sm" variant="outline" onClick={() => setChanging((value) => !value)}>
            Ändern ab Stichtag
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setShowHistory((value) => !value)}>
          {showHistory ? 'Verlauf ausblenden' : 'Verlauf'}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setNewName(profile.name)
            setRenaming(true)
          }}
        >
          Umbenennen
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={updateProfile.isPending}
          onClick={() =>
            void run(
              () => updateProfile.mutateAsync({ profileId: profile.id, payload: { archived: !profile.archived } }),
              'Speichern fehlgeschlagen.',
            )
          }
        >
          {profile.archived ? 'Wieder aktivieren' : 'Archivieren'}
        </Button>
        <Button size="sm" variant="ghost" className="text-red-600" disabled={deleteProfile.isPending} onClick={handleDelete}>
          Löschen
        </Button>
      </div>

      {changing && (
        <WorkTimeModelForm
          source={profile}
          loadToken={`profile-${profile.id}`}
          heading={`„${profile.name}“ ändern ab Stichtag`}
          highlighted
          withTolerance
          validFromHint="Gilt ab diesem Tag für alle zugewiesenen Mitarbeiter und ersetzt spätere Fassungen des Modells. Die Zeit davor bleibt unverändert; liegt bei einem Mitarbeiter ein abgeschlossener Monat ab diesem Tag, wird nichts geändert."
          pending={setModel.isPending}
          savedText="Arbeitszeitmodell gespeichert."
          onSubmit={handleChange}
          onCancel={() => setChanging(false)}
        />
      )}

      {showHistory && historyQuery.data && (
        <div className="flex flex-col divide-y divide-slate-100 border-t border-slate-100">
          {historyQuery.data.map((version) => (
            <div key={version.id} className="flex flex-wrap gap-x-4 gap-y-1 py-2">
              <span className="w-48 font-medium text-slate-800">
                {version.valid_from === PROFILE_START
                  ? `von Anfang an – ${version.valid_to ? formatDate(version.valid_to) : 'heute'}`
                  : formatRange(version)}
              </span>
              <span className="flex-1 text-slate-600">{describeVersion(version)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
