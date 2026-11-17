<template>
  <div class="login">
    <!-- ───────────── 左：品牌面板 ───────────── -->
    <aside class="login-brand">
      <div class="bg-grid" aria-hidden="true"></div>
      <div class="bg-glow" aria-hidden="true"></div>
      <div class="bg-ring bg-ring--a" aria-hidden="true"></div>
      <div class="bg-ring bg-ring--b" aria-hidden="true"></div>

      <header class="brand-top">
        <BrandMark :size="34" variant="onDark" />
        <span class="brand-word">JMH</span>
        <span class="brand-rule"></span>
        <span class="brand-tag">跨境 ERP</span>
      </header>

      <div class="brand-body">
        <h2 class="brand-title">加入团队，<br />从这一步开始。</h2>
        <p class="brand-desc">注册后由运营管理员分配店铺与模块权限，即可进入各自的工作台。</p>

        <ul class="brand-chips">
          <li><Chart2Icon :size="15" /><span>利润核算</span></li>
          <li><BoxMinimalisticIcon :size="15" /><span>库存预警</span></li>
          <li><UsersGroupRoundedIcon :size="15" /><span>多店协同</span></li>
        </ul>
      </div>

      <footer class="brand-foot">{{ footerContent }}</footer>
    </aside>

    <!-- ───────────── 右：注册表单 ───────────── -->
    <main class="login-panel">
      <div class="login-box">
        <div class="mobile-brand">
          <BrandMark :size="30" />
          <span>{{ title }}</span>
        </div>

        <p class="eyebrow">创建账号</p>
        <h1 class="panel-title">注册工作台</h1>
        <p class="panel-desc">填写账号信息，注册成功后返回登录页登录</p>

        <el-form
          ref="registerRef"
          :model="registerForm"
          :rules="registerRules"
          class="login-form"
          hide-required-asterisk
          @submit.prevent
        >
          <el-form-item prop="username">
            <div class="field">
              <label class="field-label" for="rg-user">账号</label>
              <el-input
                id="rg-user"
                v-model="registerForm.username"
                type="text"
                size="large"
                auto-complete="off"
                placeholder="2-20 位字符"
              >
                <template #prefix><UserIcon :size="18" class="field-icon" /></template>
              </el-input>
            </div>
          </el-form-item>

          <el-form-item prop="password" :rules="registerPwdValidator">
            <div class="field">
              <label class="field-label" for="rg-pwd">密码</label>
              <el-input
                id="rg-pwd"
                v-model="registerForm.password"
                :type="pwdVisible ? 'text' : 'password'"
                size="large"
                auto-complete="off"
                placeholder="请输入密码"
                @keyup.enter="handleRegister"
              >
                <template #prefix><LockPasswordIcon :size="18" class="field-icon" /></template>
                <template #suffix>
                  <button
                    type="button"
                    class="pwd-toggle"
                    :aria-label="pwdVisible ? '隐藏密码' : '显示密码'"
                    :title="pwdVisible ? '隐藏密码' : '显示密码'"
                    @click="pwdVisible = !pwdVisible"
                  >
                    <EyeIcon v-if="pwdVisible" :size="16" />
                    <EyeClosedIcon v-else :size="16" />
                  </button>
                </template>
              </el-input>
            </div>
          </el-form-item>

          <el-form-item prop="confirmPassword">
            <div class="field">
              <label class="field-label" for="rg-pwd2">确认密码</label>
              <el-input
                id="rg-pwd2"
                v-model="registerForm.confirmPassword"
                :type="pwd2Visible ? 'text' : 'password'"
                size="large"
                auto-complete="off"
                placeholder="请再次输入密码"
                @keyup.enter="handleRegister"
              >
                <template #prefix><LockPasswordIcon :size="18" class="field-icon" /></template>
                <template #suffix>
                  <button
                    type="button"
                    class="pwd-toggle"
                    :aria-label="pwd2Visible ? '隐藏密码' : '显示密码'"
                    :title="pwd2Visible ? '隐藏密码' : '显示密码'"
                    @click="pwd2Visible = !pwd2Visible"
                  >
                    <EyeIcon v-if="pwd2Visible" :size="16" />
                    <EyeClosedIcon v-else :size="16" />
                  </button>
                </template>
              </el-input>
            </div>
          </el-form-item>

          <el-form-item prop="code" v-if="captchaEnabled">
            <div class="field">
              <label class="field-label" for="rg-code">验证码</label>
              <div class="code-row">
                <el-input
                  id="rg-code"
                  v-model="registerForm.code"
                  size="large"
                  auto-complete="off"
                  placeholder="请输入验证码"
                  @keyup.enter="handleRegister"
                >
                  <template #prefix><ShieldCheckIcon :size="18" class="field-icon" /></template>
                </el-input>
                <button type="button" class="code-box" title="点击刷新验证码" @click="getCode">
                  <img :src="codeUrl" alt="验证码" />
                  <span class="code-refresh"><RefreshIcon :size="14" /></span>
                </button>
              </div>
            </div>
          </el-form-item>

          <el-button type="primary" class="submit" :loading="loading" @click.prevent="handleRegister">
            <span class="submit-tx">{{ loading ? '注册中' : '注 册' }}</span>
            <ArrowRightIcon v-if="!loading" :size="17" class="submit-arrow" />
          </el-button>

          <p class="back-login">
            已有账号？<router-link class="link-type" :to="'/login'">直接登录</router-link>
          </p>
        </el-form>

        <p class="panel-foot">注册后请联系运营管理员开通权限</p>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ElMessageBox } from "element-plus"
