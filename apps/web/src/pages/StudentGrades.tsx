import { Flex, Heading, Link, Table, Text, ToggleDetails, View } from '@instructure/ui'

import { useGrades } from '../api/hooks'
import type { GradeRow, Grades } from '../api/types'
import { assessmentPath } from '../components/AssessmentRow'
import FeedbackList from '../components/FeedbackList'
import QueryState from '../components/QueryState'
import RubricTable, { criteriaFromScores } from '../components/RubricTable'
import StatusPill from '../components/StatusPill'
import { formatDateTime, formatPercent, formatPoints } from '../format'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'

/** Canvas grade summary for one student (the student themself, or a teacher looking). */
export default function StudentGrades({ userId }: { userId: number }) {
  const course = useCurrentCourse()
  const grades = useGrades(course.id, userId)
  useDocumentTitle(grades.data ? `Grades for ${grades.data.user_name}` : 'Grades')
  return (
    <QueryState query={grades} label="grades">
      {(g) => (
        <>
          <Heading level="h1" margin="0 0 medium">Grades for {g.user_name}</Heading>
          <div className="grades-layout">
            <div className="table-scroll">
              <Table caption={`Grades for ${g.user_name}`} layout="auto">
                <Table.Head>
                  <Table.Row>
                    <Table.ColHeader id="name">Name</Table.ColHeader>
                    <Table.ColHeader id="due">Due</Table.ColHeader>
                    <Table.ColHeader id="status">Status</Table.ColHeader>
                    <Table.ColHeader id="score" textAlign="end">Score</Table.ColHeader>
                  </Table.Row>
                </Table.Head>
                <Table.Body>
                  {g.rows.map((row) => (
                    <Table.Row key={row.assessment_id}>
                      <Table.Cell><NameCell courseId={course.id} row={row} groupName={groupName(g, row)} /></Table.Cell>
                      <Table.Cell>{formatDateTime(row.due_at)}</Table.Cell>
                      <Table.Cell><StatusPill status={row} /></Table.Cell>
                      <Table.Cell textAlign="end">
                        <Text weight="bold">{row.score === null ? '–' : formatPoints(row.score)}</Text>
                        <Text color="secondary"> / {formatPoints(row.points_possible)}</Text>
                      </Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table>
            </div>
            <Totals g={g} />
          </div>
        </>
      )}
    </QueryState>
  )
}

function groupName(g: Grades, row: GradeRow) {
  return g.groups.find((gr) => gr.id === row.group_id)?.name ?? ''
}

function NameCell({ courseId, row, groupName }: { courseId: number; row: GradeRow; groupName: string }) {
  const link = useRouterLink()
  const to = assessmentPath(courseId, { id: row.assessment_id, kind: row.kind })
  const n = row.comments.length
  const summary = [n ? `${n} comment${n === 1 ? '' : 's'}` : '', row.rubric.length ? 'rubric' : '']
    .filter(Boolean).join(' and ')
  return (
    <>
      <Link href={to} onClick={link(to)}>{row.title}</Link>
      <Text as="div" size="x-small" color="secondary">{groupName}</Text>
      {summary && (
        <ToggleDetails summary={summary[0].toUpperCase() + summary.slice(1)} size="small">
          <FeedbackList comments={row.comments} />
          {row.rubric.length > 0 && (
            <RubricTable criteria={criteriaFromScores(row.rubric)} scores={row.rubric} caption={`${row.title} rubric`} />
          )}
          {row.submission_id && (
            <Link href={`/courses/${courseId}/submissions/${row.submission_id}`}
              onClick={link(`/courses/${courseId}/submissions/${row.submission_id}`)}>
              Open submission
            </Link>
          )}
        </ToggleDetails>
      )}
    </>
  )
}

function Totals({ g }: { g: Grades }) {
  return (
    <aside aria-label="Total grade">
      <View as="div" padding="small medium" background="secondary" borderRadius="medium">
        <Text size="small" color="secondary">Total</Text>
        <Text as="div" size="xx-large" weight="bold">{formatPercent(g.current_percent)}</Text>
        <Text size="x-small" color="secondary">Calculated from graded work only</Text>
      </View>
      {g.weighted && (
        <View as="div" margin="medium 0 0">
          <Table caption="Assignments are weighted by group" layout="auto">
            <Table.Head>
              <Table.Row>
                <Table.ColHeader id="group">Group</Table.ColHeader>
                <Table.ColHeader id="weight" textAlign="end">Weight</Table.ColHeader>
                <Table.ColHeader id="pct" textAlign="end">Score</Table.ColHeader>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {g.groups.map((gr) => (
                <Table.Row key={gr.id}>
                  <Table.Cell>{gr.name}</Table.Cell>
                  <Table.Cell textAlign="end">{gr.weight}%</Table.Cell>
                  <Table.Cell textAlign="end">{formatPercent(gr.percent)}</Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </View>
      )}
      <Flex margin="small 0 0"><Text size="x-small" color="secondary">Groups with no graded work are left out of the total.</Text></Flex>
    </aside>
  )
}
