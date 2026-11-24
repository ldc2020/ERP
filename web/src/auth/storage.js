// Browser session storage keeps each tab's signed-in account across reloads.
const storage = {
  get(key) {
    const value = window.sessionStorage.getItem(key)
    return value === null ? undefined : JSON.parse(value)
  },
  set(key, value) {
    window.sessionStorage.setItem(key, JSON.stringify(value))
  },
  remove(key) {
    window.sessionStorage.removeItem(key)
  },
  sessionId() {
    return this.get('Auth-Session') || this.startSession()
  },
  startSession() {
    // This identity changes on login/logout, never on an access-token refresh.
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, '0')).join('')
    this.set('Auth-Session', id)
    return id
  },
  endSession() {
    this.startSession()
    this.remove('Access-Token')
    this.remove('Refresh-Token')
  }
}

export default storage
