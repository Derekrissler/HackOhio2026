import { Flex, IconCheckMarkSolid, IconXSolid, Text, View } from '@instructure/ui'

import type { QuestionResponse } from '../api/types'
import { formatPoints } from '../format'
import FeedbackList from './FeedbackList'
import HtmlContent from './HtmlContent'

function Verdict({ r }: { r: QuestionResponse }) {
  if (r.is_correct === null) return null
  return r.is_correct ? (
    <Text color="success" size="small"><IconCheckMarkSolid size="x-small" /> Correct</Text>
  ) : (
    <Text color="danger" size="small"><IconXSolid size="x-small" /> {r.points_awarded ? 'Partially correct' : 'Incorrect'}</Text>
  )
}

/**
 * Per-question answers, scores and comments. `compact` is the submission sidebar: no prompt,
 * and clicking a question with a scan page calls `onSelectPage`.
 */
export default function ResponseList({
  responses,
  compact = false,
  onSelectPage,
}: {
  responses: QuestionResponse[]
  compact?: boolean
  onSelectPage?: (page: number) => void
}) {
  return (
    <ol className="response-list">
      {responses.map((r) => (
        <li key={r.question_id}>
          <View as="div" padding="small" borderWidth="small" borderRadius="medium">
            <Flex justifyItems="space-between" alignItems="start" gap="small">
              <Text weight="bold">
                {onSelectPage && r.source_page ? (
                  <button type="button" className="link-button" onClick={() => onSelectPage(r.source_page!)}>
                    {r.label}
                    <span className="visually-hidden"> (show page {r.source_page} of the scan)</span>
                  </button>
                ) : r.label}
              </Text>
              <Text size="small" weight="bold">
                {r.points_awarded === null ? '–' : formatPoints(r.points_awarded)} / {formatPoints(r.points_possible)}
              </Text>
            </Flex>
            {!compact && <HtmlContent html={r.prompt_html} />}
            {r.response !== null && r.response !== '' && (
              <Text as="p" size="small"><strong>{compact ? 'Answer' : 'Your answer'}:</strong> {r.response}</Text>
            )}
            {r.graded_by === 'manual_entry' && r.response === null && compact && (
              <Text as="p" size="x-small" color="secondary">Handwritten — see the scan.</Text>
            )}
            <Verdict r={r} />
            {r.is_correct === false && r.answer_key && (
              <Text as="p" size="small"><strong>Correct answer:</strong> {r.answer_key}</Text>
            )}
            {r.comments.length > 0 && <View as="div" margin="x-small 0 0"><FeedbackList comments={r.comments} /></View>}
          </View>
        </li>
      ))}
    </ol>
  )
}
