import { describe, expect, it } from 'vitest'
import { buildRefreshMenuItem, REFRESH_UNAVAILABLE_LABEL } from '../AppContextMenuItems'

describe('buildRefreshMenuItem', () => {
  it('disables refresh when unavailable', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: false,
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe(REFRESH_UNAVAILABLE_LABEL)
  })

  it('prefers backend-provided refresh disabled reason', () => {
    const item = buildRefreshMenuItem({
      refreshEnabled: false,
      refreshDisabledReason: 'table mode is static',
      refreshing: false,
      onRefresh: () => {},
    })

    expect(item.disabled).toBe(true)
    expect(item.label).toBe('table mode is static')
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
