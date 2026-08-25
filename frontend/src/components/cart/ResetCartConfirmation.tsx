import { useId } from 'react'

interface ResetCartConfirmationProps {
  canReset: boolean
  error: string | null
  isResetting: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ResetCartConfirmation({
  canReset,
  error,
  isResetting,
  onCancel,
  onConfirm,
}: ResetCartConfirmationProps) {
  const titleId = useId()
  const descriptionId = useId()

  return (
    <div
      className="reset-confirmation"
      role="alertdialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      <p id={titleId}>Reset current cart?</p>
      <p id={descriptionId}>This removes every item from the active checkout.</p>
      {error ? (
        <p className="reset-confirmation__error" role="alert">
          {error}
        </p>
      ) : null}
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
          disabled={isResetting || !canReset}
        >
          {isResetting ? 'Resetting...' : 'Reset Cart'}
        </button>
      </div>
    </div>
  )
}
