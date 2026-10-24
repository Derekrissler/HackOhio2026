import { Alert, Flex, Heading, Text, View } from '@instructure/ui'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { useSubmission } from '../api/hooks'
import type { SubmissionDetail as Detail } from '../api/types'
import FeedbackList from '../components/FeedbackList'
import PdfViewer from '../components/PdfViewer'
import QueryState from '../components/QueryState'
import ResponseList from '../components/ResponseList'
import RubricTable, { criteriaFromScores } from '../components/RubricTable'
import StatusPill from '../components/StatusPill'
import { formatDateTime, formatPoints } from '../format'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useCrumbs } from '../shell/crumbs'
import { useDocumentTitle } from './PlaceholderPage'

/** Canvas SpeedGrader-style view: the submitted work on the left, scores and comments on the right. */
export default function SubmissionDetail() {
  const course = useCurrentCourse()
  const { submissionId = '' } = useParams()
  const submission = useSubmission(course.id, submissionId)
  const [page, setPage] = useState<number | null>(null)
  const s = submission.data
  const listPath = s?.assessment.kind === 'quiz' ? 'quizzes' : 'assignments'
  useCrumbs(s ? [
    { label: s.assessment.kind === 'quiz' ? 'Quizzes' : 'Assignments', to: listPath },
    { label: s.assessment.title, to: `${listPath}/${s.assessment.id}` },
    { label: s.user_name },
  ] : [])
  useDocumentTitle(s ? `${s.assessment.title}: ${s.user_name}` : 'Submission')

  return (
    <QueryState query={submission} label="submission">
      {(s) => (
        <>
          <Heading level="h1">{s.assessment.title}</Heading>
          <Flex gap="small" alignItems="center" wrap="wrap" margin="0 0 medium">
            <Text color="secondary">{s.user_name}</Text>
            {s.submitted_at && <Text color="secondary">· Submitted {formatDateTime(s.submitted_at)}</Text>}
            <StatusPill status={s} />
          </Flex>
          <div className="submission-layout">
            <div className="submission-layout__main">
              {s.file ? (
                <PdfViewer file={s.file} page={page} />
              ) : s.assessment.kind === 'quiz' && s.responses.length > 0 ? (
                <ResponseList responses={s.responses} />
              ) : (
                <Alert variant="info">{s.missing ? 'Nothing was submitted.' : 'No file for this submission.'}</Alert>
              )}
            </div>
            <aside className="submission-layout__side" aria-label="Grade and feedback">
              <Sidebar s={s} onSelectPage={s.file && !s.file.has_text_layer ? setPage : undefined} />
            </aside>
          </div>
        </>
      )}
    </QueryState>
  )
}

function Sidebar({ s, onSelectPage }: { s: Detail; onSelectPage?: (page: number) => void }) {
  return (
    <>
      <View as="div" padding="small" background="secondary" borderRadius="medium" margin="0 0 medium">
        <Text size="small" color="secondary">Grade</Text>
        <Text as="div" size="x-large" weight="bold">
          {s.excused ? 'Excused' : s.score !== null
            ? `${formatPoints(s.score)} / ${formatPoints(s.assessment.points_possible)}`
            : 'Not graded yet'}
        </Text>
        {s.graded_at && <Text size="x-small" color="secondary">Graded {formatDateTime(s.graded_at)}</Text>}
      </View>
      {!s.results_visible && s.workflow_state !== 'graded' && (
        <Text as="p" size="small">Scores and comments appear here once your instructor grades this submission.</Text>
      )}
      {s.file && s.responses.length > 0 && (
        <section aria-labelledby="question-scores">
          <Heading level="h2" variant="titleCardRegular" id="question-scores" margin="0 0 x-small">
            Question scores
          </Heading>
          {onSelectPage && <Text as="p" size="x-small" color="secondary">Select a question to show its page in the scan.</Text>}
          <ResponseList responses={s.responses} compact onSelectPage={onSelectPage} />
        </section>
      )}
      {s.rubric.length > 0 && (
        <View as="section" margin="medium 0 0">
          <RubricTable criteria={criteriaFromScores(s.rubric)} scores={s.rubric} caption="Rubric" />
        </View>
      )}
      <section aria-labelledby="comments">
        <Heading level="h2" variant="titleCardRegular" id="comments" margin="medium 0 x-small">Comments</Heading>
        <FeedbackList comments={s.comments} empty="No comments." />
      </section>
    </>
  )
}
