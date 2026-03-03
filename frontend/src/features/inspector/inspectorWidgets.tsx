import type { ComponentProps, JSX } from 'react'
import { BasicsSection } from './sections/BasicsSection'
import { CompareMetadataSection } from './sections/CompareMetadataSection'
import { MetadataSection } from './sections/MetadataSection'
import { NotesSection } from './sections/NotesSection'
import { OverviewSection } from './sections/OverviewSection'
import { QuickViewSection } from './sections/QuickViewSection'
import type { InspectorWidgetId } from './model/inspectorWidgetOrder'

export interface InspectorWidgetContext {
  multi: boolean
  viewerCompareActive: boolean
  metadataCompareReady: boolean
  quickViewVisible: boolean
  quickViewProps: ComponentProps<typeof QuickViewSection>
  overviewProps: ComponentProps<typeof OverviewSection>
  compareMetadataProps: ComponentProps<typeof CompareMetadataSection>
  basicsProps: ComponentProps<typeof BasicsSection>
  metadataProps: ComponentProps<typeof MetadataSection>
  notesProps: ComponentProps<typeof NotesSection>
}

export interface InspectorWidgetDefinition {
  id: InspectorWidgetId
  isVisible: (ctx: InspectorWidgetContext) => boolean
  render: (ctx: InspectorWidgetContext) => JSX.Element
}

export const INSPECTOR_WIDGETS: readonly InspectorWidgetDefinition[] = [
  {
    id: 'quickView',
    isVisible: ({ quickViewVisible }) => quickViewVisible,
    render: ({ quickViewProps }) => <QuickViewSection {...quickViewProps} />,
  },
  {
    id: 'overview',
    isVisible: () => true,
    render: ({ overviewProps }) => <OverviewSection {...overviewProps} />,
  },
  {
    id: 'compareMetadata',
    isVisible: ({ metadataCompareReady }) => metadataCompareReady,
    render: ({ compareMetadataProps }) => <CompareMetadataSection {...compareMetadataProps} />,
  },
  {
    id: 'metadata',
    isVisible: ({ multi }) => !multi,
    render: ({ metadataProps }) => <MetadataSection {...metadataProps} />,
  },
  {
    id: 'basics',
    isVisible: () => true,
    render: ({ basicsProps }) => <BasicsSection {...basicsProps} />,
  },
  {
    id: 'notes',
    isVisible: () => true,
    render: ({ notesProps }) => <NotesSection {...notesProps} />,
  },
]
