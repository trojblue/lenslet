import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AppShell from './app/AppShell'
import './styles.css'

const qc = new QueryClient()

export default function AppRoot(){
  return (
    <QueryClientProvider client={qc}>
      <AppShell/>
    </QueryClientProvider>
  )
}
