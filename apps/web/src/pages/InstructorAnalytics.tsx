import { Alert, Heading, Spinner, Text, View } from '@instructure/ui'
import type { Session } from '@supabase/supabase-js'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { analyticsGet, ApiError } from '../api/client'
import { useAnalyticsSummary } from '../api/hooks'
import { createAnalyticsClient } from '../api/supabase'
import type { AnalyticsCourse, AnalyticsDashboard, AnalyticsPerformance } from '../api/types'
import ApiErrorAlert from '../shell/ApiErrorAlert'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useDemoUser } from '../shell/demoUser'
import { useDocumentTitle } from './PlaceholderPage'

export default function InstructorAnalytics() {
  const course = useCurrentCourse()
  const { userId } = useDemoUser()
  const { error, isPending } = useAnalyticsSummary(course.id)
  useDocumentTitle('Instructor Analytics')
  return <>
    <Heading level="h1" margin="0 0 medium">Instructor Analytics</Heading>
    {isPending ? <Spinner renderTitle="Loading analytics" /> : error ? <ApiErrorAlert error={error} /> :
      <AnalyticsConnection key={userId} canvasCourseId={course.id} />}
  </>
}

function AnalyticsConnection({ canvasCourseId }: { canvasCourseId: number }) {
  const client = useMemo(createAnalyticsClient, [])
  const queryClient = useQueryClient()
  const [session, setSession] = useState<Session | null>(null)
  const [cacheScope, setCacheScope] = useState(() => crypto.randomUUID())
  const [loginError, setLoginError] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!client) return
    void client.auth.startAutoRefresh()
    const { data } = client.auth.onAuthStateChange((_event, next) => {
      queryClient.removeQueries({ queryKey: ['supabase-analytics'] })
      setCacheScope(crypto.randomUUID())
      setSession(next)
    })
    return () => {
      data.subscription.unsubscribe()
      client.auth.stopAutoRefresh()
      queryClient.removeQueries({ queryKey: ['supabase-analytics'] })
    }
  }, [client, queryClient])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!client) return
    const form = event.currentTarget
    const values = new FormData(form)
    const email = String(values.get('email') ?? '')
    const password = String(values.get('password') ?? '')
    form.reset()
    setBusy(true)
    setLoginError(false)
    try {
      const { error } = await client.auth.signInWithPassword({ email, password })
      setLoginError(!!error)
    } catch { setLoginError(true) }
    finally { setBusy(false) }
  }

  function signOut() {
    setSession(null)
    queryClient.removeQueries({ queryKey: ['supabase-analytics'] })
    void client?.auth.signOut({ scope: 'local' }).catch(() => {})
  }

  if (!client) return <Alert variant="info">Analytics connection is not configured. Contact the project team.</Alert>
  if (!session) return <section aria-label="Analytics sign-in">
    <Text as="p">Sign in with your course account to view shared analytics.</Text>
    <form onSubmit={signIn} className="analytics-login">
      <label>Email<input type="email" name="email" autoComplete="username" required /></label>
      <label>Password<input type="password" name="password" autoComplete="current-password" required /></label>
      <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in to analytics'}</button>
    </form>
    {loginError && <Alert variant="error">Sign-in failed. Check your course account and try again.</Alert>}
  </section>
  return <>
    <p>Signed in to shared analytics. <button type="button" onClick={signOut}>Sign out</button></p>
    <ConnectedResults token={session.access_token} cacheScope={cacheScope} canvasCourseId={canvasCourseId} />
  </>
}

function ConnectedResults({ token, cacheScope, canvasCourseId }: { token: string; cacheScope: string; canvasCourseId: number }) {
  const [selected, setSelected] = useState('')
  const courses = useQuery({
    queryKey: ['supabase-analytics', cacheScope, 'courses'],
    queryFn: ({ signal }) => analyticsGet<AnalyticsCourse[]>('/courses', token, signal),
  })
  const staffCourses = courses.data?.filter(c => c.role === 'instructor' || c.role === 'ta') ?? []
  const matching = staffCourses.filter(c => c.canvas_id === String(canvasCourseId))
  const courseId = staffCourses.some(c => c.id === selected) ? selected : matching.length === 1 ? matching[0].id : ''
  const course = staffCourses.find(c => c.id === courseId)
  const results = useQuery({
    queryKey: ['supabase-analytics', cacheScope, 'summary', courseId],
    queryFn: ({ signal }) => analyticsGet<AnalyticsDashboard>(`/courses/${courseId}/summary`, token, signal),
    enabled: !!courseId,
    refetchOnWindowFocus: true,
    staleTime: 0,
  })
  if (courses.isPending) return <Spinner renderTitle="Loading analytics courses" />
  if (courses.error) return <AnalyticsError error={courses.error} />
  if (!staffCourses.length) return <Alert variant="warning">This account has no instructor or TA course enrollments.</Alert>
  return <>
    <label>Analytics course{' '}
      <select aria-label="Analytics course" value={courseId} onChange={event => setSelected(event.target.value)}>
        <option value="">Choose a shared course</option>
        {staffCourses.map(c => <option key={c.id} value={c.id}>{c.code} — {c.title}</option>)}
      </select>
    </label>
    {course && <Text as="p">Showing {course.code}: {course.title}</Text>}
    {courseId && <>
      <button type="button" onClick={() => void results.refetch()} disabled={results.isFetching}>Refresh results</button>
      {results.isFetching ? <Spinner renderTitle="Checking current analytics" /> :
        results.error ? <AnalyticsError error={results.error} /> : results.data ? <Dashboard data={results.data} token={token} cacheScope={cacheScope} /> : null}
    </>}
  </>
}

