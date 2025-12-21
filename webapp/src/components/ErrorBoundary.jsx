import React from 'react';
import { captureException } from '../utils/sentry';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });

    // Log error to console
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Send to Sentry
    captureException(error, {
      componentStack: errorInfo?.componentStack,
      url: window.location.href,
    });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    // Navigate to home - using window.location as fallback
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.content}>
            <div style={styles.icon}>!</div>
            <h1 style={styles.title}>Xatolik yuz berdi</h1>
            <p style={styles.message}>
              Ilovada kutilmagan xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.
            </p>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details style={styles.details}>
                <summary style={styles.summary}>Xatolik tafsilotlari</summary>
                <pre style={styles.errorText}>
                  {this.state.error.toString()}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </details>
            )}

            <div style={styles.buttons}>
              <button style={styles.primaryButton} onClick={this.handleRetry}>
                Qaytadan urinish
              </button>
              <button style={styles.secondaryButton} onClick={this.handleGoHome}>
                Bosh sahifa
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: '20px',
    backgroundColor: '#f5f5f5',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  content: {
    textAlign: 'center',
    maxWidth: '400px',
    padding: '40px 24px',
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
  },
  icon: {
    fontSize: '64px',
    marginBottom: '16px',
  },
  title: {
    fontSize: '24px',
    fontWeight: '600',
    color: '#181725',
    margin: '0 0 12px',
  },
  message: {
    fontSize: '16px',
    color: '#7C7C7C',
    margin: '0 0 24px',
    lineHeight: '1.5',
  },
  details: {
    textAlign: 'left',
    marginBottom: '24px',
    padding: '12px',
    backgroundColor: '#FFF5F5',
    borderRadius: '8px',
    border: '1px solid #FFE0E0',
  },
  summary: {
    cursor: 'pointer',
    fontWeight: '500',
    color: '#D32F2F',
    marginBottom: '8px',
  },
  errorText: {
    fontSize: '12px',
    color: '#D32F2F',
    overflow: 'auto',
    maxHeight: '200px',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    margin: '8px 0 0',
  },
  buttons: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  primaryButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    padding: '16px 24px',
    fontSize: '16px',
    fontWeight: '600',
    color: '#ffffff',
    backgroundColor: '#53B175',
    border: 'none',
    borderRadius: '12px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  secondaryButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    padding: '16px 24px',
    fontSize: '16px',
    fontWeight: '500',
    color: '#53B175',
    backgroundColor: 'transparent',
    border: '1px solid #53B175',
    borderRadius: '12px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
};

export default ErrorBoundary;
