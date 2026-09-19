// @vitest-environment jsdom

import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SearchableSelect } from './SearchableSelect'

describe('SearchableSelect', () => {
  it('filters by typing, selects a value, and preserves its label', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [value, setValue] = useState('')
      return (
        <SearchableSelect
          value={value}
          onChange={setValue}
          placeholder="Select asset type"
          options={[
            { value: 'Chiller', label: 'Chiller' },
            { value: 'Pump', label: 'Pump' },
          ]}
        />
      )
    }
    render(<Harness />)
    const input = screen.getByRole('combobox')
    await user.type(input, 'pump')
    expect(screen.queryByRole('option', { name: 'Chiller' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('option', { name: 'Pump' }))
    expect(input).toHaveValue('Pump')
  })

  it('shows loading and API-error states even while the disabled menu cannot open', () => {
    const { rerender } = render(
      <SearchableSelect value="" onChange={vi.fn()} placeholder="Select" options={[]} loading />,
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    rerender(
      <SearchableSelect value="" onChange={vi.fn()} placeholder="Select" options={[]} error />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
