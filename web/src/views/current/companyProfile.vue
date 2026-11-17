<template>
  <a-card title="公司资料" style="margin-top: 16px">
    <a-spin :spinning="loading">
      <a-alert v-if="loadFailed" type="error" message="无法加载公司资料">
        <template #action>
          <a-button size="small" @click="loadProfile">重试</a-button>
        </template>
      </a-alert>
      <a-form v-else-if="canEdit" :model="profile" layout="vertical" @finish="saveProfile">
        <a-form-item label="公司名称" name="name" :rules="[{ required: true, whitespace: true, message: '请输入公司名称' }]">
          <a-input v-model:value="profile.name" :maxlength="200" />
        </a-form-item>
        <a-form-item label="公司地址">
          <a-input v-model:value="profile.address" :maxlength="500" />
        </a-form-item>
        <a-form-item label="公司电话">
          <a-input v-model:value="profile.phone" :maxlength="50" />
        </a-form-item>
        <a-button type="primary" html-type="submit" :loading="saving">保存</a-button>
      </a-form>
      <a-descriptions v-else-if="profile.name" :column="1">
        <a-descriptions-item label="公司名称">{{ profile.name }}</a-descriptions-item>
        <a-descriptions-item label="公司地址">{{ profile.address || '—' }}</a-descriptions-item>
        <a-descriptions-item label="公司电话">{{ profile.phone || '—' }}</a-descriptions-item>
      </a-descriptions>
      <a-empty v-else-if="!loading" description="尚未填写公司资料" />
    </a-spin>
  </a-card>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import request from '@/utils/axios'

const profile = reactive({ name: '', address: '', phone: '' })
const canEdit = ref(false)
const loading = ref(true)
const saving = ref(false)
const loadFailed = ref(false)

function setProfile(data) {
  profile.name = data?.name ?? ''
  profile.address = data?.address ?? ''
  profile.phone = data?.phone ?? ''
}

async function loadProfile() {
  loading.value = true
  loadFailed.value = false
  try {
    const { data } = await request.get('/api/system/company/profile')
    setProfile(data.data.profile)
    canEdit.value = data.data.can_edit
  } catch {
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  if (saving.value) return
  saving.value = true
  try {
    const { data } = await request.post('/api/system/company/profile/update', { ...profile })
    setProfile(data.data)
    message.success(data.message)
  } catch {
    // The request interceptor displays errors.
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>
