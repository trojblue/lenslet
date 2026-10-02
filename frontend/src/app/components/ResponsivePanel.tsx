import { useId, useRef, type ReactNode } from 'react'
import { useModalFocusTrap } from '../../shared/hooks/useModalFocusTrap'
import type { PanelSide } from '../layout/useResponsivePanels'

type Props = {
  side: PanelSide
  overlay: boolean
  onClose: () => void
  children: ReactNode
}

/** Keep the same panel subtree mounted in both inline and sheet presentations. */
export default function ResponsivePanel({ side, overlay, onClose, children }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const onKeyDown = useModalFocusTrap(ref, { enabled: overlay, onEscape: onClose })
  return (
    <div
      ref={ref}
      className={`responsive-panel${overlay ? ' is-overlay' : ''}`}
      data-panel-side={side}
      role={overlay ? 'dialog' : undefined}
      aria-modal={overlay || undefined}
      aria-labelledby={overlay ? titleId : undefined}
      tabIndex={overlay ? -1 : undefined}
      onKeyDown={onKeyDown}
    >
      {overlay && <div className="responsive-panel-backdrop" onClick={onClose} aria-hidden="true" />}
      <div
        className="responsive-panel-surface"
      >
        {overlay && (
          <div className="responsive-panel-header">
            <h2 id={titleId}>{side === 'left' ? 'Browse tools' : 'Inspector'}</h2>
            <button type="button" className="btn btn-sm" onClick={onClose} aria-label={`Close ${side === 'left' ? 'browse tools' : 'Inspector'}`}>Close</button>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}
