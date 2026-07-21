import React from 'react'

// Keeps one page's runtime error from white-screening the whole app.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Page error:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="err">
          Something went wrong on this page ({String(this.state.error.message || this.state.error)}).
          Pick another section from the sidebar.
        </div>
      )
    }
    return this.props.children
  }
}
