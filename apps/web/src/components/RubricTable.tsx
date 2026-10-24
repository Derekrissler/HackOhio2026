import { Pill, Table, Text } from '@instructure/ui'

import type { RubricCriterion, RubricScore } from '../api/types'
import { formatPoints } from '../format'

/** The rubric's criteria, with the student's scores when `scores` is given. */
export default function RubricTable({
  criteria,
  scores,
  caption,
}: {
  criteria: RubricCriterion[]
  scores?: RubricScore[]
  caption: string
}) {
  const byId = new Map(scores?.map((s) => [s.criterion_id, s]))
  const total = criteria.reduce((sum, c) => sum + c.points, 0)
  return (
    <Table caption={caption} layout="auto">
      <Table.Head>
        <Table.Row>
          <Table.ColHeader id="criterion">Criteria</Table.ColHeader>
          <Table.ColHeader id="points" textAlign="end">Pts</Table.ColHeader>
        </Table.Row>
      </Table.Head>
      <Table.Body>
        {criteria.map((c) => {
          const score = byId.get(c.id)
          return (
            <Table.Row key={c.id}>
              <Table.Cell>
                <Text weight="bold">{c.description}</Text>
                {c.outcome && <> <Pill>{c.outcome.code}</Pill></>}
                {c.long_description && <Text as="div" size="small" color="secondary">{c.long_description}</Text>}
                {score?.comment && <Text as="div" size="small"><em>{score.comment}</em></Text>}
              </Table.Cell>
              <Table.Cell textAlign="end">
                {score ? `${formatPoints(score.points ?? 0)} / ${formatPoints(c.points)}` : `${formatPoints(c.points)} pts`}
              </Table.Cell>
            </Table.Row>
          )
        })}
        <Table.Row>
          <Table.Cell><Text weight="bold">Total points</Text></Table.Cell>
          <Table.Cell textAlign="end">
            {scores
              ? `${formatPoints(scores.reduce((s, r) => s + (r.points ?? 0), 0))} / ${formatPoints(total)}`
              : formatPoints(total)}
          </Table.Cell>
        </Table.Row>
      </Table.Body>
    </Table>
  )
}

/** Turn submission rubric scores into the criteria shape RubricTable expects. */
export function criteriaFromScores(scores: RubricScore[]): RubricCriterion[] {
  return scores.map((s) => ({
    id: s.criterion_id, description: s.description, long_description: null, points: s.points_possible, outcome: null,
  }))
}
