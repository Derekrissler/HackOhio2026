import { Pill } from '@instructure/ui'

import type { WorkflowState } from '../api/types'

interface Status {
  workflow_state: WorkflowState
  late: boolean
  missing: boolean
  excused: boolean
}

/** Canvas-style status pill; renders nothing for plain graded work. */
export default function StatusPill({ status, showSubmitted = true }: { status: Status; showSubmitted?: boolean }) {
  if (status.excused) return <Pill>Excused</Pill>
  if (status.missing) return <Pill color="danger">Missing</Pill>
  if (status.late) return <Pill color="warning">Late</Pill>
  if (status.workflow_state === 'submitted' && showSubmitted) return <Pill color="info">Submitted</Pill>
  return null
}
