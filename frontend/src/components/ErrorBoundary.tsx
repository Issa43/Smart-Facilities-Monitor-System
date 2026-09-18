import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/Button/Button'
import { StateCard } from '@/components/ui/Feedback/Feedback'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/** Prevents a render failure in one route from leaving the application blank. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled application render error', error, info)
  }

  private retry = () => {
    this.setState({ error: null })
  }

  render() {
    if (this.state.error) {
      return (
        <main id="main-content" style={{ padding: 'var(--space-8)' }}>
          <StateCard
            tone="critical"
            title="تعذّر عرض الصفحة"
            description="حدث خطأ غير متوقع أثناء عرض الصفحة. يمكنك إعادة المحاولة بأمان."
            action={
              <Button variant="subtle" onClick={this.retry}>
                إعادة المحاولة
              </Button>
            }
          />
        </main>
      )
    }

    return this.props.children
  }
}
