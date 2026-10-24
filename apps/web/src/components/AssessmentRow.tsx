import { Flex, Link, Text } from '@instructure/ui'

import type { AssessmentSummary } from '../api/types'
import { formatDateTime, formatPoints } from '../format'
import { useRouterLink } from '../shell/useRouterLink'
import KindIcon from './KindIcon'
import StatusPill from './StatusPill'

export function assessmentPath(courseId: number, a: { id: number; kind: string }): string {
  return `/courses/${courseId}/${a.kind === 'quiz' ? 'quizzes' : 'assignments'}/${a.id}`
}

/** One assessment in a list: icon, linked title, due date, points and the viewer's status. */
export default function AssessmentRow({ courseId, assessment: a }: { courseId: number; assessment: AssessmentSummary }) {
  const link = useRouterLink()
  const to = assessmentPath(courseId, a)
  const mine = a.my_submission
  return (
    <Flex gap="small" alignItems="start" padding="small">
      <Flex.Item padding="xxx-small 0 0"><KindIcon kind={a.kind} /></Flex.Item>
      <Flex.Item shouldGrow shouldShrink>
        <Link href={to} onClick={link(to)} isWithinText={false}>
          <Text weight="bold">{a.title}</Text>
        </Link>
        <Text as="div" size="small" color="secondary">
          <strong>Due</strong> {formatDateTime(a.due_at)} | {formatPoints(a.points_possible)} pts
          {a.submission_counts &&
            ` | ${a.submission_counts.submitted} of ${a.submission_counts.total} submitted, ${a.submission_counts.graded} graded`}
        </Text>
      </Flex.Item>
      {mine && (
        <Flex.Item>
          <Flex gap="x-small" alignItems="center">
            <StatusPill status={mine} />
            {mine.score !== null && (
              <Text weight="bold">{formatPoints(mine.score)}/{formatPoints(a.points_possible)}</Text>
            )}
          </Flex>
        </Flex.Item>
      )}
    </Flex>
  )
}
