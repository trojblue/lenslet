import React from 'react'
import type { JsonRenderNode, MetadataPathSegment } from '../model/metadataCompare'

const JSON_INDENT = 2

const jsonStringStyle: React.CSSProperties = { color: 'var(--json-string)' }
const jsonNumberStyle: React.CSSProperties = { color: 'var(--json-number)' }
const jsonLiteralStyle: React.CSSProperties = { color: 'var(--json-literal)' }
const jsonFallbackStyle: React.CSSProperties = { color: 'var(--json-fallback)' }
const jsonKeyStyle: React.CSSProperties = { color: 'var(--json-key)' }

function renderJsonNode(
  node: JsonRenderNode,
  indent: number,
  onPathClick?: (path: MetadataPathSegment[]) => void,
): React.ReactNode {
  switch (node.kind) {
    case 'null':
    case 'boolean':
      return <span style={jsonLiteralStyle}>{node.text}</span>
    case 'undefined':
    case 'fallback':
      return <span style={jsonFallbackStyle}>{node.text}</span>
    case 'string':
      return <span style={jsonStringStyle}>{node.text}</span>
    case 'number':
      return <span style={jsonNumberStyle}>{node.text}</span>
    case 'array':
      if (node.items.length === 0) return '[]'
      return (
        <>
          {'[\n'}
          {node.items.map((item, idx) => (
            <React.Fragment key={idx}>
              {' '.repeat(indent + JSON_INDENT)}
              {renderJsonNode(item, indent + JSON_INDENT, onPathClick)}
              {idx < node.items.length - 1 ? ',' : ''}
              {'\n'}
            </React.Fragment>
          ))}
          {' '.repeat(indent)}
          {']'}
        </>
      )
    case 'object':
      if (node.entries.length === 0) return '{}'
      return (
        <>
          {'{\n'}
          {node.entries.map((entry, idx) => (
            <React.Fragment key={JSON.stringify(entry.path)}>
              {' '.repeat(indent + JSON_INDENT)}
              <span
                className="ui-json-key"
                style={jsonKeyStyle}
                onClick={onPathClick ? (event) => {
                  event.stopPropagation()
                  onPathClick(entry.path)
                } : undefined}
              >
                {JSON.stringify(entry.key)}
              </span>
              {': '}
              {renderJsonNode(entry.value, indent + JSON_INDENT, onPathClick)}
              {idx < node.entries.length - 1 ? ',' : ''}
              {'\n'}
            </React.Fragment>
          ))}
          {' '.repeat(indent)}
          {'}'}
        </>
      )
  }
}

interface JsonRenderCodeProps {
  node: JsonRenderNode
  onPathClick?: (path: MetadataPathSegment[]) => void
}

export function JsonRenderCode({ node, onPathClick }: JsonRenderCodeProps): JSX.Element {
  return <code className="block whitespace-pre-wrap">{renderJsonNode(node, 0, onPathClick)}</code>
}
