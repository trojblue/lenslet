type BootShellProps = {
  showLoadingCopy: boolean
}

export default function BootShell({ showLoadingCopy }: BootShellProps) {
  return (
    <div
      className="boot-loading"
      data-boot-shell
      data-loading-copy-visible={showLoadingCopy ? 'true' : 'false'}
      aria-busy="true"
    >
      <span aria-live="polite">{showLoadingCopy ? 'Loading Lenslet...' : '\u00a0'}</span>
    </div>
  )
}
