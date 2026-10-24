/**
 * Renders HTML authored in the LMS (syllabus, descriptions, question prompts).
 * Safe today because it only comes from our own seed. Phase 4 ingests real Canvas HTML and
 * must sanitize it before rendering (see the Phase 3 summary's risk list).
 */
export default function HtmlContent({ html, className }: { html: string | null; className?: string }) {
  if (!html) return null
  return <div className={`user-content ${className ?? ''}`} dangerouslySetInnerHTML={{ __html: html }} />
}