function AnalyticsError({ error }: { error: unknown }) {
  const status = error instanceof ApiError ? error.status : 0
  const message = status === 401 ? 'Your analytics session expired. Sign out and sign in again.' :
    status === 403 ? 'Access denied. This account is not course staff.' :
      'Analytics is temporarily unavailable. Try again or contact the project team.'
  return <Alert variant="warning">{message}</Alert>
}

const statuses = {
  no_results: 'No published analytics are available for this course yet.',
  stale: 'These results need to be recomputed because their source evidence changed.',
  incomplete: 'The latest analytics run has not finished publishing.',
  insufficient_evidence: 'There is not enough eligible evidence to display performance estimates.',
}
const percentage = (ratio: number | null) => ratio === null ? 'Unavailable' : `${(ratio * 100).toFixed(1)}%`

export function Dashboard({ data, token, cacheScope }: { data: AnalyticsDashboard; token?: string; cacheScope?: string }) {
  if (data.status === 'stale' || data.status === 'incomplete' || data.status === 'no_results') {
    return <Alert variant="info">{statuses[data.status]}</Alert>
  }
  return <section aria-label="Published analytics">
    {data.status !== 'ready' && <Alert variant="info">{statuses[data.status]}</Alert>}
    <Text as="p">{data.interpretation}</Text>
    {data.computed_at && <p>Computed {new Date(data.computed_at).toLocaleString()}</p>}
    <PerformanceTable title="Class outcomes" rows={data.performance.filter(row => row.scope === 'class_outcome')} />
    <PerformanceTable title="Assessment questions" rows={data.performance.filter(row => row.scope === 'assessment_question')} />
    <Heading level="h2" margin="medium 0">Classified error patterns</Heading>
    {!data.performance.some(row => row.errors?.length) ? <p>No publishable classified error summaries are available. This does not establish that no mistakes occurred.</p> :
      data.performance.filter(row => row.errors?.length && !row.suppressed).map(row => <div key={row.id}>
        <strong>{row.label}</strong>
        <ul>{row.errors.map(error => <li key={error.code}>
          {error.code}: {error.affected_students !== null && error.assessed_students !== null ?
            `${error.affected_students} of ${error.assessed_students} eligible classified students (${percentage(error.prevalence)})` :
            `${error.occurrence_count ?? 'Unavailable'} occurrences`}
        </li>)}</ul>
      </div>)}
    <Heading level="h2" margin="medium 0">Related mistake groups</Heading>
    {!data.clusters.length ? <p>No publishable mistake groups are available.</p> : data.clusters.map(group =>
      <View as="div" key={group.id} borderWidth="small" padding="small" margin="small 0">
        <strong>{group.error_code}</strong>
        {group.representative_text && <blockquote>{group.representative_text}</blockquote>}
        <p>{group.unique_students} students · {group.evidence_count} evidence observations · {group.assessment_origin} · {group.assistance}</p>
        <p>{group.interpretation_limit}</p>
        {token && cacheScope && <ClusterEvidence courseId={data.course_id} arrId={group.id} token={token} cacheScope={cacheScope} />}
      </View>)}
  </section>
}

function ClusterEvidence({ courseId, arrId, token, cacheScope }: { courseId: string; arrId: string; token: string; cacheScope: string }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['supabase-analytics', cacheScope, 'evidence', courseId, arrId],
    queryFn: ({ signal }) => analyticsGet<{ evidence: { id: string; source_type: string; page: number | null; excerpt: string | null }[] }>(
      `/courses/${courseId}/clusters/${arrId}/evidence`, token, signal),
    enabled: open, staleTime: 0,
  })
  return <>
    <button type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>View supporting evidence</button>
    {open && (query.isFetching ? <Spinner renderTitle="Loading evidence" /> : query.error ? <AnalyticsError error={query.error} /> :
      <ul>{query.data?.evidence.map(ref => <li key={ref.id}>
        {ref.source_type}{ref.page !== null ? ` · page ${ref.page}` : ''}
        <blockquote>{ref.excerpt ?? 'No excerpt available.'}</blockquote>
      </li>)}</ul>)}
  </>
}

function PerformanceTable({ title, rows }: { title: string; rows: AnalyticsPerformance[] }) {
  return <>
    <Heading level="h2" margin="medium 0">{title}</Heading>
    {!rows.length ? <p>No results available.</p> : <div className="gradebook" role="region" aria-label={title} tabIndex={0}>
      <table>
        <caption className="visually-hidden">{title}</caption>
        <thead><tr><th scope="col">Dimension</th><th scope="col">Mean student score</th><th scope="col">Pooled points score</th>
          <th scope="col">Eligible students</th><th scope="col">Evidence coverage</th><th scope="col">Evidence observations</th><th scope="col">Status</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}>
          <th scope="row">{row.label}{row.assessment_id && <Text as="div" size="x-small">Assessment {row.assessment_id}</Text>}</th>
          <td>{row.suppressed ? 'Suppressed' : percentage(row.mean_student_ratio)}</td>
          <td>{row.suppressed ? 'Suppressed' : percentage(row.pooled_score_ratio)}</td>
          <td>{row.suppressed ? 'Suppressed' : row.eligible_students ?? 'Unavailable'}</td>
          <td>{row.suppressed ? 'Suppressed' : percentage(row.evidence_coverage_ratio)}</td>
          <td>{row.suppressed ? 'Suppressed' : row.evidence_count ?? 'Unavailable'}</td>
          <td>{row.suppressed ? 'Small cohort suppressed' : row.insufficient_evidence ? 'Insufficient evidence' : 'Available'}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    <Text as="p" size="small">Mean student score weights each eligible student equally. Pooled points score weights their scored points. Unavailable values are not zero.</Text>
  </>
}
