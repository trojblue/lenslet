import React from 'react'
import { createRoot } from 'react-dom/client'
import { logApiBaseForDev } from './api/base'
import { initializeBrowseRequestBudgetTelemetry } from './api/requestBudget'
import App from './App'
logApiBaseForDev()
initializeBrowseRequestBudgetTelemetry()
createRoot(document.getElementById('root')!).render(<App />)
