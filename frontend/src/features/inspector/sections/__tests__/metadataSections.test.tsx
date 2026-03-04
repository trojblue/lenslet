import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { buildJsonRenderNode, type CompareMetadataMatrixResult } from '../../model/metadataCompare'
import { CompareMetadataSection } from '../CompareMetadataSection'
import { MetadataSection } from '../MetadataSection'
import { OverviewSection } from '../OverviewSection'
import { QuickViewSection } from '../QuickViewSection'
import { buildGifExportTooltip, SelectionExportSection } from '../SelectionExportSection'

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
        selectedCount={2}
        totalSize={2048}
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
        selectedCount={2}
        totalSize={4096}
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
        selectedCount={1}
        totalSize={4096}
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
        selectedCount={3}
        totalSize={4096}
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

  it('renders quick view rows with copy feedback and collapsed custom path controls', () => {
    const html = renderToStaticMarkup(
      <QuickViewSection
        open
        onToggle={noop}
        rows={[
          {
            id: 'default:prompt',
            label: 'Prompt',
            value: 'character portrait',
            sourcePath: 'quick_view_defaults.prompt',
          },
          {
            id: 'custom:quick_fields.parameters',
            label: 'quick_fields.parameters',
            value: 'steps=24,cfg=7',
            sourcePath: 'quick_fields.parameters',
          },
        ]}
        reservationActive={false}
        reservationRowCount={3}
        metadataLoading={false}
        quickViewCopiedRowId="default:prompt"
        onCopyQuickViewValue={noop}
        quickViewCustomPathsDraft={'quick_fields.parameters\nfound_text_chunks[0].keyword'}
        onQuickViewCustomPathsDraftChange={noop}
        onSaveQuickViewCustomPaths={noop}
        quickViewCustomPathsError={null}
      />,
    )

    expect(html).toContain('Quick View')
    expect(html).toContain('Prompt')
    expect(html).toContain('quick_fields.parameters')
    expect(html).toContain('character portrait')
    expect(html).toContain('Prompt copied')
    expect(html).toContain('aria-label="Copy Prompt"')
    expect(html).toContain('Custom JSON paths')
    expect(html).not.toContain('Save fields')
    expect(html).not.toContain('Supported syntax: dot paths and [index].')
  })

  it('keeps quick view footprint reserved while metadata is loading for a new selection', () => {
    const html = renderToStaticMarkup(
      <QuickViewSection
        open
        onToggle={noop}
        rows={[]}
        reservationActive
        reservationRowCount={2}
        metadataLoading
        quickViewCopiedRowId={null}
        onCopyQuickViewValue={noop}
        quickViewCustomPathsDraft=""
        onQuickViewCustomPathsDraftChange={noop}
        onSaveQuickViewCustomPaths={noop}
        quickViewCustomPathsError={null}
      />,
    )

    expect(html).toContain('Loading metadata…')
    expect((html.match(/aria-hidden=\"true\"/g) ?? []).length).toBeGreaterThanOrEqual(2)
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
        compareCopiedPath={null}
        onCopyCompareValue={noop}
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
        compareCopiedPath={null}
        onCopyCompareValue={noop}
        compareMatrix={null}
        compareSelectionTruncatedCount={0}
      />,
    )

    expect(html).toContain('metadata failed')
  })

  it('moves GIF mode guidance into Export GIF tooltip text', () => {
    const html = renderToStaticMarkup(
      <SelectionExportSection
        selectedCount={2}
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
      />,
    )

    expect(html).toContain('Export GIF slideshow')
    expect(html).toContain(buildGifExportTooltip(false))
    expect(html).not.toContain('>GIF mode:')
  })

  it('keeps GIF tooltip guidance available when export is disabled and high quality is enabled', () => {
    const html = renderToStaticMarkup(
      <SelectionExportSection
        selectedCount={1}
        compareExportLabelsText=""
        onCompareExportLabelsTextChange={noop}
        compareExportEmbedMetadata
        onCompareExportEmbedMetadataChange={noop}
        compareExportReverseOrder={false}
        onCompareExportReverseOrderChange={noop}
        compareExportHighQualityGif
        onCompareExportHighQualityGifChange={noop}
        compareExportBusy={false}
        compareExportMode={null}
        onComparisonExport={noop}
        compareExportError={null}
      />,
    )

    expect(html).toContain('Export GIF slideshow')
    expect(html).toContain('disabled=""')
    expect(html).toContain(buildGifExportTooltip(true))
  })
})
