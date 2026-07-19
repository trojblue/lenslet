import { afterEach, describe, expect, it, vi } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import AttributesPanel, {
  commitTextDraft,
  projectCompareOperator,
  scheduleCommittedText,
} from '../AttributesPanel'

describe('committed attribute text', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces ten rapid draft changes into one idle commit', () => {
    vi.useFakeTimers()
    const commit = vi.fn()
    let cancel = () => {}

    for (let index = 0; index < 10; index += 1) {
      cancel()
      cancel = scheduleCommittedText(commit, 250)
      vi.advanceTimersByTime(20)
    }

    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(250)
    expect(commit).toHaveBeenCalledTimes(1)
  })

  it('cancels an idle commit when the input unmounts', () => {
    vi.useFakeTimers()
    const commit = vi.fn()
    const cancel = scheduleCommittedText(commit, 250)

    cancel()
    vi.runAllTimers()

    expect(commit).not.toHaveBeenCalled()
  })

  it('retires a normalized draft after one debounced commit', () => {
    vi.useFakeTimers()
    const commit = vi.fn()
    let activeDraft: string | null = ' draft '
    const runCommit = () => {
      activeDraft = commitTextDraft(activeDraft, 'draft', commit)
    }

    scheduleCommittedText(runCommit, 250)
    vi.advanceTimersByTime(250)
    expect(commit).toHaveBeenCalledOnce()
    expect(commit).toHaveBeenCalledWith(' draft ')
    expect(activeDraft).toBeNull()

    scheduleCommittedText(runCommit, 250)
    vi.advanceTimersByTime(250)
    expect(commit).toHaveBeenCalledOnce()
  })
})

describe('attribute operator controls', () => {
  it('projects external filter identity synchronously while preserving same-identity drafts', () => {
    expect(projectCompareOperator('<', '<:10', null)).toBe('<')
    expect(projectCompareOperator('<', '<:10', {
      filterIdentity: '<:10',
      value: '>=',
    })).toBe('>=')
    expect(projectCompareOperator('>', '>:20', {
      filterIdentity: '<:10',
      value: '>=',
    })).toBe('>')
  })

  it('uses app-owned dropdowns for width and height while leaving date inputs native', () => {
    const html = renderToStaticMarkup(React.createElement(AttributesPanel, {
      filters: { and: [] },
      onChangeFilters: () => {},
    }))

    expect(html).toContain('aria-label="Width operator"')
    expect(html).toContain('aria-label="Height operator"')
    expect(html).not.toContain('<select')
    expect(html.match(/type="date"/g)).toHaveLength(2)
  })
})
