// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/features/shared/ReportsPage', () => ({
  ReportsPage: ({ cards }: { cards: Array<{ kind: string }> }) => (
    <ul>
      {cards.map((card) => (
        <li key={card.kind}>{card.kind}</li>
      ))}
    </ul>
  ),
}))

import { ConstructionReportsPage } from './ConstructionReportsPage'

describe('ConstructionReportsPage', () => {
  it('shows only the construction module allowed by the frozen backend role matrix', () => {
    render(<ConstructionReportsPage />)

    expect(screen.getByText('construction')).toBeInTheDocument()
    expect(screen.queryByText('projects')).not.toBeInTheDocument()
    expect(screen.queryByText('materials')).not.toBeInTheDocument()
  })
})
