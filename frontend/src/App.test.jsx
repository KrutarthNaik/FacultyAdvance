// Runtime validation coverage for the sign-in experience.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import api from './api'
import App from './App'

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    defaults: { baseURL: '/api/' },
  },
}))

describe('sign-in experience', () => {
  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('shows the sign-in form and password recovery link to signed-out users', async () => {
    render(<BrowserRouter><App /></BrowserRouter>)

    expect(await screen.findByRole('heading', { name: 'Sign in to your account' })).toBeVisible()
    expect(screen.getByLabelText('Username')).toBeRequired()
    expect(screen.getByLabelText('Password')).toBeRequired()
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/reset-password')
    expect(screen.getByRole('link', { name: 'Continue with Google Workspace' })).toHaveAttribute(
      'href', '/api/auth/google/start/',
    )
  })

  it('exchanges the one-time Google sign-in ticket for a session', async () => {
    window.history.replaceState({}, '', '/sso/callback?ticket=temporary-ticket')
    api.post.mockResolvedValue({
      data: {
        access: 'access-token',
        refresh: 'refresh-token',
        user: { id: 8, username: 'faculty', role: 'FACULTY', first_name: 'Faculty' },
      },
    })
    api.get.mockRejectedValue(new Error('dashboard unavailable'))
    render(<BrowserRouter><App /></BrowserRouter>)

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('auth/google/complete/', {
      ticket: 'temporary-ticket',
    }))
    await waitFor(() => expect(localStorage.getItem('access_token')).toBe('access-token'))
    expect(localStorage.getItem('refresh_token')).toBe('refresh-token')
  })

  it('displays the authentication error returned by the API', async () => {
    api.post.mockRejectedValue({
      response: { data: { detail: 'Verify your email address before signing in.' } },
    })
    const user = userEvent.setup()
    render(<BrowserRouter><App /></BrowserRouter>)

    await user.type(screen.getByLabelText('Username'), 'faculty.member')
    await user.type(screen.getByLabelText('Password'), 'not-a-real-password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Verify your email address before signing in.',
    )
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('auth/token/', {
      username: 'faculty.member',
      password: 'not-a-real-password',
    }))
  })

  it('creates an empty appraisal policy draft for an administrator', async () => {
    localStorage.setItem('access_token', 'test-access-token')
    api.get.mockImplementation((url) => {
      if (url === 'auth/me/') {
        return Promise.resolve({ data: { id: 1, username: 'admin', role: 'ADMIN' } })
      }
      if (url === 'policies/') return Promise.resolve({ data: { results: [] } })
      if (url === 'periods/') {
        return Promise.resolve({
          data: { results: [{ id: 7, name: 'Test period', is_active: true }] },
        })
      }
      return Promise.reject(new Error(`Unexpected API request: ${url}`))
    })
    api.post.mockResolvedValue({
      data: { id: 11, period: 7, version: 1, rules: {}, status: 'DRAFT' },
    })
    const user = userEvent.setup()
    render(<BrowserRouter><App /></BrowserRouter>)

    await user.click(await screen.findByRole('link', { name: 'Criteria' }))
    await user.click(await screen.findByRole('button', { name: 'New policy draft' }))

    expect(await screen.findByText('Draft created. Add policy rules and save before approval.')).toBeVisible()
    expect(api.post).toHaveBeenCalledWith('policies/', {
      period: 7,
      version: 1,
      rules: {},
    })
  })
})
