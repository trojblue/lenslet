import { describe, expect, it } from 'vitest'
import { toggleInspectorSectionState } from '../../hooks/useInspectorUiState'
import {
  INSPECTOR_WIDGET_DEFAULT_ORDER,
  parseStoredInspectorWidgetOrder,
  reorderInspectorWidgetOrder,
  sanitizeInspectorWidgetOrder,
} from '../inspectorWidgetOrder'

describe('inspector widget order model', () => {
  it('keeps metadata above basics in the canonical default order', () => {
    expect(INSPECTOR_WIDGET_DEFAULT_ORDER).toEqual([
      'overview',
      'compareMetadata',
      'metadata',
      'basics',
      'notes',
    ])
  })

  it('sanitizes persisted order by removing unknown IDs, deduping, and appending missing IDs', () => {
    const sanitized = sanitizeInspectorWidgetOrder([
      'notes',
      'overview',
      'notes',
      'unknown',
      'metadata',
    ])

    expect(sanitized).toEqual([
      'notes',
      'overview',
      'metadata',
      'compareMetadata',
      'basics',
    ])
  })

  it('marks stale persisted order payloads for rewrite', () => {
    const parsed = parseStoredInspectorWidgetOrder(
      JSON.stringify(['notes', 'notes', 42, 'overview', 'metadata']),
    )

    expect(parsed.order).toEqual([
      'notes',
      'overview',
      'metadata',
      'compareMetadata',
      'basics',
    ])
    expect(parsed.shouldRewrite).toBe(true)
  })

  it('keeps canonical persisted order without rewrite', () => {
    const parsed = parseStoredInspectorWidgetOrder(JSON.stringify(INSPECTOR_WIDGET_DEFAULT_ORDER))

    expect(parsed.order).toEqual([...INSPECTOR_WIDGET_DEFAULT_ORDER])
    expect(parsed.shouldRewrite).toBe(false)
  })

  it('moves the dragged widget to the dropped position', () => {
    const nextOrder = reorderInspectorWidgetOrder(
      INSPECTOR_WIDGET_DEFAULT_ORDER,
      'metadata',
      'notes',
    )

    expect(nextOrder).toEqual([
      'overview',
      'compareMetadata',
      'basics',
      'notes',
      'metadata',
    ])
  })

  it('keeps section open-state toggles independent from reorder operations', () => {
    const closedMetadata = toggleInspectorSectionState(
      {
        overview: true,
        compare: true,
        metadata: true,
        basics: true,
        notes: true,
      },
      'metadata',
    )

    const reordered = reorderInspectorWidgetOrder(
      INSPECTOR_WIDGET_DEFAULT_ORDER,
      'notes',
      'overview',
    )
    const reopenedMetadata = toggleInspectorSectionState(closedMetadata, 'metadata')

    expect(reordered).toEqual([
      'notes',
      'overview',
      'compareMetadata',
      'metadata',
      'basics',
    ])
    expect(closedMetadata.metadata).toBe(false)
    expect(reopenedMetadata.metadata).toBe(true)
  })
})
