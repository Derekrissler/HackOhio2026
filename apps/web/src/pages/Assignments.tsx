import { Heading, Text, ToggleGroup } from '@instructure/ui'

import { useAssignmentGroups } from '../api/hooks'
import type { AssessmentKind } from '../api/types'
import AssessmentRow from '../components/AssessmentRow'
import QueryState from '../components/QueryState'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useDocumentTitle } from './PlaceholderPage'

/** Assignments (all kinds) or Quizzes (`kinds={['quiz']}`), grouped by assignment group. */
export default function Assignments({ title = 'Assignments', kinds }: { title?: string; kinds?: AssessmentKind[] }) {
  const course = useCurrentCourse()
  const groups = useAssignmentGroups(course.id)
  useDocumentTitle(title)

  return (
    <>
      <Heading level="h1" margin="0 0 medium">{title}</Heading>
      <QueryState query={groups} label={title.toLowerCase()}>
        {(data) => {
          const shown = data
            .map((g) => ({ ...g, assessments: g.assessments.filter((a) => !kinds || kinds.includes(a.kind)) }))
            .filter((g) => g.assessments.length > 0 || !kinds)
          if (shown.length === 0) return <Text>No {title.toLowerCase()} yet.</Text>
          return <div className="stack">{shown.map((g) => (
            <ToggleGroup
              key={g.id}
              defaultExpanded
              toggleLabel={(expanded) => `${expanded ? 'Collapse' : 'Expand'} ${g.name}`}
              summary={
                <span>
                  <Text weight="bold">{g.name}</Text>
                  {g.weight > 0 && <Text size="small" color="secondary"> · {g.weight}% of total</Text>}
                </span>
              }
            >
              {g.assessments.length === 0 ? (
                <Text as="p" color="secondary">Nothing in this group yet.</Text>
              ) : (
                <ul className="plain-list divided">
                  {g.assessments.map((a) => (
                    <li key={a.id}><AssessmentRow courseId={course.id} assessment={a} /></li>
                  ))}
                </ul>
              )}
            </ToggleGroup>
          ))}</div>
        }}
      </QueryState>
    </>
  )
}
