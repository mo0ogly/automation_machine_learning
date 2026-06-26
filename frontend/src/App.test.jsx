import { render, screen } from '@testing-library/react'
import App from './App'

describe('App Component', () => {
  it('renders the dashboard without crashing', () => {
    render(<App />)
    expect(screen.getByText(/machine_learning/i)).toBeDefined()
    expect(screen.getByRole('button', { name: /Pipeline/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /Configuration/i })).toBeDefined()
  })
})
