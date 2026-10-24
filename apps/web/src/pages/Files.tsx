import { Heading, Text, ToggleGroup } from '@instructure/ui'
import { useSearchParams } from 'react-router-dom'

import { useMaterials } from '../api/hooks'
import KindIcon from '../components/KindIcon'
import PdfViewer from '../components/PdfViewer'
import QueryState from '../components/QueryState'
import { useCurrentCourse } from '../shell/CourseLayout'
import { useDocumentTitle } from './PlaceholderPage'

const KIND_LABELS: Record<string, string> = { slides: 'Slides', lecture: 'Lecture', reading: 'Reading', exam: 'Exam' }

/** Course materials grouped by module. The selected file (?file=<id>) opens in the browser's PDF viewer. */
export default function Files() {
  const course = useCurrentCourse()
  const materials = useMaterials(course.id)
  const [params, setParams] = useSearchParams()
  useDocumentTitle('Files')

  return (
    <>
      <Heading level="h1" margin="0 0 medium">Files</Heading>
      <QueryState query={materials} label="files">
        {(modules) => {
          const all = modules.flatMap((m) => m.materials)
          if (all.length === 0) return <Text>No files have been shared yet.</Text>
          const selected = all.find((m) => String(m.file.id) === params.get('file')) ?? null
          return (
            <div className="files-layout">
              <nav aria-label="Course files" className="files-layout__list stack">
                {modules.map((m) => (
                  <ToggleGroup key={m.label} defaultExpanded toggleLabel={(e) => `${e ? 'Collapse' : 'Expand'} ${m.label}`}
                    summary={<Text weight="bold" size="small">{m.label}</Text>} size="small">
                    <ul className="plain-list">
                      {m.materials.map((mat) => (
                        <li key={mat.id}>
                          <button type="button" className="file-button"
                            aria-current={selected?.id === mat.id ? 'true' : undefined}
                            onClick={() => setParams({ file: String(mat.file.id) })}>
                            <KindIcon kind={mat.kind} />
                            <span>
                              {mat.title}
                              <Text as="span" size="x-small" color="secondary">
                                {' '}· {KIND_LABELS[mat.kind] ?? mat.kind}
                                {mat.file.page_count ? ` · ${mat.file.page_count} pp` : ''}
                              </Text>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </ToggleGroup>
                ))}
              </nav>
              <section className="files-layout__viewer" aria-label="File preview">
                {selected ? <PdfViewer file={selected.file} /> : <Text color="secondary">Select a file to preview it.</Text>}
              </section>
            </div>
          )
        }}
      </QueryState>
    </>
  )
}