import { getCodeImg, register } from "@/api/login"
import defaultSettings from '@/settings'
import { usePasswordRule } from "@/utils/passwordRule"

import { UserIcon } from '@solar-icons/vue/bold-duotone/user'
import { LockPasswordIcon } from '@solar-icons/vue/bold-duotone/lock-password'
import { EyeIcon } from '@solar-icons/vue/bold-duotone/eye'
import { EyeClosedIcon } from '@solar-icons/vue/bold-duotone/eye-closed'
import { ShieldCheckIcon } from '@solar-icons/vue/bold-duotone/shield-check'
import { RefreshIcon } from '@solar-icons/vue/bold-duotone/refresh'
import { ArrowRightIcon } from '@solar-icons/vue/bold-duotone/arrow-right'
import { Chart2Icon } from '@solar-icons/vue/bold-duotone/chart-2'
import { BoxMinimalisticIcon } from '@solar-icons/vue/bold-duotone/box-minimalistic'
import { UsersGroupRoundedIcon } from '@solar-icons/vue/bold-duotone/users-group-rounded'

const title = import.meta.env.VITE_APP_TITLE
const footerContent = defaultSettings.footerContent
const router = useRouter()
const { proxy } = getCurrentInstance()
const { registerPwdValidator } = usePasswordRule()

const registerForm = ref({
  username: "",
  password: "",
  confirmPassword: "",
  code: "",
  uuid: ""
})

// 密码明文切换
const pwdVisible = ref(false)
const pwd2Visible = ref(false)

const equalToPassword = (rule, value, callback) => {
  if (registerForm.value.password !== value) {
    callback(new Error("两次输入的密码不一致"))
  } else {
    callback()
  }
}

const registerRules = {
  username: [
    { required: true, trigger: "blur", message: "请输入您的账号" },
    { min: 2, max: 20, message: "用户账号长度必须介于 2 和 20 之间", trigger: "blur" }
  ],
  confirmPassword: [
    { required: true, trigger: "blur", message: "请再次输入您的密码" },
    { required: true, validator: equalToPassword, trigger: "blur" }
  ],
  code: [{ required: true, trigger: "change", message: "请输入验证码" }]
}

const codeUrl = ref("")
const loading = ref(false)
const captchaEnabled = ref(true)

function handleRegister() {
  proxy.$refs.registerRef.validate(valid => {
    if (valid) {
      loading.value = true
      register(registerForm.value).then(res => {
        const username = registerForm.value.username
        ElMessageBox.alert("恭喜你，您的账号 " + username + " 注册成功！", "系统提示", {
          type: "success",
        }).then(() => {
          router.push("/login")
        }).catch(() => {})
      }).catch(() => {
        loading.value = false
        if (captchaEnabled) {
          getCode()
        }
      })
    }
  })
}

