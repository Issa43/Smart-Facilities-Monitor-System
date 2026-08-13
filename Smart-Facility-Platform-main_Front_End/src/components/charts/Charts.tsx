import { useId, type ReactNode } from 'react'
import {
  Area,
  AreaChart as RechartsAreaChart,
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Tone } from '@/types'
import { formatNumber, formatPercent } from '@/lib/format'
import {
  CHART_MARGIN,
  GRID_PROPS,
  STATUS_COLORS,
  X_AXIS_PROPS,
  Y_AXIS_PROPS,
  seriesColor,
} from './chartTheme'
import styles from './Charts.module.css'

/* ==========================================================================
   Tooltip & legend — shared by every chart
   ========================================================================== */

interface TooltipPayloadEntry {
  name?: string | number
  value?: string | number
  color?: string
  payload?: { fill?: string }
}

function ChartTooltip({
  active,
  payload,
  label,
  suffix,
}: {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string | number
  suffix?: string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className={styles.tooltip}>
      {label !== undefined && <div className={styles.tooltipLabel}>{label}</div>}
      {payload.map((entry, index) => (
        <div key={index} className={styles.tooltipRow}>
          <span
            className={styles.tooltipSwatch}
            style={{ background: entry.color ?? entry.payload?.fill }}
          />
          <span>{entry.name}</span>
          <span className={styles.tooltipValue}>
            {formatNumber(Number(entry.value))}
            {suffix}
          </span>
        </div>
      ))}
    </div>
  )
}

export interface LegendEntry {
  label: string
  color: string
  value?: ReactNode
}

/** Always rendered for two or more series — identity is never colour alone. */
export function ChartLegend({ entries }: { entries: LegendEntry[] }) {
  return (
    <ul className={styles.legend}>
      {entries.map((entry) => (
        <li key={entry.label} className={styles.legendItem}>
          <span className={styles.legendSwatch} style={{ background: entry.color }} />
          {entry.label}
          {entry.value !== undefined && <span className={styles.legendValue}>{entry.value}</span>}
        </li>
      ))}
    </ul>
  )
}

/* ==========================================================================
   Area chart — trends over time
   ========================================================================== */

export interface AreaSeries {
  key: string
  label: string
  color?: string
}

/**
 * Generic over the row shape rather than requiring `Record<string, …>`: a plain
 * interface like TrendPoint has no index signature and would otherwise need a
 * cast at every call site.
 */
interface AreaChartProps<T extends object> {
  data: T[]
  /** Category key on the X axis — usually a month label. */
  xKey: keyof T & string
  series: AreaSeries[]
  height?: number
  suffix?: string
}

export function AreaChart<T extends object>({
  data,
  xKey,
  series,
  height = 240,
  suffix,
}: AreaChartProps<T>) {
  const gradientId = useId().replace(/:/g, '')

  return (
    <div className={styles.wrap}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsAreaChart data={data} margin={CHART_MARGIN}>
          <defs>
            {series.map((entry, index) => {
              const color = entry.color ?? seriesColor(index)
              return (
                <linearGradient
                  key={entry.key}
                  id={`${gradientId}-${entry.key}`}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor={color} stopOpacity={0.26} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              )
            })}
          </defs>

          <CartesianGrid {...GRID_PROPS} />
          {/* Recharts 3 types dataKey as TypedDataKey<T, V>, which cannot be
              proven against our generic T. The cast is at the library boundary
              only — our own props stay `keyof T`. */}
          <XAxis dataKey={xKey as never} {...X_AXIS_PROPS} />
          <YAxis {...Y_AXIS_PROPS} />
          <Tooltip
            content={<ChartTooltip suffix={suffix} />}
            cursor={{ stroke: 'var(--border-strong)', strokeDasharray: '4 4' }}
          />

          {series.map((entry, index) => {
            const color = entry.color ?? seriesColor(index)
            return (
              <Area
                key={entry.key}
                type="monotone"
                dataKey={entry.key as never}
                name={entry.label}
                stroke={color}
                strokeWidth={2}
                fill={`url(#${gradientId}-${entry.key})`}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
              />
            )
          })}
        </RechartsAreaChart>
      </ResponsiveContainer>

      {series.length > 1 && (
        <ChartLegend
          entries={series.map((entry, index) => ({
            label: entry.label,
            color: entry.color ?? seriesColor(index),
          }))}
        />
      )}
    </div>
  )
}

/* ==========================================================================
   Column chart — counts per period
   ========================================================================== */

