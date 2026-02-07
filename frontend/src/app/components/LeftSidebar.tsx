import type { MouseEvent } from 'react'
import FolderTree from '../../features/folders/FolderTree'
import MetricsPanel from '../../features/metrics/MetricsPanel'
import type { FilterAST, FolderIndex, Item, SavedView } from '../../lib/types'

type LeftSidebarProps = {
  leftTool: 'folders' | 'metrics'
  onToolChange: (tool: 'folders' | 'metrics') => void
  compareEnabled: boolean
  compareActive: boolean
  onOpenCompare: () => void
  views: SavedView[]
  activeViewId: string | null
  onActivateView: (view: SavedView) => void
  onSaveView: () => void
  current: string
  data?: FolderIndex
  onOpenFolder: (path: string) => void
  onPullRefreshFolders: () => Promise<void>
  onContextMenu: (event: MouseEvent, path: string) => void
  countVersion: number
  items: Item[]
  filteredItems: Item[]
  metricKeys: string[]
  selectedItems?: Item[]
  selectedMetric?: string
  onSelectMetric: (key: string) => void
  filters: FilterAST
  onChangeRange: (key: string, range: { min: number; max: number } | null) => void
  onChangeFilters: (filters: FilterAST) => void
  onResize: (event: MouseEvent) => void
}

const ROOTS = [{ label: 'Root', path: '/' }]

export default function LeftSidebar({
  leftTool,
  onToolChange,
  compareEnabled,
  compareActive,
  onOpenCompare,
  views,
  activeViewId,
  onActivateView,
  onSaveView,
  current,
  data,
  onOpenFolder,
  onPullRefreshFolders,
  onContextMenu,
  countVersion,
  items,
  filteredItems,
  metricKeys,
  selectedItems,
  selectedMetric,
  onSelectMetric,
  filters,
  onChangeRange,
  onChangeFilters,
  onResize,
}: LeftSidebarProps): JSX.Element {
  const folderButtonClass = leftTool === 'folders'
    ? 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-accent-muted text-accent'
    : 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-surface text-text hover:bg-surface-hover'
  const metricsButtonClass = leftTool === 'metrics'
    ? 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-accent-muted text-accent'
    : 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-surface text-text hover:bg-surface-hover'
  const compareButtonClass = compareActive
    ? 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-accent-muted text-accent'
    : 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-surface text-text hover:bg-surface-hover'
  const githubButtonClass = 'w-7 h-7 rounded-md border border-border flex items-center justify-center transition-colors bg-surface text-text hover:bg-surface-hover cursor-pointer'

  return (
    <div className="app-left-panel col-start-1 row-start-2 relative border-r border-border bg-panel overflow-hidden">
      <div className="absolute inset-y-0 left-0 w-10 border-r border-border flex flex-col items-center gap-2 py-3 bg-surface-overlay">
        <button
          className={folderButtonClass}
          title="Folders"
          aria-label="Folders"
          aria-pressed={leftTool === 'folders'}
          onClick={() => onToolChange('folders')}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 7.5h6l2-2h10a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" />
          </svg>
        </button>
        <button
          className={metricsButtonClass}
          title="Metrics / Filters"
          aria-label="Metrics and Filters"
          aria-pressed={leftTool === 'metrics'}
          onClick={() => onToolChange('metrics')}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 19V9" />
            <path d="M10 19V5" />
            <path d="M16 19v-7" />
            <path d="M3 19h18" />
          </svg>
        </button>
        <div className="w-6 h-px bg-border/70 my-1" />
        <button
          className={`${compareButtonClass} ${compareEnabled ? '' : 'opacity-40 cursor-not-allowed'}`}
          title={compareEnabled ? 'Compare selected images' : 'Compare (select 2+)'}
          aria-label="Compare selected images"
          aria-pressed={compareActive}
          aria-disabled={!compareEnabled}
          disabled={!compareEnabled}
          onClick={() => { if (compareEnabled) onOpenCompare() }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="8" height="16" rx="1" />
            <rect x="13" y="4" width="8" height="16" rx="1" />
          </svg>
        </button>
        <div className="flex-1" />
        <a
          className={githubButtonClass}
          href="https://github.com/trojblue/lenslet"
          title="Lenslet on GitHub"
          aria-label="Lenslet on GitHub"
          target="_blank"
          rel="noreferrer"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 .5C5.73.5.5 5.74.5 12.02c0 5.1 3.29 9.42 7.86 10.95.58.11.79-.25.79-.56v-2.17c-3.2.7-3.88-1.55-3.88-1.55-.53-1.35-1.29-1.71-1.29-1.71-1.05-.72.08-.71.08-.71 1.16.08 1.78 1.2 1.78 1.2 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.23-1.29-5.23-5.74 0-1.27.45-2.31 1.19-3.13-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.19.92-.26 1.91-.39 2.89-.39.98 0 1.97.13 2.89.39 2.2-1.5 3.18-1.19 3.18-1.19.63 1.59.23 2.76.11 3.05.74.82 1.19 1.86 1.19 3.13 0 4.46-2.69 5.45-5.25 5.73.41.36.78 1.07.78 2.16v3.2c0 .31.21.67.8.56 4.56-1.53 7.85-5.85 7.85-10.95C23.5 5.74 18.27.5 12 .5z" />
          </svg>
        </a>
      </div>
      <div className="ml-10 h-full">
        {leftTool === 'folders' ? (
          <div className="h-full flex flex-col">
            <div className="px-2 py-2 border-b border-border">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] uppercase tracking-wide text-muted">Smart Folders</div>
                <button
                  className="btn btn-sm btn-ghost text-xs"
                  onClick={onSaveView}
                  title="Save current view as Smart Folder"
                >
                  + New
                </button>
              </div>
              {views.length ? (
                <div className="flex flex-col gap-1">
                  {views.map((view) => {
                    const active = view.id === activeViewId
                    return (
                      <button
                        key={view.id}
                        className={`text-left px-2 py-1.5 rounded-md text-sm ${active ? 'bg-accent-muted text-accent' : 'hover:bg-hover text-text'}`}
                        onClick={() => onActivateView(view)}
                      >
                        {view.name}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="text-xs text-muted px-1 py-1.5">No saved Smart Folders yet.</div>
              )}
            </div>
            <FolderTree
              current={current}
              roots={ROOTS}
              data={data}
              onOpen={onOpenFolder}
              onPullRefresh={onPullRefreshFolders}
              onContextMenu={onContextMenu}
              countVersion={countVersion}
              className="flex-1 min-h-0 overflow-auto scrollbar-thin"
              showResizeHandle={false}
            />
          </div>
        ) : (
          <MetricsPanel
            items={items}
            filteredItems={filteredItems}
            metricKeys={metricKeys}
            selectedItems={selectedItems}
            selectedMetric={selectedMetric}
            onSelectMetric={onSelectMetric}
            filters={filters}
            onChangeRange={onChangeRange}
            onChangeFilters={onChangeFilters}
          />
        )}
      </div>
      <div className="toolbar-offset absolute bottom-0 right-0 w-1.5 cursor-col-resize z-10 hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )
}
