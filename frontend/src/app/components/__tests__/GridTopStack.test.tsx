import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import GridTopStack from '../GridTopStack'
import type { StatusBarProps } from '../StatusBar'

function makeStatusBarProps(overrides: Partial<StatusBarProps> = {}): StatusBarProps {
  return {
    persistenceEnabled: true,
    indexing: null,
    offViewSummary: null,
    onClearOffView: () => {},
    browserZoomPercent: null,
    ...overrides,
  }
}

function renderGridTopStack(overrides: Partial<Parameters<typeof GridTopStack>[0]> = {}): string {
  return renderToStaticMarkup(
    <GridTopStack
      statusBarProps={makeStatusBarProps()}
      actionError={null}
      similarity={null}
      onExitSimilarity={() => {}}
      filterChips={[]}
      onClearFilters={() => {}}
      {...overrides}
    />,
  )
}

describe('GridTopStack bands', () => {
  it('keeps all top bands mounted when hidden', () => {
    const html = renderGridTopStack()
    expect(html).toContain('data-grid-top-band="status"')
    expect(html).toContain('data-grid-top-band="similarity"')
    expect(html).toContain('data-grid-top-band="filters"')
    expect(html).toContain('data-grid-top-band="status" aria-hidden="true"')
    expect(html).toContain('data-grid-top-band="similarity" aria-hidden="true"')
    expect(html).toContain('data-grid-top-band="filters" aria-hidden="true"')
    expect(html.match(/class="grid-top-band-reserve"/g) ?? []).toHaveLength(3)
  })

  it('shows filter band content when chips are active', () => {
    const html = renderGridTopStack({
      filterChips: [
        {
          id: 'star',
          label: 'Stars: 5',
          onRemove: () => {},
        },
      ],
    })
    expect(html).toContain('Stars: 5')
    expect(html).toContain('Clear all')
    expect(html).not.toContain('data-grid-top-band="filters" aria-hidden="true"')
    expect(html.match(/class="grid-top-band-reserve"/g) ?? []).toHaveLength(2)
  })

  it('shows status band for action errors even without status banners', () => {
    const html = renderGridTopStack({
      actionError: 'Upload failed',
    })
    expect(html).toContain('Upload failed')
    expect(html).not.toContain('data-grid-top-band="status" aria-hidden="true"')
    expect(html.match(/class="grid-top-band-reserve"/g) ?? []).toHaveLength(2)
  })
})
