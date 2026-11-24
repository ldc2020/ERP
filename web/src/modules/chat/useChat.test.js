import test from 'node:test'
import assert from 'node:assert/strict'
import { ref, watch } from 'vue'
import { useChat } from './useChat.js'

const alice = { id: 1, username: 'alice', name: 'Alice', avatar: null }
const bob = { id: 2, username: 'bob', name: 'Bob', avatar: null, available: true }
const contact = { id: 7, user: bob, last_message: null }
const message = (id, extra = {}) => ({
  id, sender_id: 2, content: `message ${id}`, created_at: '2026-11-24T08:00:00Z',
  client_id: `server-${id}`, ...extra,
})
const apiFor = (overrides = {}) => ({
  listContacts: async () => [contact],
  searchUsers: async () => [],
  addContact: async () => contact,
  listMessages: async () => ({ items: [], has_more: false }),
  sendMessage: async () => { throw new Error('offline') },
  ...overrides,
})

test('failed sending retries with the same client ID and replaces the pending message', async () => {
  const requests = []
  const chat = useChat({ currentUser: alice, api: apiFor({
    sendMessage: async (id, body) => {
      requests.push({ id, ...body })
      if (requests.length === 1) throw new Error('connection lost')
      return message(11, { sender_id: 1, content: body.content, client_id: body.client_id })
    },
  }) })
  await chat.initialize()
  await chat.sendMessage({ roomId: 7, content: 'Hello Bob' })
  assert.equal(chat.messages.value.length, 1)
  assert.equal(chat.messages.value[0].status, 'failed')
  const clientId = chat.messages.value[0].client_id
  await chat.retryMessage(clientId)
  assert.equal(requests[0].client_id, requests[1].client_id)
  assert.equal(requests[1].content, 'Hello Bob')
  assert.equal(chat.messages.value.length, 1)
  assert.equal(chat.messages.value[0].id, 11)
  assert.equal(chat.failedMessages.value.length, 0)
  chat.stop()
})

test('history stays chronological and incremental polling does not duplicate messages', async () => {
  const queries = []
  const chat = useChat({ currentUser: alice, api: apiFor({
    listMessages: async (id, query) => {
      queries.push(query)
      if (query.before_id) return { items: [message(1), message(2)], has_more: false }
      if (query.after_id) return { items: [message(4), message(5)], has_more: false }
      return { items: [message(3), message(4)], has_more: true }
    },
  }) })
  await chat.initialize()
  await chat.loadOlder()
  await chat.poll()
  assert.deepEqual(chat.messages.value.map(item => item.id), [1, 2, 3, 4, 5])
  assert.equal(queries[1].before_id, 3)
  assert.equal(queries[2].after_id, 4)
  assert.equal(chat.hasOlder.value, false)
  chat.stop()
})

test('poll skips a second request while a previous poll is still running', async () => {
  let finishPoll
  let requests = 0
  const chat = useChat({ currentUser: alice, api: apiFor({
    listContacts: async () => {
      requests += 1
      if (requests === 2) await new Promise(resolve => { finishPoll = resolve })
      return [contact]
    },
  }) })
  await chat.initialize()
  const first = chat.poll()
  await chat.poll()
  assert.equal(requests, 2)
  finishPoll()
  await first
  chat.stop()
})

test('late history from another conversation cannot replace the selected conversation', async () => {
  let finishFirst
  const chat = useChat({ currentUser: alice, api: apiFor({
    listContacts: async () => [],
    listMessages: async id => id === 7
      ? new Promise(resolve => { finishFirst = resolve })
      : { items: [message(21)], has_more: false },
  }) })
  const first = chat.selectConversation(7)
  await chat.selectConversation(8)
  finishFirst({ items: [message(1)], has_more: false })
  await first
  assert.equal(chat.selectedId.value, 8)
  assert.deepEqual(chat.messages.value.map(item => item.id), [21])
  chat.stop()
})

test('a message recovered by polling is not marked failed after a lost send response', async () => {
  let rejectSend
  let sentBody
  const chat = useChat({ currentUser: alice, api: apiFor({
    sendMessage: async (id, body) => {
      sentBody = body
      return new Promise((resolve, reject) => { rejectSend = reject })
    },
    listMessages: async (id, query) => ({
      items: query.after_id !== undefined && sentBody
        ? [message(30, { sender_id: 1, content: sentBody.content, client_id: sentBody.client_id })]
        : [],
      has_more: false,
    }),
  }) })
  await chat.initialize()
  const sending = chat.sendMessage({ roomId: 7, content: 'delivered' })
  await chat.poll()
  rejectSend(new Error('response lost'))
  await sending
  assert.equal(chat.messages.value.length, 1)
  assert.equal(chat.messages.value[0].id, 30)
  assert.equal(chat.failedMessages.value.length, 0)
  chat.stop()
})

test('an own send response cannot advance past an unseen incoming message', async () => {
  const queries = []
  const chat = useChat({ currentUser: alice, api: apiFor({
    listMessages: async (id, query) => {
      queries.push(query)
      if (query.after_id === 10) return { items: [message(11), message(12, { sender_id: 1, client_id: 'mine' })], has_more: false }
      return { items: [message(10)], has_more: false }
    },
    sendMessage: async (id, body) => message(12, { sender_id: 1, content: body.content, client_id: body.client_id }),
  }) })
  await chat.initialize()
  await chat.sendMessage({ roomId: 7, content: 'my reply' })
  await chat.poll()
  assert.equal(queries[1].after_id, 10)
  assert.deepEqual(chat.messages.value.map(item => item.id), [10, 11, 12])
  chat.stop()
})

test('the initial conversation is selected after contact loading ends', async () => {
  let loadingContactsAtSelection
  let renderedLoadingContacts = false
  let chat
  chat = useChat({ currentUser: alice, api: apiFor({
    listMessages: async () => {
      loadingContactsAtSelection = renderedLoadingContacts
      return { items: [], has_more: false }
    },
  }) })
  const unwatch = watch(chat.loadingContacts, value => { renderedLoadingContacts = value }, { flush: 'post' })
  await chat.initialize()
  assert.equal(chat.selectedId.value, 7)
  assert.equal(loadingContactsAtSelection, false)
  unwatch()
  chat.stop()
})

test('pending messages use the loaded current account rather than an empty bootstrap object', async () => {
  const account = ref({})
  const chat = useChat({ currentUser: account, api: apiFor() })
  await chat.initialize()
  account.value = alice
  await chat.sendMessage({ roomId: 7, content: 'Hello after account loading' })
  assert.equal(chat.messages.value[0].sender_id, 1)
  chat.stop()
})
