export interface DropdownSearchOption {
  value: string
  label: string
  keywords?: readonly string[]
  disabled?: boolean
}

export interface DropdownSearchGroup<T extends DropdownSearchOption> {
  label?: string
  options: T[]
}

export type DropdownSearchOptions<T extends DropdownSearchOption> = T[] | DropdownSearchGroup<T>[]

export interface FilteredDropdownOptions<T extends DropdownSearchOption> {
  options: DropdownSearchOptions<T>
  totalCount: number
  matchCount: number
}

export function isDropdownGrouped<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
): options is DropdownSearchGroup<T>[] {
  return options.length > 0 && 'options' in options[0]
}

export function flattenDropdownOptions<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
): T[] {
  if (!isDropdownGrouped(options)) return [...options]
  return options.flatMap((group) => group.options)
}

export function filterDropdownOptions<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
  query: string,
): FilteredDropdownOptions<T> {
  const normalizedTokens = normalizeDropdownQuery(query)
  const totalCount = flattenDropdownOptions(options).length
  if (!normalizedTokens.length) {
    return { options, totalCount, matchCount: totalCount }
  }

  if (!isDropdownGrouped(options)) {
    const matches = options.filter((option) => dropdownOptionMatches(option, normalizedTokens))
    return { options: matches, totalCount, matchCount: matches.length }
  }

  let matchCount = 0
  const groups = options.flatMap((group) => {
    const matches = group.options.filter((option) => dropdownOptionMatches(option, normalizedTokens))
    if (!matches.length) return []
    matchCount += matches.length
    return [{ ...group, options: matches }]
  })
  return { options: groups, totalCount, matchCount }
}

export function findFirstEnabledOption<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
): T | null {
  return flattenDropdownOptions(options).find((option) => !option.disabled) ?? null
}

export function findEnabledOption<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
  value: string | null,
): T | null {
  if (value == null) return null
  return flattenDropdownOptions(options).find((option) => option.value === value && !option.disabled) ?? null
}

export function findNextEnabledOption<T extends DropdownSearchOption>(
  options: DropdownSearchOptions<T>,
  currentValue: string | null,
  direction: 1 | -1,
): T | null {
  const enabled = flattenDropdownOptions(options).filter((option) => !option.disabled)
  if (!enabled.length) return null
  const currentIndex = currentValue == null
    ? -1
    : enabled.findIndex((option) => option.value === currentValue)
  const fallbackIndex = direction > 0 ? 0 : enabled.length - 1
  if (currentIndex < 0) return enabled[fallbackIndex] ?? null
  const nextIndex = (currentIndex + direction + enabled.length) % enabled.length
  return enabled[nextIndex] ?? null
}

function normalizeDropdownQuery(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
}

function dropdownOptionMatches(option: DropdownSearchOption, tokens: readonly string[]): boolean {
  const haystack = [
    option.label,
    option.value,
    ...(option.keywords ?? []),
  ].join(' ').toLowerCase()
  return tokens.every((token) => haystack.includes(token))
}
