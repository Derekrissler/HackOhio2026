import { Heading, Link, Table, Text, View } from '@instructure/ui'

import { useSyllabus } from '../api/hooks'
import { assessmentPath } from '../components/AssessmentRow'
import HtmlContent from '../components/HtmlContent'
import QueryState from '../components/QueryState'
import { formatDay, parseUtc, formatPoints } from '../format'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'

const timeFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })

export default function Syllabus() {
  const course = useCurrentCourse()
  const syllabus = useSyllabus(course.id)
  const link = useRouterLink()
  useDocumentTitle('Syllabus')

  return (
    <>
      <Heading level="h1" margin="0 0 medium">Course Syllabus</Heading>
      <QueryState query={syllabus} label="syllabus">
        {(data) => (
          <>
            {/* The syllabus HTML contains the objectives list; shell.css styles it as a callout. */}
            <HtmlContent html={data.syllabus_html} className="syllabus-body" />
            <View as="section" margin="large 0 0" aria-labelledby="course-summary">
              <Heading level="h2" id="course-summary" margin="0 0 small">Course Summary</Heading>
              <Table caption="Course summary: all assessments by due date" layout="auto">
                <Table.Head>
                  <Table.Row>
                    <Table.ColHeader id="date">Date</Table.ColHeader>
                    <Table.ColHeader id="details">Details</Table.ColHeader>
                    <Table.ColHeader id="due" textAlign="end">Due</Table.ColHeader>
                  </Table.Row>
                </Table.Head>
                <Table.Body>
                  {data.summary.map((a) => {
                    const to = assessmentPath(course.id, a)
                    return (
                      <Table.Row key={a.id}>
                        <Table.Cell>{a.due_at ? formatDay(a.due_at) : '–'}</Table.Cell>
                        <Table.Cell>
                          <Link href={to} onClick={link(to)}>{a.title}</Link>
                          <Text size="small" color="secondary"> ({formatPoints(a.points_possible)} pts)</Text>
                        </Table.Cell>
                        <Table.Cell textAlign="end">
                          {a.due_at ? `due by ${timeFormat.format(parseUtc(a.due_at)).toLowerCase()}` : ''}
                        </Table.Cell>
                      </Table.Row>
                    )
                  })}
                </Table.Body>
              </Table>
            </View>
          </>
        )}
      </QueryState>
    </>
  )
}
