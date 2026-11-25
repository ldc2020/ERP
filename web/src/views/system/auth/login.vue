<template>
  <a-layout>
    <div class="container">
      <a-layout-content :style="contentStyle">
        <div class="header">
          <div class="logo">
            <a-image src="/logo.png" :preview="false" />
          </div>
          <div class="title">FastAPI Vue Admin</div>
        </div>
        <div class="desc">FastAPI Vue Admin 是完全开源的权限管理系统</div>

        <div class="login-main" style="width: 330px; margin: 0 auto;">
          <a-tabs centered>
            <a-tab-pane :key="1" tab="账户密码登录">
              <a-form
                :model="loginForm"
                name="normal_login"
                class="login-form"
                @finish="onFinish"
              >
                <a-form-item name="username" :rules="[{ required: true, message: '用户名是必填项！' }]">
                  <a-input v-model:value="loginForm.username" placeholder="用户名" autocomplete="username">
                    <template #prefix>
                      <UserOutlined class="site-form-item-icon" />
                    </template>
                  </a-input>
                </a-form-item>

                <a-form-item name="password" :rules="[{ required: true, message: '密码是必填项！' }]">
                  <a-input-password v-model:value="loginForm.password" placeholder="密码" autocomplete="current-password">
                    <template #prefix>
                      <LockOutlined class="site-form-item-icon" />
                    </template>
                  </a-input-password>
                </a-form-item>

                <a-form-item v-if="captchaState.enable" name="captcha" :rules="[{ required: captchaState.enable, message: '验证码是必填项！' }]">
                  <a-input v-model:value="loginForm.captcha" placeholder="验证码">
                    <template #addonAfter>
                      <div class="login-form-captcha" @click="loadLoginConfig">
                        <a-image :src="captchaState.img_base" :preview="false" />
                      </div>
                    </template>
                  </a-input>
                </a-form-item>

                <a-form-item>
                  <a-form-item name="remember" no-style>
                    <a-checkbox v-model:checked="loginForm.remember">自动登录</a-checkbox>
                  </a-form-item>
                  <a class="login-form-forgot">忘记密码 ?</a>
                </a-form-item>

                <a-alert v-if="configError" type="error" :message="configError" show-icon>
                  <template #action><a-button type="link" @click="loadLoginConfig">重试</a-button></template>
                </a-alert>
                <a-form-item>
                  <a-button
                    type="primary"
                    html-type="submit"
                    class="login-form-button"
                    :loading="loginFlag"
                    :disabled="!configReady"
                  >
                    登录
                  </a-button>
                </a-form-item>
              </a-form>
            </a-tab-pane>
          </a-tabs>
        </div>
      </a-layout-content>

      <a-layout-footer :style="footerStyle">
        <div class="footer-list">
          <a-button type="link" href="https://gitee.com/senqi666/fastapi-vue-admin">Fastapi Vue Admin</a-button>
          <a-button type="link" href="https://github.com/SenQi-666/fastapi-vue-admin">
            <span>
              <GithubOutlined />
            </span>
          </a-button>
          <a-button type="link" href="https://gitee.com/senqi666/fastapi-vue-admin">Fastapi Vue Admin</a-button>
        </div>
        <div class="footer-copyright">
          <icon-font type="icon-copyright" :style="{ fontSize: '16px' }" />
          Powered by senqi
        </div>
      </a-layout-footer>
    </div>
  </a-layout>
</template>

<script lang="ts" setup>
import type { CSSProperties } from "vue";
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { UserOutlined, LockOutlined, GithubOutlined } from '@ant-design/icons-vue';
import { login, getCaptcha, getLoginConfig } from "@/api/auth"
import type { loginFormType, captchaStateType } from './types';
import { save_token } from "@/utils/util"

const router = useRouter()
const loginFlag = ref(false);
const configReady = ref(false);
const configError = ref("");

const contentStyle: CSSProperties = {
  minHeight: 850,
  height: "850px",
  background: "none",
  padding: "35px 0",
};
const footerStyle: CSSProperties = {
  textAlign: "center",
  background: "none",
};


const loginForm = reactive<loginFormType>({
  username: "",
  password: "",
  captcha: "",
  captcha_key: "",
  remember: true
});


const captchaState = reactive<captchaStateType>({
  enable: false,
  key: "",
  img_base: ""
});

const onFinish = (values: loginFormType) => {
  if (!configReady.value) return;
  loginFlag.value = true;

  login({ ...values, captcha_key: captchaState.key }).then(response => {
    let result = response.data;
    if (result.code === 200) {
      save_token(result.data.access_token, result.data.refresh_token, result.data.expires_in, { newSession: true })
      loginFlag.value = false;
      router.push('/');
    } else {
      loginFlag.value = false;
    }
  }).catch(error => {
    if ((error.response?.data ?? error.data)?.code === 410) {
      loadLoginConfig();
    }
    loginFlag.value = false;
  })
};

const requestCaptcha = async () => {
  if (!captchaState.enable) return;
  const response = await getCaptcha();
  captchaState.key = response.data.data.key;
  captchaState.img_base = response.data.data.img_base;
};

const loadLoginConfig = async () => {
  configReady.value = false;
  configError.value = "";
  try {
    const response = await getLoginConfig();
    captchaState.enable = response.data.data.captcha_enabled;
    captchaState.key = "";
    captchaState.img_base = "";
    loginForm.captcha = "";
    if (captchaState.enable) await requestCaptcha();
    configReady.value = true;
  } catch {
    configError.value = "登录配置加载失败，请重试";
  }
};

onMounted(loadLoginConfig);
</script>

<style lang="scss" scoped>
.ant-btn-link {
  color: rgba(0, 0, 0, 0.65);
  margin-inline-end: 8px;
}
.ant-btn {
  padding: 0;
}
.container {
  background-image: url("/background.png");
  background-size: 100% 100%;
  .desc {
    text-align: center;
    font-size: 15px;
    margin-block-start: 12px;
    margin-block-end: 40px;
  }
  .header {
    display: flex;
    line-height: 44px;
    justify-content: center;
    align-items: center;
    .logo {
      width: 44px;
      height: 44px;
      margin-inline-end: 16px;
    }
    .title {
      font-size: 33px;
      font-weight: 650;
    }
  }
}
.login-form-button {
  width: 100%;
}
.login-form-captcha {
  width: 80px;

  &:hover {
    cursor: pointer;
  }
}
.login-form-forgot {
  float: right;
}
:deep(.ant-input-group .ant-input-group-addon) {
  padding: 0;
}
</style>
