import axios from 'axios'

const configuredApiUrl = import.meta.env.VITE_API_URL || (
  import.meta.env.DEV ? 'http://127.0.0.1:8000/api/' : '/api/'
)
const api = axios.create({
  baseURL: configuredApiUrl.endsWith('/') ? configuredApiUrl : `${configuredApiUrl}/`,
})
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
api.interceptors.response.use((response) => response, async (error) => {
  const original = error.config
  if (error.response?.status === 401 && !original?._retry && localStorage.getItem('refresh_token')) {
    original._retry = true
    try {
      const refreshed = await axios.post(`${api.defaults.baseURL}auth/token/refresh/`, { refresh: localStorage.getItem('refresh_token') })
      localStorage.setItem('access_token', refreshed.data.access)
      original.headers.Authorization = `Bearer ${refreshed.data.access}`
      return api(original)
    } catch {
      localStorage.clear()
      window.location.href = '/login'
    }
  }
  return Promise.reject(error)
})
export default api