function getCode() {
  getCodeImg().then(res => {
    captchaEnabled.value = res.captchaEnabled === undefined ? true : res.captchaEnabled
    if (captchaEnabled.value) {
      codeUrl.value = "data:image/gif;base64," + res.img
      registerForm.value.uuid = res.uuid
    }
  })
}

getCode()
</script>

<style lang="scss" scoped>
/* 与登录页同构：左品牌面板 + 右表单面板 */
.login {
  --lp-canvas: #f5f7fb;
  --lp-panel: #ffffff;
  --lp-field: #f4f7fb;
  --lp-field-hover: #edf2fa;
  --lp-field-focus: #ffffff;
  --lp-text: #0b1526;
  --lp-sub: #5a6b85;
  --lp-mute: #8a99b0;
  --lp-line: #e3e9f2;
  --lp-brand: #1257d6;
  --lp-brand-ring: rgba(18, 87, 214, 0.12);

  display: grid;
  grid-template-columns: minmax(0, 1.06fr) minmax(0, 1fr);
  height: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--lp-canvas);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

.login-brand {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 44px 56px 38px;
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(88% 72% at 2% 0%, rgba(3, 11, 28, 0.72), transparent 62%),
    linear-gradient(133deg, #071c3e 0%, #0a3068 38%, #0b5286 68%, #0e8b8c 88%, #12b2a6 100%);
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.055) 1px, transparent 1px);
  background-size: 56px 56px;
  -webkit-mask-image: radial-gradient(120% 95% at 0% 0%, #000 22%, transparent 68%);
  mask-image: radial-gradient(120% 95% at 0% 0%, #000 22%, transparent 68%);
}

.bg-glow {
  position: absolute;
  top: -300px;
  right: -260px;
  width: 760px;
  height: 760px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(18, 178, 166, 0.16), transparent 64%);
}

.bg-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.085);

  &--a {
    right: -240px;
    top: 34%;
    width: 620px;
    height: 620px;
  }

  &--b {
    right: -400px;
    top: 18%;
    width: 940px;
    height: 940px;
    border-color: rgba(255, 255, 255, 0.05);
  }
}

.brand-top,
.brand-body,
.brand-foot {
  position: relative;
  z-index: 1;
}

.brand-top {
  display: flex;
  align-items: center;
  gap: 11px;
}

.brand-word {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.brand-rule {
  width: 1px;
  height: 13px;
  background: rgba(255, 255, 255, 0.3);
}

.brand-tag {
  font-size: 12px;
  letter-spacing: 0.1em;
  color: rgba(255, 255, 255, 0.62);
}

.brand-body {
  max-width: 452px;
}

.brand-title {
  margin: 0 0 18px;
  font-size: 34px;
  line-height: 1.34;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.brand-desc {
  margin: 0 0 30px;
  max-width: 380px;
  font-size: 13.5px;
  line-height: 1.85;
  color: rgba(255, 255, 255, 0.6);
}

.brand-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 13px 7px 10px;
    border-radius: 999px;
    font-size: 12px;
    letter-spacing: 0.02em;
    color: rgba(255, 255, 255, 0.88);
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    -webkit-backdrop-filter: blur(6px);
    backdrop-filter: blur(6px);
  }

  svg {
    color: #8fe6de;
  }
}

.brand-foot {
  font-size: 11.5px;
  letter-spacing: 0.02em;
  color: rgba(255, 255, 255, 0.34);
}

.login-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  padding: 48px 40px;
  background: var(--lp-panel);
  overflow-y: auto;
}

.login-box {
  width: 100%;
  min-width: 0;
  max-width: 372px;
}

.mobile-brand {
  display: none;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--lp-text);
}

.eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  letter-spacing: 0.14em;
  color: var(--lp-brand);
  font-weight: 500;
}

.panel-title {
  margin: 0 0 8px;
  font-size: 25px;
  line-height: 1.3;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--lp-text);
}

.panel-desc {
  margin: 0 0 30px;
  font-size: 12.5px;
  color: var(--lp-mute);
}

.login-form {
  :deep(.el-form-item) {
    display: block;
    margin-bottom: 24px;
  }

  :deep(.el-form-item__content) {
    display: block;
    line-height: normal;
  }

  :deep(.el-form-item__error) {
    padding-top: 5px;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--jb-danger, #f56c6c);
  }
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--lp-sub);
}

