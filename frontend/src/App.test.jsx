import { render, screen } from '@testing-library/react'
import App from './App'

describe('App Component', () => {
  it('renders the dashboard without crashing', () => {
    render(<App />)
    expect(screen.getByText(/ML Automator/i)).toBeDefined()
    expect(screen.getByText(/Dashboard/i)).toBeDefined()
  })
})
