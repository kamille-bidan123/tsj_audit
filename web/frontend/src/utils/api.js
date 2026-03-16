// API 请求工具函数
const getBaseUrl = () => '/api'

const getAuthToken = () => {
  const userStr = localStorage.getItem('user')
  if (userStr) {
    const user = JSON.parse(userStr)
    return user.user_id || localStorage.getItem('token')
  }
  return localStorage.getItem('token')
}

const apiRequest = async (endpoint, options = {}) => {
  const url = `${getBaseUrl()}${endpoint}`
  const token = getAuthToken()

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }

  // 添加 Authorization 头
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...options,
    headers
  })

  const result = await response.json()
  return result
}

export default {
  getAuthToken,
  apiRequest
}
