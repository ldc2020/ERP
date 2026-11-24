import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import axios, { AxiosError } from 'axios'
import storage from '../src/auth/storage.js'

const requestSource = fs.readFileSync(new URL('../src/utils/axios.js', import.meta.url), 'utf8')
  .replace(/^import .*\n/gm, '').replace('export default request', 'return request')
const tokenSource = fs.readFileSync(new URL('../src/utils/util.js', import.meta.url), 'utf8')
  .replace(/^import .*\n/gm, '').replaceAll('export function ', 'function ')
const saveToken = new Function('storage', `${tokenSource}\nreturn save_token`)(storage)
const flush = () => new Promise(resolve => setImmediate(resolve))

function fixture(adapter) {
  const values = new Map()
  globalThis.window = { sessionStorage: {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  } }
  const routes = []
  const notifications = []
  const clears = []
  // Run the production interceptors with real Axios; only the network adapter and UI are replaced.
  const request = new Function('axios', 'storage', 'router', 'store', 'save_token', 'notification', requestSource)(
    { create: options => axios.create({ ...options, adapter }) }, storage,
    { push: path => routes.push(path) }, { dispatch: action => clears.push(action) },
    saveToken, { error: value => notifications.push(value) },
  )
  const signIn = (account, token = account) => saveToken(token, `refresh-${account}`, 3600, { newSession: true })
  return { request, signIn, routes, clears, notifications }
}

function response(config, data, status = 200) {
  return { config, data, status, statusText: status === 200 ? 'OK' : 'Unauthorized', headers: {} }
}

function unauthorized(config) {
  return new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, null,
    response(config, { code: 401, message: 'expired' }, 401))
}

test('a late unauthorized write is never replayed as a different signed-in account', async () => {
  const requests = []
  let rejectFirst
  const f = fixture(config => {
    requests.push(config)
    if (requests.length === 1) return new Promise((resolve, reject) => { rejectFirst = () => reject(unauthorized(config)) })
    return Promise.resolve(response(config, { code: 200, data: {} }))
  })
  f.signIn('alice')
  const pending = f.request({ url: '/api/chat/send', method: 'post', data: { content: 'Alice private text' } })
  await flush()
  f.signIn('bob')
  rejectFirst()
  await assert.rejects(pending, { code: 'AUTH_SESSION_CHANGED' })
  assert.equal(requests.length, 1)
  assert.equal(storage.get('Access-Token'), 'bob')
  assert.deepEqual(f.routes, [])
})

test('a late failed retry cannot clear a newer account session', async () => {
  let rejectFirst
  const f = fixture(config => new Promise((resolve, reject) => { rejectFirst = () => reject(unauthorized(config)) }))
  f.signIn('alice')
  const pending = f.request({ url: '/api/chat/contacts', authRetried: true })
  await flush()
  f.signIn('bob')
  rejectFirst()
  await assert.rejects(pending, { code: 'AUTH_SESSION_CHANGED' })
  assert.equal(storage.get('Access-Token'), 'bob')
  assert.equal(storage.get('Refresh-Token'), 'refresh-bob')
  assert.deepEqual(f.clears, [])
  assert.deepEqual(f.routes, [])
})

test('a late successful response cannot publish private data into a newer session', async () => {
  let resolveFirst
  const f = fixture(config => new Promise(resolve => {
    resolveFirst = () => resolve(response(config, { code: 200, data: { content: 'Alice private text' } }))
  }))
  f.signIn('alice')
  const pending = f.request({ url: '/api/chat/messages' })
  await flush()
  f.signIn('bob')
  resolveFirst()
  await assert.rejects(pending, { code: 'AUTH_SESSION_CHANGED' })
})

test('ending an expired session invalidates other pending successful responses', async () => {
  let finishPrivate
  const f = fixture(config => {
    if (config.url === '/api/private') return new Promise(resolve => {
      finishPrivate = () => resolve(response(config, { code: 200, data: 'old private data' }))
    })
    return Promise.reject(unauthorized(config))
  })
  f.signIn('alice')
  const pending = f.request({ url: '/api/private' })
  await flush()
  await assert.rejects(f.request({ url: '/api/expired', authRetried: true }))
  finishPrivate()
  await assert.rejects(pending, { code: 'AUTH_SESSION_CHANGED' })
  assert.equal(storage.get('Access-Token'), undefined)
  assert.equal(storage.get('Refresh-Token'), undefined)
  assert.deepEqual(f.routes, ['/login'])
})

test('silent polling errors leave the global notification area unchanged', async () => {
  const f = fixture(config => Promise.resolve(response(config, { code: 503, message: 'temporarily unavailable' })))
  f.signIn('alice')
  await assert.rejects(f.request({ url: '/api/chat/contacts', silent: true }))
  assert.deepEqual(f.notifications, [])
})

test('new logins rotate session identity while token refresh preserves it', () => {
  const f = fixture(() => { throw new Error('network not expected') })
  f.signIn('alice')
  const original = storage.get('Auth-Session')
  assert.ok(original)
  saveToken('alice-new', 'refresh-alice-new', 3600)
  assert.equal(storage.get('Auth-Session'), original)
  f.signIn('bob')
  assert.notEqual(storage.get('Auth-Session'), original)
})

test('concurrent expired requests share one refresh and retry with the new token', async () => {
  let resolveRefresh
  let refreshes = 0
  const f = fixture(config => {
    if (config.url.endsWith('/token/refresh')) {
      refreshes += 1
      return new Promise(resolve => { resolveRefresh = () => resolve(response(config, {
        code: 200, data: { access_token: 'alice-new', refresh_token: 'refresh-alice-new', expires_in: 3600 },
      })) })
    }
    if (config.headers.Authorization === 'Bearer alice') return Promise.reject(unauthorized(config))
    return Promise.resolve(response(config, { code: 200, data: config.headers.Authorization }))
  })
  f.signIn('alice')
  const pending = Promise.all([f.request({ url: '/api/one' }), f.request({ url: '/api/two' })])
  await flush()
  assert.equal(refreshes, 1)
  resolveRefresh()
  const results = await pending
  assert.deepEqual(results.map(item => item.data.data), ['Bearer alice-new', 'Bearer alice-new'])
  assert.equal(storage.get('Refresh-Token'), 'refresh-alice-new')
})

test('a new account can refresh independently while an obsolete refresh is pending', async () => {
  const refreshes = new Map()
  const f = fixture(config => {
    if (config.url.endsWith('/token/refresh')) {
      const token = JSON.parse(config.data).refresh_token
      return new Promise(resolve => refreshes.set(token, () => resolve(response(config, {
        code: 200, data: { access_token: `${token}-new`, refresh_token: `${token}-rotated`, expires_in: 3600 },
      }))))
    }
    if (!config.headers.Authorization.endsWith('-new')) return Promise.reject(unauthorized(config))
    return Promise.resolve(response(config, { code: 200, data: {} }))
  })
  f.signIn('alice')
  const oldRequest = f.request({ url: '/api/one' })
  const oldResult = assert.rejects(oldRequest, { code: 'AUTH_SESSION_CHANGED' })
  await flush()
  f.signIn('bob')
  const currentRequest = f.request({ url: '/api/two' })
  await flush()
  assert.equal(refreshes.has('refresh-bob'), true)
  refreshes.get('refresh-alice')()
  await oldResult
  refreshes.get('refresh-bob')()
  await currentRequest
  assert.equal(storage.get('Access-Token'), 'refresh-bob-new')
  assert.deepEqual(f.routes, [])
})
