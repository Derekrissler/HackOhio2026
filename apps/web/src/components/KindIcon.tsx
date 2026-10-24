import { IconAssignmentLine, IconDocumentLine, IconPdfLine, IconQuizLine } from '@instructure/ui'

const ICONS = {
  homework: IconAssignmentLine,
  exam: IconAssignmentLine,
  quiz: IconQuizLine,
  slides: IconPdfLine,
  lecture: IconPdfLine,
  reading: IconDocumentLine,
} as const

export default function KindIcon({ kind }: { kind: string }) {
  const Icon = ICONS[kind as keyof typeof ICONS] ?? IconDocumentLine
  return <Icon size="x-small" />
}
