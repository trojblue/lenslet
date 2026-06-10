import { describe, expect, it } from 'vitest'
import {
  filterDropdownOptions,
  findNextEnabledOption,
  flattenDropdownOptions,
} from '../dropdownSearch'

describe('dropdownSearch', () => {
  it('matches labels, values, and keywords with all query tokens', () => {
    const result = filterDropdownOptions([
      { value: 'metric:l0p_style_family', label: 'Style family', keywords: ['l0p_style_family'] },
      { value: 'metric:quality_score', label: 'Quality score', keywords: ['quality_score'] },
    ], 'l0p family')

    expect(flattenDropdownOptions(result.options).map((option) => option.value)).toEqual([
      'metric:l0p_style_family',
    ])
    expect(result.matchCount).toBe(1)
    expect(result.totalCount).toBe(2)
  })

  it('keeps only groups with matching options', () => {
    const result = filterDropdownOptions([
      {
        label: 'Layout',
        options: [
          { value: 'layout:grid', label: 'Grid' },
          { value: 'layout:adaptive', label: 'Justified rows' },
        ],
      },
      {
        label: 'Sort by',
        options: [
          { value: 'builtin:added', label: 'Date added' },
          { value: 'metric:quality_score', label: 'Quality score' },
        ],
      },
    ], 'quality')

    expect(result.options).toEqual([
      {
        label: 'Sort by',
        options: [
          { value: 'metric:quality_score', label: 'Quality score' },
        ],
      },
    ])
  })

  it('moves through enabled options only', () => {
    const options = [
      { value: 'a', label: 'A' },
      { value: 'b', label: 'B', disabled: true },
      { value: 'c', label: 'C' },
    ]

    expect(findNextEnabledOption(options, 'a', 1)?.value).toBe('c')
    expect(findNextEnabledOption(options, 'c', 1)?.value).toBe('a')
    expect(findNextEnabledOption(options, 'a', -1)?.value).toBe('c')
  })
})