.login-form {
  :deep(.el-input__wrapper) {
    padding: 0 12px;
    border-radius: 8px;
    background: var(--lp-field);
    box-shadow: inset 0 0 0 1px transparent;
    transition: background 0.16s ease, box-shadow 0.16s ease;
  }

  :deep(.el-input__wrapper:hover) {
    background: var(--lp-field-hover);
  }

  :deep(.el-input__wrapper.is-focus) {
    background: var(--lp-field-focus);
    box-shadow: inset 0 0 0 1px var(--lp-brand), 0 0 0 3px var(--lp-brand-ring);
  }

  :deep(.el-input__inner) {
    height: 44px;
    font-size: 13.5px;
    color: var(--lp-text);
    letter-spacing: 0.01em;

    &::placeholder {
      color: var(--lp-mute);
    }
  }

  :deep(.el-input__prefix) {
    margin-right: 2px;
  }

  :deep(.el-input__suffix) {
    margin-left: 2px;
  }

  .field:focus-within .field-icon {
    color: var(--lp-brand);
  }
}

.field-icon {
  color: var(--lp-sub);
  transition: color 0.16s ease;
}

.pwd-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  color: var(--lp-mute);
  background: transparent;
  cursor: pointer;
  transition: color 0.16s ease, background 0.16s ease;

  &:hover {
    color: var(--lp-sub);
    background: rgba(13, 26, 45, 0.06);
  }
}

.code-row {
  display: flex;
  align-items: stretch;
  gap: 10px;

  .el-input {
    flex: 1;
    min-width: 0;
  }
}

.code-box {
  position: relative;
  flex: none;
  align-self: stretch;
  box-sizing: border-box;
  width: 108px;
  min-height: 44px;
  padding: 0;
  border: 1px solid var(--lp-line);
  border-radius: 8px;
  background: var(--lp-field);
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.16s ease;

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  &:hover {
    border-color: var(--lp-brand);
  }

  &:hover .code-refresh {
    opacity: 1;
  }
}

.code-refresh {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: rgba(11, 21, 38, 0.42);
  opacity: 0;
  transition: opacity 0.16s ease;
}

.link-type {
  font-size: 12.5px;
  color: var(--lp-brand);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.submit {
  position: relative;
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.08em;
  background: linear-gradient(180deg, #2a6be6 0%, #1257d6 100%);
  box-shadow: 0 8px 18px -10px rgba(18, 87, 214, 0.85);
  transition: transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease;

  &:hover {
    filter: brightness(1.05);
    box-shadow: 0 10px 22px -10px rgba(18, 87, 214, 0.9);
  }

  &:active {
    transform: translateY(1px);
  }

  :deep(.submit-tx) {
    letter-spacing: 0.08em;
  }

  .submit-arrow {
    margin-left: 8px;
    transition: transform 0.18s ease;
  }

  &:hover .submit-arrow {
    transform: translateX(3px);
  }
}

.back-login {
  margin: 16px 0 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--lp-mute);
}

.panel-foot {
  margin: 22px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--lp-mute);
  text-align: center;
}

html.dark .login {
  --lp-canvas: #070d18;
  --lp-panel: #0c1420;
  --lp-field: rgba(255, 255, 255, 0.045);
  --lp-field-hover: rgba(255, 255, 255, 0.07);
  --lp-field-focus: rgba(255, 255, 255, 0.06);
  --lp-text: #eaf0f9;
  --lp-sub: #9baabf;
  --lp-mute: #6f7f96;
  --lp-line: rgba(255, 255, 255, 0.12);
  --lp-brand: #5b93f5;
  --lp-brand-ring: rgba(91, 147, 245, 0.18);
}

html.dark .login-panel {
  border-left: 1px solid rgba(255, 255, 255, 0.06);
}

@media (max-width: 1024px) {
  .login {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .login-brand {
    padding: 36px 36px 32px;
  }

  .brand-title {
    font-size: 27px;
  }
}

@media (max-width: 860px) {
  .login {
    grid-template-columns: minmax(0, 1fr);
  }

  .login-brand {
    display: none;
  }

  .login-panel {
    padding: 40px 24px;
  }

  .mobile-brand {
    display: flex;
  }

  .code-box {
    width: 96px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login * {
    transition: none !important;
  }
}
</style>
