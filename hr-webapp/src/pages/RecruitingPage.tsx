import { useState } from 'react'
import { useRecruitingAccessQuery } from '../api/queries/recruiting'
import { ApplicationsTab } from '../components/recruiting/ApplicationsTab'
import { JobsTab } from '../components/recruiting/JobsTab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'

/** Recruiting: Reiter „Stellen“ und „Bewerbungen“. Admin/HR sehen alles; Konten im Hiring Team nur
 * ihre Stellen. Auch in „Mein Bereich“ eingebettet (Konten ohne Verwaltungsrolle). */
export function RecruitingContent() {
  const access = useRecruitingAccessQuery()
  const [tab, setTab] = useState('applications')
  const [jobId, setJobId] = useState<number | null>(null)

  if (access.isLoading) return <p className="text-sm text-slate-500">Lädt…</p>
  if (!access.data?.enabled || (!access.data.can_manage && !access.data.member)) {
    return <p className="text-sm text-slate-500">Recruiting ist nicht eingeschaltet oder du stehst in keinem Hiring Team.</p>
  }
  const { can_manage: canManage, can_see_salary: canSeeSalary } = access.data

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="applications">Bewerbungen</TabsTrigger>
        <TabsTrigger value="jobs">Stellen</TabsTrigger>
      </TabsList>
      <TabsContent value="applications">
        <ApplicationsTab canManage={canManage} canSeeSalary={canSeeSalary} jobId={jobId} onJobChange={setJobId} />
      </TabsContent>
      <TabsContent value="jobs">
        <JobsTab
          canManage={canManage}
          onShowApplications={(id) => {
            setJobId(id)
            setTab('applications')
          }}
        />
      </TabsContent>
    </Tabs>
  )
}

export function RecruitingPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-900">Recruiting</h1>
      <RecruitingContent />
    </div>
  )
}
