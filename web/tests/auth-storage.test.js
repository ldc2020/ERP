import assert from 'node:assert/strict'
import test from 'node:test'
import storage from '../src/auth/storage.js'

function tabStorage() {
  const values = new Map()
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key)
  }
}

test('accounts remain isolated between tabs and survive module reuse', () => {
  const first = tabStorage()
  const second = tabStorage()
  globalThis.window = { sessionStorage: first }
  storage.set('Access-Token', 'admin-access')
  storage.set('Refresh-Token', 'admin-refresh')
  window.sessionStorage = second
  assert.equal(storage.get('Access-Token'), undefined)
  storage.set('Access-Token', 'employee-access')
  storage.remove('Refresh-Token')
  window.sessionStorage = first
  assert.equal(storage.get('Access-Token'), 'admin-access')
  assert.equal(storage.get('Refresh-Token'), 'admin-refresh')
  window.sessionStorage = second
  assert.equal(storage.get('Access-Token'), 'employee-access')
})
