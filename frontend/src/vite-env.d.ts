interface ImportMetaEnv {
  readonly DEV: boolean
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
