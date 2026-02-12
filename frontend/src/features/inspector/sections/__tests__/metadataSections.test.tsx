import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { buildJsonRenderNode, type CompareMetadataDiffResult } from '../../model/metadataCompare'
import { CompareMetadataSection } from '../CompareMetadataSection'
import { MetadataSection } from '../MetadataSection'
import { OverviewSection } from '../OverviewSection'

const noop = (..._args: unknown[]) => {}
const noopPath = (_path: Array<string | number>) => {}

function buildCompareDiff(): CompareMetadataDiffResult {
  return {
    entries: [
      {
        key: 'prompt.steps',
        kind: 'different',
        aText: '24',
        bText: '30',
      },
    ],
    onlyA: 0,
    onlyB: 0,
    different: 1,
    truncatedCount: 0,
  }
}

describe('inspector metadata section rendering', () => {
  it('renders enabled selection actions and export controls for an active compare pair', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={2}
        totalSize={2048}
        filename=""
        compareActive
        compareReady
        onOpenCompare={noop}
        compareExportLabelsText={'Prompt A\nPrompt B'}
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Selection Actions')
    expect(html).toContain('Selection Export')
    expect(html).toContain('Side by side view')
    expect(html).toContain('Export comparison')
    expect(html).toContain('Side-by-side viewer is already open.')
    expect((html.match(/disabled=\"\"/g) ?? [])).toHaveLength(2)
  })

  it('keeps selection export visible when compare is closed and shows enablement guidance', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={2}
        totalSize={4096}
        filename=""
        compareActive={false}
        compareReady={false}
        onOpenCompare={noop}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Selection Export')
    expect(html).toContain('Open side-by-side view to enable comparison export.')
    expect((html.match(/disabled=\"\"/g) ?? []).length).toBeGreaterThanOrEqual(3)
  })

  it('shows explicit side-by-side and export disabled reasons for selections above two', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={3}
        totalSize={4096}
        filename=""
        compareActive={false}
        compareReady={false}
        onOpenCompare={noop}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Side-by-side view supports exactly 2 selections (selected 3).')
    expect(html).toContain('Comparison export (v1) supports exactly 2 selections (selected 3).')
    expect((html.match(/disabled=\"\"/g) ?? []).length).toBeGreaterThanOrEqual(4)
  })

  it('renders metadata copy status with typed metadata output', () => {
    const html = renderToStaticMarkup(
      <MetadataSection
        open
        onToggle={noop}
        metadataLoading={false}
        metadataActionLabel="Copy"
        onMetadataAction={noop}
        metadataActionDisabled={false}
        hasPilInfo
        showPilInfo={false}
        onToggleShowPilInfo={noop}
        metaValueCopiedPath="prompt.values[0].score"
        metaHeightClass="h-48"
        metaLoaded
        metaDisplayNode={buildJsonRenderNode({ prompt: { values: [{ score: 0.72 }] } })}
        metaContent=""
        metaError={null}
        onMetaPathCopy={noopPath}
      />,
    )

    expect(html).toContain('Show PIL info')
    expect(html).toContain('Copied value:')
    expect(html).toContain('prompt.values[0].score')
    expect(html).toContain('&quot;prompt&quot;')
    expect(html).toContain('&quot;score&quot;')
    expect(html).toContain('Copy')
  })

  it('keeps compare pane A/B copy states and controls explicit when loaded', () => {
    const html = renderToStaticMarkup(
      <CompareMetadataSection
        open
        onToggle={noop}
        compareMetaState="loaded"
        compareMetaError={null}
        compareLabelA="/images/a.png"
        compareLabelB="/images/b.png"
        compareIncludePilInfo={false}
        onToggleCompareIncludePilInfo={noop}
        onReload={noop}
        compareDiff={buildCompareDiff()}
        compareHasPilInfoA
        compareHasPilInfoB={false}
        compareShowPilInfoA={false}
        compareShowPilInfoB={false}
        onToggleCompareShowPilInfoA={noop}
        onToggleCompareShowPilInfoB={noop}
        compareMetaCopied="B"
        onCopyCompareMetadata={noop}
        compareValueCopiedPathA="prompt.steps"
        compareValueCopiedPathB={null}
        compareDisplayNodeA={buildJsonRenderNode({ prompt: { steps: 24 } })}
        compareDisplayNodeB={buildJsonRenderNode({ prompt: { steps: 30 } })}
        compareMetaContent=""
        onCompareMetaPathCopyA={noopPath}
        onCompareMetaPathCopyB={noopPath}
      />,
    )

    expect(html).toContain('Compare Metadata')
    expect(html).toContain('Metadata A')
    expect(html).toContain('Metadata B')
    expect(html).toContain('Copied value:')
    expect(html).toContain('prompt.steps')
    expect(html).toContain('1 different')
    expect((html.match(/>Copied</g) ?? [])).toHaveLength(1)
    expect((html.match(/>Copy</g) ?? []).length).toBeGreaterThanOrEqual(1)
  })

  it('renders compare metadata errors when compare loading fails', () => {
    const html = renderToStaticMarkup(
      <CompareMetadataSection
        open
        onToggle={noop}
        compareMetaState="error"
        compareMetaError="metadata failed"
        compareLabelA="/images/a.png"
        compareLabelB="/images/b.png"
        compareIncludePilInfo={false}
        onToggleCompareIncludePilInfo={noop}
        onReload={noop}
        compareDiff={null}
        compareHasPilInfoA={false}
        compareHasPilInfoB={false}
        compareShowPilInfoA={false}
        compareShowPilInfoB={false}
        onToggleCompareShowPilInfoA={noop}
        onToggleCompareShowPilInfoB={noop}
        compareMetaCopied={null}
        onCopyCompareMetadata={noop}
        compareValueCopiedPathA={null}
        compareValueCopiedPathB={null}
        compareDisplayNodeA={null}
        compareDisplayNodeB={null}
        compareMetaContent="Metadata not loaded yet."
        onCompareMetaPathCopyA={noopPath}
        onCompareMetaPathCopyB={noopPath}
      />,
    )

    expect(html).toContain('metadata failed')
  })
})
