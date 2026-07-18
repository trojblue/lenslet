import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { EmbeddingSpec } from '../../../lib/types'
import SimilarityModal from '../SimilarityModal'

const EMBEDDINGS: EmbeddingSpec[] = [{
  name: 'clip',
  dimension: 768,
  metric: 'cosine',
  dtype: 'float32',
}]

function renderModal(selectedPath: string | null): string {
  return renderToStaticMarkup(
    <SimilarityModal
      embeddings={EMBEDDINGS}
      selectedPath={selectedPath}
      onClose={() => {}}
      onSearch={async () => true}
    />,
  )
}

describe('SimilarityModal prepared presentation', () => {
  it('mounts a selected path in the stable path-mode shell', () => {
    const html = renderModal('/sample.jpg')

    expect(html).toContain('similarity-modal-shell')
    expect(html).toContain('similarity-modal-body scrollbar-thin')
    expect(html).toContain('similarity-modal-query')
    expect(html).toContain('similarity-modal-status')
    expect(html).toContain('value="/sample.jpg"')
    expect(html).toMatch(/aria-pressed="true"[^>]*>Selected image/)
  })

  it('mounts vector mode directly when no path is selected', () => {
    const html = renderModal(null)

    expect(html).toContain('Vector (base64 float32)')
    expect(html).toMatch(/aria-pressed="true"[^>]*>Vector input/)
    expect(html).not.toContain('placeholder="Select an image first"')
  })
})
