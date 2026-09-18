// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AreaChart, ChartLegend, ComparisonBars, DonutChart } from './Charts'

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => <>{children}</>,
  }
})

describe('shared enterprise charts', () => {
  it('provides Arabic accessible names for trend and distribution charts', () => {
    render(
      <>
        <AreaChart
          data={[{ label: 'يناير', value: 81 }]}
          xKey="label"
          series={[{ key: 'value', label: 'التقدم المسجل' }]}
          suffix="%"
        />
        <DonutChart slices={[{ label: 'نشط', value: 2 }]} centerLabel="مشروع" />
      </>,
    )

    expect(screen.getByRole('img', { name: 'مخطط اتجاه التقدم المسجل' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'مخطط توزيع مشروع' })).toBeInTheDocument()
  })

  it('keeps long RTL legend and comparison labels available without truncating their content', () => {
    const longLabel = 'اسم منشأة عربي طويل لاختبار التفاف النص في العرض الضيق'
    render(
      <>
        <ChartLegend entries={[{ label: longLabel, color: '#2563eb', value: 12 }]} />
        <ComparisonBars bars={[{ label: longLabel, value: 81, max: 100, display: '81%' }]} />
      </>,
    )

    expect(screen.getAllByText(longLabel)).toHaveLength(2)
    expect(screen.getByLabelText('مفتاح المخطط')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'مخطط مقارنة' })).toBeInTheDocument()
  })
})
