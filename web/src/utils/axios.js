import axios from 'axios'
import storage from '@/auth/storage'
import router from '@/router'
import store from '@/store'
import { save_token } from './util.js'
import notification from 'ant-design-vue/es/notification'

const request = axios.create({ timeout: 10000 })
const refreshRequest = axios.create({ timeout: 10000 })
let refreshState

function sessionChangedError() {
  const error = new Error('登录账号已更改')
  error.code = 'AUTH_SESSION_CHANGED'
  return error
}

function assertCurrentSession(config) {
  if (config && config.authSessionId !== storage.sessionId()) throw sessionChangedError()
}

function clearSession(sessionId) {
  if (sessionId !== storage.sessionId()) return
  storage.endSession()
  store.dispatch('clearUserInfo')
  router.push('/login')
}

function refreshSession(sessionId) {
  if (!refreshState || refreshState.sessionId !== sessionId) {
    const refreshToken = storage.get('Refresh-Token')
    const state = { sessionId }
    refreshState = state
    state.promise = refreshRequest.post('/api/system/auth/token/refresh', {
      refresh_token: refreshToken
    }).then(response => {
      if (storage.sessionId() !== sessionId || storage.get('Refresh-Token') !== refreshToken) {
        throw sessionChangedError()
      }
      if (response.data.code !== 200) {
        throw new Error(response.data.message || '登录已过期')
      }
      const tokens = response.data.data
      save_token(tokens.access_token, tokens.refresh_token, tokens.expires_in)
      return tokens.access_token
    }).catch(error => {
      if (storage.sessionId() !== sessionId) throw sessionChangedError()
      if (storage.get('Refresh-Token') === refreshToken) clearSession(sessionId)
      throw error
    }).finally(() => {
      if (refreshState === state) refreshState = undefined
    })
  }
  return refreshState.promise
}

async function errorHandler(error) {
  const response = error.response
  const config = error.config || response?.config
  assertCurrentSession(config)
  if (!response) throw error
  const data = response.data
  const isLogin = config?.url === '/api/system/auth/login'
  const unauthorized = response.status === 401 || data?.code === 401

  if (unauthorized && !isLogin) {
    if (!config) throw error
    if (config.authRetried || !storage.get('Refresh-Token')) {
      clearSession(config.authSessionId)
      throw error
    }
    config.authRetried = true
    const sentToken = config.headers?.Authorization
    const currentToken = storage.get('Access-Token')
    // Another completed refresh may already have replaced this request's token.
    if (!currentToken || sentToken === 'Bearer ' + currentToken) {
      await refreshSession(config.authSessionId)
    }
    assertCurrentSession(config)
    return request(config)
  }

  if (!config?.silent) notification.error({ message: '错误', description: data?.message || '请求失败' })
  throw error
}

request.interceptors.request.use(config => {
  if (config.authSessionId === undefined) config.authSessionId = storage.sessionId()
  assertCurrentSession(config)
  const token = storage.get('Access-Token')
  if (token) config.headers.Authorization = 'Bearer ' + token
  else delete config.headers.Authorization
  return config
})

request.interceptors.response.use(response => {
  assertCurrentSession(response.config)
  if (response.data.code !== 200) {
    return errorHandler({ response, config: response.config })
  }
  return response
}, errorHandler)

export default request
