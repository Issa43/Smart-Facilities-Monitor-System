// @vitest-environment jsdom

import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorState } from '@/components/ui/Feedback/Feedback'
import { Modal } from '@/components/ui/Modal/Modal'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('shared accessibility and recovery states', () => {
  it('announces query failures and exposes a working retry action', async () => {
    const user = userEvent.setup()
    const retry = vi.fn()
    render(<ErrorState error={new Error('service unavailable')} onRetry={retry} />)

    expect(screen.getByRole('alert')).toHaveTextContent('service unavailable')
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('contains render failures and can retry without leaving a blank page', async () => {
    const user = userEvent.setup()
    let shouldThrow = true
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    function UnstablePage() {
      if (shouldThrow) throw new Error('render failed')
      return <h1>Recovered page</h1>
    }

    render(
      <ErrorBoundary>
        <UnstablePage />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('تعذّر عرض الصفحة')
    shouldThrow = false
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }))
    expect(screen.getByRole('heading', { name: 'Recovered page' })).toBeInTheDocument()
  })

  it('traps modal focus, closes with Escape, and restores focus to the opener', async () => {
    const user = userEvent.setup()

    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open dialog
          </button>
          <Modal
            open={open}
            onClose={() => setOpen(false)}
            title="Accessible dialog"
            subtitle="Dialog instructions"
            footer={<button type="button">Save</button>}
          >
            <input aria-label="Name" />
          </Modal>
        </>
      )
    }

    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open dialog' })
    await user.click(opener)

    const dialog = screen.getByRole('dialog', { name: 'Accessible dialog' })
    expect(dialog).toHaveAccessibleDescription('Dialog instructions')
    const close = screen.getByRole('button', { name: 'إغلاق' })
    const save = screen.getByRole('button', { name: 'Save' })
    expect(close).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(save).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(close).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })
})
