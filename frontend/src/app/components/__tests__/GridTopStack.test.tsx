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
      actionFeedback={null}
      similarity={null}
      onExitSimilarity={() => {}}
      filterChips={[]}
      onClearFilters={() => {}}
      {...overrides}
    />,
  )
}

describe('GridTopStack rail', () => {
  it('always reserves one keyboard-reachable context rail', () => {
    const html = renderGridTopStack()
    expect(html).toContain('data-filter-count="0"')
    expect(html).toContain('data-grid-top-rail="true"')
    expect(html).toContain('aria-label="Gallery filters and status"')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('Filters')
  })

  it('shows active filters inside the same rail', () => {
    const html = renderGridTopStack({
      filterChips: [
        {
          id: 'star',
          label: 'Stars: 5',
          onRemove: () => {},
        },
      ],
    })
    expect(html).toContain('data-filter-count="1"')
    expect(html).toContain('Stars: 5')
    expect(html).toContain('Clear all')
  })

  it('shows action errors inside the same rail', () => {
    const html = renderGridTopStack({
      actionFeedback: { kind: 'error', message: 'Upload failed' },
    })
    expect(html).toContain('Upload failed')
    expect(html).toContain('role="status"')
  })
})
