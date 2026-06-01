import type { CSSProperties } from 'react'

export type CssVariableName = `--${string}`
export type CssVariableValue = string | number
export type CssVariableStyle = CSSProperties & Partial<Record<CssVariableName, CssVariableValue>>

export function cssVars(vars: Record<CssVariableName, CssVariableValue>): CssVariableStyle {
  return vars as CssVariableStyle
}