export function ColumnChart<T extends object>({
  data,
  xKey,
  valueKey,
  label,
  color,
  height = 240,
}: {
  data: T[]
  xKey: keyof T & string
  valueKey: keyof T & string
  label: string
  color?: string
  height?: number
}) {
  return (
    <div className={styles.wrap}>
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart data={data} margin={CHART_MARGIN} barCategoryGap="28%">
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey={xKey as never} {...X_AXIS_PROPS} />
          <YAxis {...Y_AXIS_PROPS} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--primary-tint-soft)' }} />
          <Bar
            dataKey={valueKey as never}
            name={label}
            fill={color ?? seriesColor(0)}
            radius={[4, 4, 0, 0]}
            maxBarSize={38}
          />
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ==========================================================================
   Donut — distribution across a handful of categories
   ========================================================================== */

export interface DonutSlice {
  label: string
  value: number
  tone?: Tone
  color?: string
}

interface DonutChartProps {
  slices: DonutSlice[]
  /** Big number in the hole. Defaults to the total. */
  centerValue?: ReactNode
  centerLabel?: string
  size?: number
}

/**
 * Slices must already be in severity order when they carry a `tone` — see the
 * ordering rule in chartTheme.ts. api/stats.ts emits them that way.
 */
export function DonutChart({ slices, centerValue, centerLabel, size = 180 }: DonutChartProps) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)
  const colored = slices.map((slice, index) => ({
    ...slice,
    fill: slice.color ?? (slice.tone ? STATUS_COLORS[slice.tone] : seriesColor(index)),
  }))

  return (
    <div className={styles.wrap}>
      <div className={styles.donutWrap} style={{ height: size }}>
        <ResponsiveContainer width="100%" height={size}>
          <PieChart>
            <Pie
              data={colored}
              dataKey="value"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius={size * 0.31}
              outerRadius={size * 0.47}
              // A 2px surface gap between segments, per the mark spec.
              paddingAngle={2}
              stroke="var(--surface)"
              strokeWidth={2}
              startAngle={90}
              endAngle={-270}
            >
              {colored.map((slice) => (
                <Cell key={slice.label} fill={slice.fill} />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        <div className={styles.donutCenter}>
          <span className={styles.donutValue}>{centerValue ?? formatNumber(total)}</span>
          {centerLabel && <span className={styles.donutLabel}>{centerLabel}</span>}
        </div>
      </div>

      <ChartLegend
        entries={colored.map((slice) => ({
          label: slice.label,
          color: slice.fill,
          value: formatNumber(slice.value),
        }))}
      />
    </div>
  )
}

/* ==========================================================================
   Progress ring — a single headline percentage
   ========================================================================== */

export function ProgressRing({
  percent,
  size = 120,
  thickness = 10,
  color,
  label,
}: {
  percent: number
  size?: number
  thickness?: number
  color?: string
  label?: string
}) {
  const clamped = Math.min(100, Math.max(0, percent))
  const radius = size / 2 - thickness / 2 - 1
  const circumference = 2 * Math.PI * radius
  const stroke =
    color ??
    (clamped >= 80
      ? STATUS_COLORS.success
      : clamped >= 45
        ? STATUS_COLORS.info
        : clamped >= 20
          ? STATUS_COLORS.warning
          : STATUS_COLORS.critical)

  return (
    <div
      className={styles.ringWrap}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label ?? 'النسبة'}: ${clamped}%`}
    >
      <svg className={styles.ringSvg} width={size} height={size}>
        <circle
          className={styles.ringTrack}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={thickness}
        />
        <circle
          className={styles.ringFill}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={thickness}
          stroke={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - (clamped / 100) * circumference}
        />
      </svg>
      <div className={styles.ringCenter}>
        <span className={styles.ringValue} style={{ fontSize: size * 0.22, color: stroke }}>
          {formatPercent(clamped)}
        </span>
        {label && <span className={styles.ringLabel}>{label}</span>}
      </div>
    </div>
  )
}

/* ==========================================================================
   Horizontal comparison bars — ranking a handful of named things
   ========================================================================== */

export interface ComparisonBar {
  label: string
  value: number
  /** Denominator for the bar width. Defaults to the largest value. */
  max?: number
  tone?: Tone
  display?: string
}

export function ComparisonBars({ bars }: { bars: ComparisonBar[] }) {
  const largest = Math.max(...bars.map((bar) => bar.max ?? bar.value), 1)

  return (
    <div className={styles.bars}>
      {bars.map((bar, index) => {
        const color = bar.tone ? STATUS_COLORS[bar.tone] : seriesColor(index)
        const width = ((bar.value / (bar.max ?? largest)) * 100).toFixed(1)
        return (
          <div key={bar.label} className={styles.barRow}>
            <span className={styles.barLabel} title={bar.label}>
              {bar.label}
            </span>
            <span className={styles.barTrack}>
              <span className={styles.barFill} style={{ width: `${width}%`, background: color }} />
            </span>
            <span className={styles.barValue} style={{ color }}>
              {bar.display ?? formatNumber(bar.value)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
