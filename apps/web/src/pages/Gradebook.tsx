import { Heading, Link, Pill, Text } from '@instructure/ui'

import { useGradebook } from '../api/hooks'
import type { GradebookCell } from '../api/types'
import { assessmentPath } from '../components/AssessmentRow'
import QueryState from '../components/QueryState'
import { formatPercent, formatPoints } from '../format'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'

/** Read-only gradebook: students × assessments. A plain table so it can scroll with a sticky first column. */
export default function Gradebook() {
  const course = useCurrentCourse()
  const gradebook = useGradebook(course.id)
  const link = useRouterLink()
  useDocumentTitle('Gradebook')

  return (
    <>
      <Heading level="h1" margin="0 0 medium">Gradebook</Heading>
      <QueryState query={gradebook} label="gradebook">
        {(gb) => (
          <div className="gradebook" role="region" aria-label="Gradebook grid" tabIndex={0}>
            <table>
              <caption className="visually-hidden">Scores for every student and assessment</caption>
              <thead>
                <tr>
                  <th scope="col">Student</th>
                  <th scope="col">Total</th>
                  {gb.assessments.map((a) => {
                    const to = assessmentPath(course.id, a)
                    return (
                      <th scope="col" key={a.id}>
                        <Link href={to} onClick={link(to)} isWithinText={false}>{a.title.split(':')[0]}</Link>
                        <Text as="div" size="x-small" color="secondary">out of {formatPoints(a.points_possible)}</Text>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {gb.students.map((s) => {
                  const to = `/courses/${course.id}/grades/${s.id}`
                  return (
                    <tr key={s.id}>
                      <th scope="row"><Link href={to} onClick={link(to)} isWithinText={false}>{s.sortable_name}</Link></th>
                      <td className="num"><strong>{formatPercent(s.current_percent)}</strong></td>
                      {s.cells.map((cell, i) => (
                        <td key={gb.assessments[i].id} className="num"><Cell courseId={course.id} cell={cell} /></td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </QueryState>
    </>
  )
}

function Cell({ courseId, cell }: { courseId: number; cell: GradebookCell }) {
  const link = useRouterLink()
  if (cell.excused) return <Pill>EX</Pill>
  if (cell.missing) return <Pill color="danger">Missing</Pill>
  if (cell.workflow_state === 'unsubmitted' || cell.submission_id === null) return <Text color="secondary">–</Text>
  const to = `/courses/${courseId}/submissions/${cell.submission_id}`
  const label = cell.score === null ? 'Needs grading' : formatPoints(cell.score)
  return (
    <Link href={to} onClick={link(to)} isWithinText={false}>
      {cell.score === null ? <Text size="x-small">{label}</Text> : label}
    </Link>
  )
}
