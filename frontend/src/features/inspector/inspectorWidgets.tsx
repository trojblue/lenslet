import type { ComponentProps, JSX } from 'react'
import { BasicsSection } from './sections/BasicsSection'
import { CompareMetadataSection } from './sections/CompareMetadataSection'
import { MetadataSection } from './sections/MetadataSection'
import { NotesSection } from './sections/NotesSection'
import { OverviewSection } from './sections/OverviewSection'

export type InspectorWidgetId = 'overview' | 'compareMetadata' | 'basics' | 'metadata' | 'notes'

export interface InspectorWidgetContext {
  multi: boolean
  compareActive: boolean
  compareReady: boolean
  overviewProps: ComponentProps<typeof OverviewSection>
  compareMetadataProps: ComponentProps<typeof CompareMetadataSection>
  basicsProps: ComponentProps<typeof BasicsSection>
  metadataProps: ComponentProps<typeof MetadataSection>
  notesProps: ComponentProps<typeof NotesSection>
}

interface InspectorWidgetDefinition {
  id: InspectorWidgetId
  isVisible: (ctx: InspectorWidgetContext) => boolean
  render: (ctx: InspectorWidgetContext) => JSX.Element
}

export const INSPECTOR_WIDGETS: readonly InspectorWidgetDefinition[] = [
  {
    id: 'overview',
    isVisible: () => true,
    render: ({ overviewProps }) => <OverviewSection {...overviewProps} />,
  },
  {
    id: 'compareMetadata',
    isVisible: ({ compareActive, compareReady }) => compareActive && compareReady,
    render: ({ compareMetadataProps }) => <CompareMetadataSection {...compareMetadataProps} />,
  },
  {
    id: 'basics',
    isVisible: () => true,
    render: ({ basicsProps }) => <BasicsSection {...basicsProps} />,
  },
  {
    id: 'metadata',
    isVisible: ({ multi }) => !multi,
    render: ({ metadataProps }) => <MetadataSection {...metadataProps} />,
  },
  {
    id: 'notes',
    isVisible: () => true,
    render: ({ notesProps }) => <NotesSection {...notesProps} />,
  },
]
