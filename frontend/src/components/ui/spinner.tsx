import { cn } from 'cn'

function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-slot="spinner"
      className={cn(
        'inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent',
        className,
      )}
    />
  )
}

export { Spinner }
