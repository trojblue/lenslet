export const INSPECTOR_WIDGET_IDS = [
  'quickView',
  'overview',
  'compareMetadata',
  'metadata',
  'basics',
  'notes',
] as const

export type InspectorWidgetId = (typeof INSPECTOR_WIDGET_IDS)[number]

export const INSPECTOR_WIDGET_DEFAULT_ORDER: readonly InspectorWidgetId[] = INSPECTOR_WIDGET_IDS

const INSPECTOR_WIDGET_ID_SET: ReadonlySet<string> = new Set(INSPECTOR_WIDGET_IDS)

export type InspectorWidgetOrderParseResult = {
  order: InspectorWidgetId[]
  shouldRewrite: boolean
}

export function isInspectorWidgetId(value: string): value is InspectorWidgetId {
  return INSPECTOR_WIDGET_ID_SET.has(value)
}

export function sanitizeInspectorWidgetOrder(rawOrder: readonly string[] | null | undefined): InspectorWidgetId[] {
  const seen = new Set<InspectorWidgetId>()
  const sanitized: InspectorWidgetId[] = []

  if (rawOrder) {
    for (const candidate of rawOrder) {
      if (!isInspectorWidgetId(candidate) || seen.has(candidate)) continue
      seen.add(candidate)
      sanitized.push(candidate)
    }
  }

  for (const widgetId of INSPECTOR_WIDGET_DEFAULT_ORDER) {
    if (!seen.has(widgetId)) sanitized.push(widgetId)
  }

  return sanitized
}

export function parseStoredInspectorWidgetOrder(raw: string | null): InspectorWidgetOrderParseResult {
  if (raw === null) {
    return {
      order: [...INSPECTOR_WIDGET_DEFAULT_ORDER],
      shouldRewrite: false,
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {
      order: [...INSPECTOR_WIDGET_DEFAULT_ORDER],
      shouldRewrite: true,
    }
  }

  if (!Array.isArray(parsed)) {
    return {
      order: [...INSPECTOR_WIDGET_DEFAULT_ORDER],
      shouldRewrite: true,
    }
  }

  const parsedStrings = parsed.filter((entry): entry is string => typeof entry === 'string')
  const hasQuickView = parsedStrings.includes('quickView')
  const sanitizedOrder = sanitizeInspectorWidgetOrder(parsedStrings)
  const migratedOrder: InspectorWidgetId[] = [
    'quickView',
    ...sanitizedOrder.filter((widgetId) => widgetId !== 'quickView'),
  ]
  const order = hasQuickView
    ? sanitizedOrder
    : migratedOrder
  const parsedOrderMatches =
    hasQuickView &&
    parsed.length === order.length &&
    parsed.every((entry, idx) => typeof entry === 'string' && entry === order[idx])

  return {
    order,
    shouldRewrite: !parsedOrderMatches,
  }
}

export function reorderInspectorWidgetOrder(
  order: readonly InspectorWidgetId[],
  activeId: InspectorWidgetId,
  overId: InspectorWidgetId,
): InspectorWidgetId[] {
  const stableOrder = sanitizeInspectorWidgetOrder(order)
  if (activeId === overId) return stableOrder

  const activeIdx = stableOrder.indexOf(activeId)
  const overIdx = stableOrder.indexOf(overId)
  if (activeIdx < 0 || overIdx < 0) return stableOrder

  const next = [...stableOrder]
  const [moved] = next.splice(activeIdx, 1)
  next.splice(overIdx, 0, moved)
  return next
}
