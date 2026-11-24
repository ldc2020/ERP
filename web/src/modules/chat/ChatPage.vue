<template>
  <section class="chat-page">
    <header class="chat-toolbar">
      <div>
        <h1>员工聊天</h1>
        <p>搜索同事，添加后即可开始一对一聊天。</p>
      </div>
      <div class="chat-actions">
        <span class="current-account">当前账号：<strong>{{ currentUser.username }}</strong><span v-if="currentUser.name"> · {{ currentUser.name }}</span></span>
        <a :href="secondLoginUrl" target="_blank" rel="noopener noreferrer">打开第二个登录页</a>
        <a-button type="primary" @click="searchOpen = true">添加联系人</a-button>
      </div>
    </header>

    <a-alert v-if="actionError" type="error" :message="actionError" show-icon closable @close="actionError = ''" />
    <a-alert v-if="syncError" type="warning" message="消息同步暂时中断，正在自动重试" :description="syncError" show-icon>
      <template #action><a-button size="small" @click="poll">立即重试</a-button></template>
    </a-alert>

    <div class="chat-panel">
      <div class="conversation-tools">
        <span>{{ contacts.length }} 位联系人</span>
        <a-button v-if="hasOlder" type="link" size="small" :loading="loadingOlder" @click="loadOlder">加载更早消息</a-button>
        <a-button v-if="!contacts.length" type="link" size="small" :loading="loadingContacts" @click="initialize">刷新联系人</a-button>
        <span v-if="selectedContact && !selectedContact.user.available" class="unavailable">该员工已停用，无法发送新消息</span>
      </div>
      <vue-advanced-chat
        v-if="currentUser.id != null && currentUser.username"
        :current-user-id="String(currentUser.id)"
        :room-id="selectedId === null ? undefined : String(selectedId)"
        :rooms="JSON.stringify(rooms)"
        :messages="JSON.stringify(chatMessages)"
        :loading-rooms="loadingContacts"
        :rooms-loaded="!loadingContacts"
        :messages-loaded="!hasOlder && !loadingMessages && !loadingOlder"
        :load-first-room="false"
        :show-add-room="true"
        :show-footer="false"
        :show-files="false"
        :show-audio="false"
        :show-emojis="false"
        :show-reaction-emojis="false"
        :show-new-messages-divider="false"
        :user-tags-enabled="false"
        :emojis-suggestion-enabled="false"
        :media-preview-enabled="false"
        :room-actions="'[]'"
        :menu-actions="'[]'"
        :message-actions="'[]'"
        :message-selection-actions="'[]'"
        :text-formatting="JSON.stringify({ disabled: true })"
        :link-options="JSON.stringify({ disabled: true })"
        :text-messages="JSON.stringify(labels)"
        height="max(380px, calc(100vh - 350px))"
        @fetch-messages="onFetchMessages"
        @add-room="searchOpen = true"
        @open-failed-message="onFailedMessage"
      />
      <div v-if="selectedId !== null" class="composer">
        <div v-for="item in failedMessages" :key="item.client_id" class="failed-message" role="status">
          <span>发送失败：{{ item.content }}</span>
          <a-button type="link" size="small" @click="retryMessage(item.client_id)">重试发送</a-button>
        </div>
        <a-textarea
          v-model:value="draft"
          aria-label="聊天消息"
          placeholder="输入文字消息，Enter 发送，Shift + Enter 换行"
          :maxlength="4000"
          :auto-size="{ minRows: 2, maxRows: 5 }"
          :disabled="!canSend"
          show-count
          @keydown="onComposerKeydown"
        />
        <div class="composer-actions">
          <span>{{ sendingCount ? `正在发送 ${sendingCount} 条消息…` : '文字消息 · 最多 4000 字符' }}</span>
          <a-button type="primary" :disabled="!canSend || !draft.trim()" @click="submitMessage">发送</a-button>
        </div>
      </div>
    </div>

    <a-modal v-model:open="searchOpen" title="添加员工联系人" :footer="null" @after-close="resetSearch">
      <p class="search-help">按账号或姓名搜索。添加后，双方都会出现这段会话。</p>
      <a-input-search
        v-model:value="searchQuery"
        aria-label="搜索员工账号或姓名"
        placeholder="输入员工账号或姓名"
        enter-button="搜索"
        :loading="searching"
        :maxlength="80"
        allow-clear
        @search="searchEmployees"
      />
      <a-alert v-if="searchError" class="search-error" type="error" :message="searchError" show-icon />
      <a-spin :spinning="searching">
        <a-list v-if="searchResults.length" :data-source="searchResults" class="search-results">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.name || item.username" :description="item.username">
                <template #avatar><a-avatar :src="item.avatar">{{ (item.name || item.username).slice(0, 1) }}</a-avatar></template>
              </a-list-item-meta>
              <template #actions>
                <a-button :type="item.is_contact ? 'default' : 'primary'" :loading="addingId === item.id" :disabled="addingId !== null" @click="openContact(item)">
                  {{ item.is_contact ? '打开会话' : '添加并聊天' }}
                </a-button>
              </template>
            </a-list-item>
          </template>
        </a-list>
        <a-empty v-else-if="searchCompleted && !searching" class="search-empty" description="没有找到符合条件的员工" />
      </a-spin>
    </a-modal>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { register } from 'vue-advanced-chat'
import store from '@/store'
import { chatApi } from './api.js'
import { useChat } from './useChat.js'

register()

const router = useRouter()
const currentUser = computed(() => store.state.user.basicInfo)
const secondLoginUrl = router.resolve('/login').href
const {
  contacts, selectedId, selectedContact, messages, hasOlder, failedMessages,
  loadingContacts, loadingMessages, loadingOlder, syncError, actionError,
  initialize, selectConversation, loadOlder, addContact, sendMessage, retryMessage, poll, start, stop,
} = useChat({ api: chatApi, currentUser })

