import { describe, expect, it } from 'vitest'
import { buildBootHealthFailure, parseBootHealth, type BootHealthState } from '../bootHealth'
import { commitBootHealth } from '../bootTheme'

describe('boot health source parsing', () => {
  it('parses mode and workspace id from health payload', () => {
    expect(parseBootHealth({ ok: true, mode: 'table', workspace_id: 'abc123' })).toEqual({
      mode: 'browse',
      healthMode: 'table',
      workspaceId: 'abc123',
    })
  })

  it('normalizes missing workspace id to null', () => {
    expect(parseBootHealth({ ok: true, mode: 'dataset' })).toEqual({
      mode: 'browse',
      healthMode: 'dataset',
      workspaceId: null,
    })
  })

  it('normalizes ranking mode from health payload', () => {
    expect(parseBootHealth({ ok: true, mode: 'ranking', workspace_id: 'workspace-a' })).toEqual({
      mode: 'ranking',
      healthMode: 'ranking',
      workspaceId: 'workspace-a',
    })
  })
})

describe('boot apply ordering', () => {
  it('applies browse theme before finishing boot state commit', () => {
    const calls: string[] = []
    const bootHealth: BootHealthState = {
      mode: 'browse',
      healthMode: 'memory',
      workspaceId: 'workspace-a',
      error: null,
    }
    commitBootHealth(
      bootHealth,
      () => calls.push('apply'),
      () => calls.push('commit'),
    )
    expect(calls).toEqual(['apply', 'commit'])
  })

  it('skips theme apply when booting ranking mode', () => {
    const calls: string[] = []
    const bootHealth: BootHealthState = {
      mode: 'ranking',
      healthMode: 'ranking',
      workspaceId: 'workspace-a',
      error: null,
    }
    commitBootHealth(
      bootHealth,
      () => calls.push('apply'),
      () => calls.push('commit'),
    )
    expect(calls).toEqual(['commit'])
  })

  it('builds browse fallback when health fails', () => {
    const failed = buildBootHealthFailure(new Error('network unreachable'))
    expect(failed.mode).toBe('browse')
    expect(failed.healthMode).toBeNull()
    expect(failed.workspaceId).toBeNull()
    expect(failed.error).toContain('network unreachable')
  })
})
