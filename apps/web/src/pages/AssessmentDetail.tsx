import { Alert, Flex, Heading, Link, Text, View } from '@instructure/ui'
import { useParams } from 'react-router-dom'

import { useAssessment, useSubmission } from '../api/hooks'
import type { AssessmentDetail as Detail } from '../api/types'
import HtmlContent from '../components/HtmlContent'
import QueryState from '../components/QueryState'
import QuestionList from '../components/QuestionList'
import ResponseList from '../components/ResponseList'
import RubricTable from '../components/RubricTable'
import StatusPill from '../components/StatusPill'
import { formatDateTime, formatPoints } from '../format'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useCrumbs } from '../shell/crumbs'
import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'
import SubmissionsTable from './SubmissionsTable'

const SUBMISSION_TYPES: Record<string, string> = {
  online_upload: 'a file upload',
  online_quiz: 'an online quiz',
  on_paper: 'on paper',
}

/** Assignment and quiz detail (Canvas shows them on separate tabs; the layout is shared). */
export default function AssessmentDetail() {
  const course = useCurrentCourse()
  const { assessmentId = '' } = useParams()
  const assessment = useAssessment(course.id, assessmentId)
  useCrumbs(assessment.data ? [{ label: assessment.data.title }] : [])
  useDocumentTitle(assessment.data?.title ?? 'Assignment')

  return (
    <QueryState query={assessment} label="assignment">
      {(a) => (
        <>
          <Heading level="h1">{a.title}</Heading>
          <Text as="p" color="secondary">
            <strong>Points</strong> {formatPoints(a.points_possible)} · <strong>Due</strong> {formatDateTime(a.due_at)} ·{' '}
            <strong>Submitting</strong> {a.submission_types.map((t) => SUBMISSION_TYPES[t] ?? t).join(', ')} ·{' '}
            {a.group_name}{a.group_weight > 0 ? ` (${a.group_weight}% of total)` : ''}
          </Text>
          <HtmlContent html={a.description_html} />
          {course.role === 'student' && <MySubmission courseId={course.id} a={a} />}
          {a.questions ? (
            course.role === 'student' && a.kind === 'quiz' ? null : (
              <View as="section" margin="large 0 0" aria-labelledby="questions">
                <Heading level="h2" id="questions" margin="0 0 small">Questions</Heading>
                <QuestionList questions={a.questions} />
              </View>
            )
          ) : (
            <Alert variant="info" margin="medium 0">{a.questions_hidden_reason}</Alert>
          )}
          {a.rubric.length > 0 && (
            <View as="section" margin="large 0 0" aria-labelledby="rubric">
              <Heading level="h2" id="rubric" margin="0 0 small">Rubric</Heading>
              <RubricTable criteria={a.rubric} caption={`${a.title} rubric`} />
            </View>
          )}
          {course.role === 'teacher' && <SubmissionsTable courseId={course.id} assessmentId={a.id} />}
        </>
      )}
    </QueryState>
  )
}

function MySubmission({ courseId, a }: { courseId: number; a: Detail }) {
  const link = useRouterLink()
  const mine = a.my_submission
  const showQuizResults = a.kind === 'quiz' && mine?.workflow_state === 'graded' && !mine.missing
  const submission = useSubmission(courseId, showQuizResults ? mine!.id : undefined)
  if (!mine) return null
  const to = `/courses/${courseId}/submissions/${mine.id}`
  return (
    <View as="section" margin="medium 0" padding="small medium" borderWidth="small" borderRadius="medium"
      background="secondary" aria-labelledby="my-submission">
      <Flex justifyItems="space-between" alignItems="center" wrap="wrap" gap="small">
        <Heading level="h2" variant="titleSection" id="my-submission">Your submission</Heading>
        <Flex gap="small" alignItems="center">
          <StatusPill status={mine} />
          <Text weight="bold" size="large">
            {mine.score !== null ? `${formatPoints(mine.score)} / ${formatPoints(a.points_possible)}`
              : mine.workflow_state === 'unsubmitted' ? 'Not submitted' : 'Not graded yet'}
          </Text>
        </Flex>
      </Flex>
      {mine.submitted_at && <Text as="p" size="small">Submitted {formatDateTime(mine.submitted_at)}</Text>}
      {(mine.workflow_state !== 'unsubmitted' && !mine.excused) && a.kind !== 'quiz' && (
        <Link href={to} onClick={link(to)}>View submission and feedback</Link>
      )}
      {showQuizResults && (
        <QueryState query={submission} label="quiz results">
          {(s) => (
            <View as="div" margin="small 0 0">
              <ResponseList responses={s.responses} />
              <Link href={to} onClick={link(to)}>View all comments</Link>
            </View>
          )}
        </QueryState>
      )}
    </View>
  )
}