const displayName = user => user.name || user.username
const roomUser = user => ({ _id: String(user.id), username: displayName(user), avatar: user.avatar || '' })
const timeOf = timestamp => new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const rooms = computed(() => contacts.value.map(contact => ({
  roomId: String(contact.id),
  roomName: `${displayName(contact.user)}${contact.user.available ? '' : '（已停用）'}`,
  avatar: contact.user.avatar || '',
  users: [roomUser(currentUser.value), roomUser(contact.user)],
  index: contact.last_message ? new Date(contact.last_message.created_at).getTime() : 0,
  lastMessage: contact.last_message ? {
    _id: String(contact.last_message.id), content: contact.last_message.content,
    senderId: String(contact.last_message.sender_id), timestamp: timeOf(contact.last_message.created_at),
  } : null,
})))
const chatMessages = computed(() => messages.value.map(item => ({
  _id: String(item.id), senderId: String(item.sender_id), content: item.content,
  date: new Date(item.created_at).toLocaleDateString('zh-CN'), timestamp: timeOf(item.created_at),
  saved: !item.status, failure: item.status === 'failed', disableActions: true, disableReactions: true,
})))
const labels = {
  ROOMS_EMPTY: '还没有联系人，点击「添加联系人」开始',
  ROOM_EMPTY: '选择一位联系人开始聊天',
  NEW_MESSAGES: '新消息',
  MESSAGE_DELETED: '消息已删除',
  MESSAGES_EMPTY: '还没有消息，发送第一条问候吧',
  CONVERSATION_STARTED: '会话已开始',
  SEARCH: '搜索联系人',
  NO_ROOM_SELECTED: '选择一位联系人开始聊天',
}

const drafts = ref({})
const draft = computed({
  get: () => drafts.value[selectedId.value] || '',
  set: value => { drafts.value[selectedId.value] = value },
})
const canSend = computed(() => currentUser.value.id != null && Boolean(currentUser.value.username)
  && Boolean(selectedContact.value?.user.available) && !loadingMessages.value)
const sendingCount = computed(() => messages.value.filter(item => item.status === 'sending').length)
function submitMessage() {
  if (!canSend.value || !draft.value.trim()) return
  const content = draft.value
  if (content.length > 4000) return
  sendMessage({ roomId: selectedId.value, content })
  draft.value = ''
}
function onComposerKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    submitMessage()
  }
}
function onFetchMessages(event) {
  const { room, options } = event.detail[0]
  if (Number(room.roomId) !== selectedId.value || options?.reset) selectConversation(room.roomId)
  else loadOlder()
}
function onFailedMessage(event) {
  const item = messages.value.find(item => String(item.id) === String(event.detail[0].message._id))
  if (item) retryMessage(item.client_id)
}

const searchOpen = ref(false)
const searchQuery = ref('')
const searchResults = ref([])
const searchCompleted = ref(false)
const searching = ref(false)
const searchError = ref('')
const addingId = ref(null)
let searchVersion = 0
watch(searchQuery, () => {
  searchVersion += 1
  searchResults.value = []
  searchCompleted.value = false
  searching.value = false
  searchError.value = ''
}, { flush: 'sync' })
async function searchEmployees() {
  const query = searchQuery.value.trim()
  if (!query) return
  const version = ++searchVersion
  searching.value = true
  searchError.value = ''
  try {
    const result = await chatApi.searchUsers(query)
    if (version === searchVersion) {
      searchResults.value = result
      searchCompleted.value = true
    }
  } catch (error) {
    if (version === searchVersion) searchError.value = '员工搜索失败，请重试'
  } finally {
    if (version === searchVersion) searching.value = false
  }
}
async function openContact(user) {
  addingId.value = user.id
  try {
    await addContact(user.id)
    searchOpen.value = false
  } catch {
    searchError.value = '添加联系人失败，请重试'
  } finally {
    addingId.value = null
  }
}
function resetSearch() {
  searchVersion += 1
  searchQuery.value = ''
  searchResults.value = []
  searchCompleted.value = false
  searchError.value = ''
}

let unmounted = false
onMounted(async () => {
  await initialize()
  if (!unmounted) start()
})
onBeforeUnmount(() => {
  unmounted = true
  searchVersion += 1
  stop()
})
</script>

<style scoped>
.chat-page { padding: 24px 0; }
.chat-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
h1 { margin: 0 0 6px; font-size: 24px; font-weight: 600; }
.chat-toolbar p, .search-help { color: #667085; margin: 0; }
.chat-actions { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; justify-content: flex-end; }
.current-account { color: #475467; }
.chat-page > .ant-alert { margin-bottom: 12px; }
.chat-panel { background: #fff; border: 1px solid #e8ebef; border-radius: 8px; overflow: hidden; }
.conversation-tools { min-height: 42px; padding: 4px 16px; display: flex; align-items: center; gap: 18px; color: #667085; border-bottom: 1px solid #f0f0f0; }
.unavailable { color: #b54708; }
vue-advanced-chat { display: block; }
.composer { padding: 14px 18px 12px; border-top: 1px solid #e8ebef; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 14px; }
.composer-actions > span { font-size: 12px; color: #667085; }
.failed-message { display: flex; align-items: center; justify-content: space-between; gap: 16px; color: #b42318; margin-bottom: 10px; }
.failed-message > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-help { margin-bottom: 16px; }
.search-error, .search-results, .search-empty { margin-top: 16px; }
@media (max-width: 1100px) {
  .chat-toolbar { align-items: flex-start; flex-direction: column; }
  .chat-actions { justify-content: flex-start; }
}
</style>
