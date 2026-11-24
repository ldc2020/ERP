import request from '@/utils/axios'

const base = '/api/chat'
const data = response => response.data.data

export const chatApi = {
  searchUsers(q) {
    return request({ url: `${base}/users`, params: { q } }).then(data)
  },
  listContacts({ silent = false } = {}) {
    return request({ url: `${base}/contacts`, silent }).then(data)
  },
  addContact(userId) {
    return request({ url: `${base}/contacts`, method: 'post', data: { user_id: userId } }).then(data)
  },
  listMessages(conversationId, params = {}, { silent = false } = {}) {
    return request({ url: `${base}/conversations/${conversationId}/messages`, params, silent }).then(data)
  },
  sendMessage(conversationId, body) {
    return request({ url: `${base}/conversations/${conversationId}/messages`, method: 'post', data: body }).then(data)
  },
}
