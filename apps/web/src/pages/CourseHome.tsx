import { Flex, Heading, Link, List, Text, View } from '@instructure/ui'

import { useHome } from '../api/hooks'
import AssessmentRow from '../components/AssessmentRow'
import FeedbackList from '../components/FeedbackList'
import QueryState from '../components/QueryState'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'

export default function CourseHome() {
  const course = useCurrentCourse()
  const home = useHome(course.id)
  const link = useRouterLink()
  useDocumentTitle(course.name)

  return (
    <>
      <Heading level="h1">{course.name}</Heading>
      <Text as="p" color="secondary">
        {[course.code, course.term, `Enrolled as ${course.role}`].filter(Boolean).join(' · ')}
      </Text>
      <QueryState query={home} label="course home">
        {(data) => (
          <Flex gap="large" alignItems="start" wrap="wrap">
            <Flex.Item shouldGrow shouldShrink size="20rem">
              {course.role === 'student' ? (
                <section aria-labelledby="recent-feedback">
                  <Heading level="h2" id="recent-feedback" margin="medium 0 small">Recent Feedback</Heading>
                  {data.recent_feedback.length === 0 && <Text color="secondary">No feedback yet.</Text>}
                  {data.recent_feedback.map((f) => {
                    const to = `/courses/${course.id}/submissions/${f.submission_id}`
                    return (
                      <View as="div" key={f.id} margin="0 0 small">
                        <Link href={to} onClick={link(to)}>{f.assessment_title}</Link>
                        <FeedbackList comments={[f]} />
                      </View>
                    )
                  })}
                </section>
              ) : (
                <section aria-labelledby="to-do">
                  <Heading level="h2" id="to-do" margin="medium 0 small">To Do</Heading>
                  {data.needs_grading.length === 0 && <Text color="secondary">Nothing to grade.</Text>}
                  <List isUnstyled itemSpacing="small">
                    {data.needs_grading.map((n) => {
                      const to = `/courses/${course.id}/assignments/${n.assessment_id}`
                      return (
                        <List.Item key={n.assessment_id}>
                          <Link href={to} onClick={link(to)}>Grade {n.title}</Link>
                          <Text as="div" size="small" color="secondary">
                            {n.count} submission{n.count === 1 ? '' : 's'} waiting
                          </Text>
                        </List.Item>
                      )
                    })}
                  </List>
                </section>
              )}
            </Flex.Item>
            <Flex.Item size="18rem" shouldShrink as="aside">
              <section aria-labelledby="coming-up">
                <Heading level="h2" id="coming-up" margin="medium 0 small">Coming Up</Heading>
                {data.upcoming.length === 0 && <Text color="secondary">Nothing due in the next two weeks.</Text>}
                <ul className="plain-list">
                  {data.upcoming.map((a) => (
                    <li key={a.id}><AssessmentRow courseId={course.id} assessment={a} /></li>
                  ))}
                </ul>
              </section>
            </Flex.Item>
          </Flex>
        )}
      </QueryState>
    </>
  )
}
