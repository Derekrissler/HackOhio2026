import { Flex, Heading, Pill, Text, View } from '@instructure/ui'

import type { Question } from '../api/types'
import { formatPoints } from '../format'
import HtmlContent from './HtmlContent'

/** Questions with answer keys and aligned outcomes when the API includes them (teacher, or graded). */
export default function QuestionList({ questions }: { questions: Question[] }) {
  const parentIds = new Set(questions.map((q) => q.parent_id).filter((id) => id !== null))
  return (
    <ol className="question-list">
      {questions.map((q) => {
        const isStem = parentIds.has(q.id)
        return (
          <li key={q.id} className={q.parent_id ? 'question-list__part' : undefined}>
            <View as="div" padding="small" borderWidth="small" borderRadius="medium" background={isStem ? 'secondary' : 'primary'}>
              <Flex justifyItems="space-between" alignItems="start" gap="small">
                <Heading level="h3" variant="titleCardMini">{q.label}</Heading>
                <Text size="small" color="secondary">{formatPoints(q.points_possible)} pts</Text>
              </Flex>
              <HtmlContent html={q.prompt_html} />
              {q.choices && (
                <ul className="choice-list">
                  {q.choices.map((c) => (
                    <li key={c} className={c === q.answer_key ? 'is-correct' : undefined}>
                      {c}
                      {c === q.answer_key && <Text size="small" weight="bold"> (correct answer)</Text>}
                    </li>
                  ))}
                </ul>
              )}
              {!isStem && q.answer_key !== null && !q.choices && (
                <Text as="p" size="small"><strong>Answer key:</strong> {q.answer_key}</Text>
              )}
              {q.outcomes.length > 0 && (
                <Flex gap="xx-small" wrap="wrap" margin="x-small 0 0">
                  <Text size="x-small" color="secondary">Aligned outcomes:</Text>
                  {q.outcomes.map((o) => <Pill key={o.id} statusLabel={o.code}>{o.title}</Pill>)}
                </Flex>
              )}
            </View>
          </li>
        )
      })}
    </ol>
  )
}
