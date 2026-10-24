import { Flex, Pill, Text, View } from '@instructure/ui'

import type { Feedback } from '../api/types'
import { formatDateTime } from '../format'

export default function FeedbackList({ comments, empty }: { comments: Feedback[]; empty?: string }) {
  if (comments.length === 0) {
    return empty ? <Text color="secondary" size="small">{empty}</Text> : null
  }
  return (
    <ul className="feedback-list">
      {comments.map((c) => (
        <li key={c.id}>
          <View as="div" background={c.visible_to_student ? 'secondary' : 'primary'} borderWidth="small"
            borderRadius="medium" padding="x-small small">
            <Flex gap="x-small" alignItems="center" wrap="wrap">
              <Text weight="bold" size="small">{c.author_name}</Text>
              <Text color="secondary" size="x-small">{formatDateTime(c.created_at)}</Text>
              {!c.visible_to_student && <Pill color="warning">Teacher only</Pill>}
            </Flex>
            <Text as="p" size="small">{c.text}</Text>
          </View>
        </li>
      ))}
    </ul>
  )
}
