import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { buildJsonRenderNode, type CompareMetadataMatrixResult } from '../../model/metadataCompare'
import { CompareMetadataSection } from '../CompareMetadataSection'
import { MetadataSection } from '../MetadataSection'
import { OverviewSection } from '../OverviewSection'

const noop = (..._args: unknown[]) => {}
const noopPath = (_path: Array<string | number>) => {}

function buildCompareMatrix(): CompareMetadataMatrixResult {
  return {
    columns: [
      {
        path: '/images/a.png',
        label: 'a.png',
      },
      {
        path: '/images/b.png',
        label: 'b.png',
      },
      {
        path: '/images/c.png',
        label: 'c.png',
      },
    ],
    rows: [
      {
        key: 'prompt.steps',
        values: ['24', '30', '24'],
        missingCount: 0,
      },
      {
        key: 'model',
        values: ['—', 'flux-dev', 'flux-dev'],
        missingCount: 1,
      },
    ],
    summary: {
      differingRows: 2,
      missingValues: 1,
      totalRows: 2,
    },
    truncatedRowCount: 0,
  }
}

describe('inspector metadata section rendering', () => {
  it('keeps compare mode focused on side-by-side actions only', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={2}
        totalSize={2048}
        filename=""
        viewerCompareActive
        metadataCompareActive={false}
        metadataCompareAvailable
        onOpenCompare={noop}
        onToggleMetadataCompare={noop}
        compareExportLabelsText={'Prompt A\nPrompt B'}
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportReverseOrder={false}
        onCompareExportReverseOrderChange={noop}
        compareExportHighQualityGif={false}
        onCompareExportHighQualityGifChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Selection Actions')
    expect(html).not.toContain('Selection Export')
    expect(html).toContain('Side by side view')
    expect(html).toContain('Compare metadata')
    expect(html).not.toContain('Export comparison')
    expect(html).toContain('Side-by-side viewer is already open.')
    expect((html.match(/disabled=\"\"/g) ?? [])).toHaveLength(1)
  })

  it('keeps selection export enabled when compare is closed and pair paths are ready', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={2}
        totalSize={4096}
        filename=""
        viewerCompareActive={false}
        metadataCompareActive={false}
        metadataCompareAvailable
        onOpenCompare={noop}
        onToggleMetadataCompare={noop}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportReverseOrder={false}
        onCompareExportReverseOrderChange={noop}
        compareExportHighQualityGif={false}
        onCompareExportHighQualityGifChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Selection Export')
    expect(html).not.toContain('Open side-by-side view to enable comparison export.')
    expect((html.match(/disabled=\"\"/g) ?? [])).toHaveLength(0)
  })

  it('shows minimum-selection guidance when fewer than two items are selected', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={1}
        totalSize={4096}
        filename=""
        viewerCompareActive={false}
        metadataCompareActive={false}
        metadataCompareAvailable={false}
        onOpenCompare={noop}
        onToggleMetadataCompare={noop}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportReverseOrder={false}
        onCompareExportReverseOrderChange={noop}
        compareExportHighQualityGif={false}
        onCompareExportHighQualityGifChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Comparison export requires at least 2 selected images.')
    expect(html).toContain('Select at least 2 images to compare metadata in the inspector.')
    expect((html.match(/disabled=\"\"/g) ?? []).length).toBeGreaterThanOrEqual(4)
  })

  it('keeps side-by-side guidance while leaving export enabled for selections above two', () => {
    const html = renderToStaticMarkup(
      <OverviewSection
        open
        onToggle={noop}
        multi
        selectedCount={3}
        totalSize={4096}
        filename=""
        viewerCompareActive={false}
        metadataCompareActive={false}
        metadataCompareAvailable
        onOpenCompare={noop}
        onToggleMetadataCompare={noop}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportReverseOrder={false}
        onCompareExportReverseOrderChange={noop}
        compareExportHighQualityGif={false}
        onCompareExportHighQualityGifChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
        canFindSimilar={false}
        findSimilarDisabledReason={null}
      />,
    )

    expect(html).toContain('Side-by-side view supports exactly 2 selections (selected 3).')
    expect(html).toContain('Open metadata compare in the inspector.')
    expect(html).not.toContain('Comparison export for more than 2 selections is unavailable on this server.')
    expect(html).toContain('Label for image 1')
    expect((html.match(/disabled=\"\"/g) ?? [])).toHaveLength(1)
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

  it('renders table-oriented compare metadata with summary and over-cap messaging', () => {
    const html = renderToStaticMarkup(
      <CompareMetadataSection
        open
        onToggle={noop}
        compareMetaState="loaded"
        compareMetaError={null}
        compareColumns={[
          { path: '/images/a.png', label: 'a.png' },
          { path: '/images/b.png', label: 'b.png' },
          { path: '/images/c.png', label: 'c.png' },
        ]}
        compareIncludePilInfo={false}
        onToggleCompareIncludePilInfo={noop}
        onReload={noop}
        compareMatrix={buildCompareMatrix()}
        compareSelectionTruncatedCount={1}
      />,
    )

    expect(html).toContain('Compare Metadata')
    expect(html).toContain('Comparing 3 images.')
    expect(html).toContain('+1 not shown.')
    expect(html).toContain('Path')
    expect(html).toContain('prompt.steps')
    expect(html).toContain('2 differing rows')
    expect(html).toContain('1 missing values')
    expect(html).toContain('flux-dev')
  })

  it('renders compare metadata errors when compare loading fails', () => {
    const html = renderToStaticMarkup(
      <CompareMetadataSection
        open
        onToggle={noop}
        compareMetaState="error"
        compareMetaError="metadata failed"
        compareColumns={[
          { path: '/images/a.png', label: 'a.png' },
          { path: '/images/b.png', label: 'b.png' },
        ]}
        compareIncludePilInfo={false}
        onToggleCompareIncludePilInfo={noop}
        onReload={noop}
        compareMatrix={null}
        compareSelectionTruncatedCount={0}
      />,
    )

    expect(html).toContain('metadata failed')
  })
})
