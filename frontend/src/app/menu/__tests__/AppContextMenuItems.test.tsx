import { describe, expect, it } from 'vitest'
import { buildRefreshMenuItem, READONLY_REFRESH_LABEL } from '../AppContextMenuItems'

describe('buildRefreshMenuItem', () => {
  it('disables refresh when in read-only mode', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: false,
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe(READONLY_REFRESH_LABEL)
  })

  it('shows refreshing label when active', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: true,
      refreshing: true,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe('Refreshing…')
  })

  it('shows refresh when enabled and idle', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: true,
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(false)
    expect(item.label).toBe('Refresh')
  })
})
