/** Small pressed-state filter control shared by list pages. */
export function FilterChip({
  label,
  pressed,
  onClick,
}: {
  label: string
  pressed: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={`chip ${pressed ? 'chip-active' : ''}`}
      aria-pressed={pressed}
      onClick={onClick}
    >
      {label}
    </button>
  )
}
