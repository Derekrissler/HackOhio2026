import { Heading, Link, Table, Text, View } from '@instructure/ui'

import { useAssessmentSubmissions } from '../api/hooks'
import QueryState from '../components/QueryState'
import StatusPill from '../components/StatusPill'
import { formatDateTime, formatPoints } from '../format'
import { useRouterLink } from '../shell/useRouterLink'

/** Teacher view: every student's submission for one assessment. */
export default function SubmissionsTable({ courseId, assessmentId }: { courseId: number; assessmentId: number }) {
  const rows = useAssessmentSubmissions(courseId, String(assessmentId), true)
  const link = useRouterLink()
  return (
    <View as="section" margin="large 0 0" aria-labelledby="submissions">
      <Heading level="h2" id="submissions" margin="0 0 small">Submissions</Heading>
      <QueryState query={rows} label="submissions">
        {(data) => (
          <div className="table-scroll">
            <Table caption="Student submissions" layout="auto">
              <Table.Head>
                <Table.Row>
                  <Table.ColHeader id="student">Student</Table.ColHeader>
                  <Table.ColHeader id="submitted">Submitted</Table.ColHeader>
                  <Table.ColHeader id="status">Status</Table.ColHeader>
                  <Table.ColHeader id="score" textAlign="end">Score</Table.ColHeader>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {data.map((s) => {
                  const to = `/courses/${courseId}/submissions/${s.id}`
                  return (
                    <Table.Row key={s.id}>
                      <Table.Cell>
                        {s.workflow_state === 'unsubmitted' ? s.user_name : (
                          <Link href={to} onClick={link(to)}>{s.user_name}</Link>
                        )}
                      </Table.Cell>
                      <Table.Cell>{s.submitted_at ? formatDateTime(s.submitted_at) : <Text color="secondary">–</Text>}</Table.Cell>
                      <Table.Cell>
                        <StatusPill status={s} />
                        {s.workflow_state === 'graded' && !s.missing && !s.excused && <Text size="small">Graded</Text>}
                        {s.workflow_state === 'unsubmitted' && <Text size="small" color="secondary">Not submitted</Text>}
                      </Table.Cell>
                      <Table.Cell textAlign="end">{s.score === null ? '–' : formatPoints(s.score)}</Table.Cell>
                    </Table.Row>
                  )
                })}
              </Table.Body>
            </Table>
          </div>
        )}
      </QueryState>
    </View>
  )
}
