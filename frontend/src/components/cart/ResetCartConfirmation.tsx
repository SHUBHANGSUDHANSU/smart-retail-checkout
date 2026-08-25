import { useId } from 'react'

interface ResetCartConfirmationProps {
  isResetting: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ResetCartConfirmation({
  isResetting,
  onCancel,
  onConfirm,
}: ResetCartConfirmationProps) {
  const titleId = useId()

  return (
    <div
      className="reset-confirmation"
      role="alertdialog"
      aria-labelledby={titleId}
    >
      <p id={titleId}>Reset current cart?</p>
      <p>This removes every item from the active checkout.</p>
      <div className="reset-confirmation__actions">
        <button
          className="button button--secondary"
          type="button"
          aria-label="Cancel reset"
          onClick={onCancel}
          disabled={isResetting}
          autoFocus
        >
          Cancel
        </button>
        <button
          className="button button--danger"
          type="button"
          aria-label={isResetting ? 'Resetting cart' : 'Confirm reset cart'}
          onClick={onConfirm}
          disabled={isResetting}
        >
          {isResetting ? 'Resetting...' : 'Reset Cart'}
        </button>
      </div>
    </div>
  )
}
