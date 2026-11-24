import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

test('loading another account replaces the previous account dynamic routes', async () => {
  let guard
  let registered
  const store = {
    state: { user: { hasGetRoute: false, routeList: [{ name: 'AdminOnly', path: '/admin-only' }] } },
    dispatch: async () => { store.state.user.hasGetRoute = true },
  }
  const source = fs.readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
    .replace(/^import .*\n/gm, '').replace('export default router', '')
  new Function('createRouter', 'createWebHistory', 'BasicLayout', 'Login', 'storage', 'store', 'generator', 'listToTree', source)(
    () => ({ beforeEach: hook => { guard = hook }, addRoute: route => { registered = route.children.map(child => child.name) } }),
    () => ({}), {}, {}, { get: () => 'signed-in' }, store, routes => routes, routes => routes,
  )
  await guard({ name: 'EmployeeChat', fullPath: '/chat' })
  assert.equal(registered.includes('AdminOnly'), true)
  store.state.user.hasGetRoute = false
  store.state.user.routeList = [{ name: 'EmployeeOnly', path: '/employee-only' }]
  await guard({ name: 'EmployeeChat', fullPath: '/chat' })
  assert.equal(registered.includes('AdminOnly'), false)
  assert.equal(registered.includes('EmployeeOnly'), true)
  assert.equal(registered.filter(name => name === 'EmployeeChat').length, 1)
})
