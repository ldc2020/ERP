import { computed, nextTick, ref, toValue } from 'vue'

const errorMessage = error => error?.response?.data?.message || error?.data?.message || error?.message || '请求失败，请重试'
const isSaved = item => Number.isInteger(item.id)
const sameMessage = (left, right) => left.id === right.id || (
  left.client_id && left.client_id === right.client_id && left.sender_id === right.sender_id
)

// The page owns lifecycle; the controller owns requests, pagination and retry state.
export function useChat({ api, currentUser, pollInterval = 2000 }) {
  const contacts = ref([])
  const selectedId = ref(null)
  const messagesByRoom = ref({})
  const historyLoaded = ref({})
  const olderByRoom = ref({})
  const loadingContacts = ref(false)
  const loadingMessages = ref(false)
  const loadingOlder = ref(false)
  const syncError = ref('')
  const actionError = ref('')
  const messages = computed(() => messagesByRoom.value[selectedId.value] || [])
  const selectedContact = computed(() => contacts.value.find(item => item.id === selectedId.value))
  const hasOlder = computed(() => olderByRoom.value[selectedId.value] || false)
  const failedMessages = computed(() => messages.value.filter(item => item.status === 'failed'))
  let timer
  let stopped = false
  let polling = false
  let messageRequests = 0
  let selectionVersion = 0
  const synchronizedThrough = {}

  function mergeMessages(roomId, incoming) {
    const merged = [...(messagesByRoom.value[roomId] || [])]
    for (const item of incoming) {
      const index = merged.findIndex(existing => sameMessage(existing, item))
      if (index === -1) merged.push(item)
      else merged[index] = item
    }
    merged.sort((left, right) => {
      if (isSaved(left) && isSaved(right)) return left.id - right.id
      if (isSaved(left) !== isSaved(right)) return isSaved(left) ? -1 : 1
      return left.created_at.localeCompare(right.created_at)
    })
    messagesByRoom.value = { ...messagesByRoom.value, [roomId]: merged }
  }

  async function refreshContacts(silent = false) {
    const result = await api.listContacts({ silent })
    if (!stopped) contacts.value = result
  }

  async function initialize() {
    loadingContacts.value = true
    actionError.value = ''
    try {
      await refreshContacts()
      // The chat component ignores room changes while its contact list loads.
      loadingContacts.value = false
      await nextTick()
      if (stopped) return
      if (contacts.value.length && selectedId.value === null) await selectConversation(contacts.value[0].id)
    } catch (error) {
      actionError.value = errorMessage(error)
    } finally {
      loadingContacts.value = false
    }
  }

  async function selectConversation(roomId) {
    roomId = Number(roomId)
    if (selectedId.value === roomId && (historyLoaded.value[roomId] || loadingMessages.value)) return
    selectedId.value = roomId
    const version = ++selectionVersion
    actionError.value = ''
    if (historyLoaded.value[roomId]) {
      loadingMessages.value = false
      return
    }
    loadingMessages.value = true
    messageRequests += 1
    try {
      const result = await api.listMessages(roomId, { limit: 50 })
      if (stopped) return
      mergeMessages(roomId, result.items)
      synchronizedThrough[roomId] = result.items.at(-1)?.id || 0
      historyLoaded.value[roomId] = true
      olderByRoom.value[roomId] = result.has_more
    } catch (error) {
      if (version === selectionVersion) actionError.value = errorMessage(error)
    } finally {
      messageRequests -= 1
      if (version === selectionVersion) loadingMessages.value = false
    }
  }

  async function loadOlder() {
    const roomId = selectedId.value
    if (!roomId || loadingMessages.value || loadingOlder.value || !hasOlder.value) return
    const first = messages.value.find(isSaved)
    if (!first) return
    loadingOlder.value = true
    messageRequests += 1
    try {
      const result = await api.listMessages(roomId, { before_id: first.id, limit: 50 })
      if (stopped) return
      mergeMessages(roomId, result.items)
      olderByRoom.value[roomId] = result.has_more
    } catch (error) {
      actionError.value = errorMessage(error)
    } finally {
      messageRequests -= 1
      loadingOlder.value = false
    }
  }

  async function poll() {
    if (stopped || polling) return
    polling = true
    try {
      await refreshContacts(true)
      const roomId = selectedId.value
      if (roomId && historyLoaded.value[roomId] && messageRequests === 0) {
        // Send responses can jump past unseen incoming messages. Only fetched
        // history advances this cursor so every server message is synchronized.
        let afterId = synchronizedThrough[roomId] || 0
        let more = true
        messageRequests += 1
        try {
          // Catch up in bounded pages without skipping bursts larger than one page.
          while (more && !stopped && selectedId.value === roomId) {
            const result = await api.listMessages(roomId, { after_id: afterId, limit: 100 }, { silent: true })
            if (stopped) break
            mergeMessages(roomId, result.items)
            const nextId = result.items.at(-1)?.id
            more = result.has_more && nextId > afterId
            if (nextId) {
              afterId = nextId
              synchronizedThrough[roomId] = nextId
            }
          }
        } finally {
          messageRequests -= 1
        }
      }
      syncError.value = ''
    } catch (error) {
      if (!stopped) syncError.value = errorMessage(error)
    } finally {
      polling = false
    }
  }

  function start() {
    stopped = false
    clearTimeout(timer)
    const tick = async () => {
      await poll()
      if (!stopped) timer = setTimeout(tick, pollInterval)
    }
    timer = setTimeout(tick, pollInterval)
  }

  function stop() {
    stopped = true
    clearTimeout(timer)
  }

  async function addContact(userId) {
    actionError.value = ''
    try {
      const contact = await api.addContact(userId)
      contacts.value = [contact, ...contacts.value.filter(item => item.id !== contact.id)]
      await selectConversation(contact.id)
      return contact
    } catch (error) {
      actionError.value = errorMessage(error)
      throw error
    }
  }

  async function deliver(roomId, pending) {
    mergeMessages(roomId, [{ ...pending, status: 'sending' }])
    try {
      const saved = await api.sendMessage(roomId, { content: pending.content, client_id: pending.client_id })
      if (!stopped) {
        mergeMessages(roomId, [saved])
        const contact = contacts.value.find(item => item.id === roomId)
        if (contact) contact.last_message = saved
      }
    } catch (error) {
      const existing = (messagesByRoom.value[roomId] || []).find(item => sameMessage(item, pending))
      // A poll may already have recovered a successful send whose response was lost.
      if (!stopped && existing && !isSaved(existing)) mergeMessages(roomId, [{ ...pending, status: 'failed' }])
    }
  }

  async function sendMessage({ roomId, content }) {
    content = content.trim()
    actionError.value = ''
    if (!content || content.length > 4000) {
      actionError.value = '请输入 1–4000 字符的文字消息'
      return
    }
    roomId = Number(roomId)
    const contact = contacts.value.find(item => item.id === roomId)
    if (!contact || !contact.user.available) {
      actionError.value = '该员工已停用，暂时无法发送消息'
      return
    }
    const clientId = crypto.randomUUID()
    await deliver(roomId, {
      id: `pending:${clientId}`, sender_id: toValue(currentUser).id, content,
      created_at: new Date().toISOString(), client_id: clientId,
    })
  }

  async function retryMessage(clientId) {
    const pending = messages.value.find(item => item.client_id === clientId && item.status === 'failed')
    if (pending) await deliver(selectedId.value, pending)
  }

  return {
    contacts, selectedId, selectedContact, messages, hasOlder, failedMessages,
    loadingContacts, loadingMessages, loadingOlder, syncError, actionError,
    initialize, selectConversation, loadOlder, addContact, sendMessage, retryMessage, poll, start, stop,
  }
}
