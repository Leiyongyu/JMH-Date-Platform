<template>
  <div class="sidebar-logo-container" :class="{ 'collapse': collapse }">
    <transition name="sidebarLogoFade">
      <router-link v-if="collapse" key="collapse" class="sidebar-logo-link" to="/">
        <brand-mark :size="30" :variant="isDarkPanel ? 'onDark' : 'onLight'" class="sidebar-logo" />
      </router-link>
      <router-link v-else key="expand" class="sidebar-logo-link" to="/">
        <brand-mark :size="30" :variant="isDarkPanel ? 'onDark' : 'onLight'" class="sidebar-logo" />
        <span class="sidebar-title">
          <strong class="brand-name">JMH</strong>
          <i class="brand-divider"></i>
          <span class="brand-sub">跨境 ERP</span>
        </span>
      </router-link>
    </transition>
  </div>
</template>

<script setup>
import useSettingsStore from '@/store/modules/settings'
import variables from '@/assets/styles/variables.module.scss'

defineProps({
  collapse: {
    type: Boolean,
    required: true
  }
})

const settingsStore = useSettingsStore()
const sideTheme = computed(() => settingsStore.sideTheme)

// 深色面板（深色侧边栏主题或全局暗色模式）
const isDarkPanel = computed(() => {
  if (settingsStore.isDark) return true
  if (settingsStore.navType == 3) return false
  return sideTheme.value === 'theme-dark'
})

// Logo 区背景跟随菜单底色
const getLogoBackground = computed(() => {
  if (settingsStore.isDark) return 'var(--sidebar-bg)'
  if (settingsStore.navType == 3) return variables.menuLightBg
  return sideTheme.value === 'theme-dark' ? variables.menuBg : variables.menuLightBg
})

// 文字与分隔线颜色
const getLogoTextColor = computed(() => (isDarkPanel.value ? '#ffffff' : 'var(--jb-ink-700, #24334a)'))
const getLogoSubColor = computed(() => (isDarkPanel.value ? 'rgba(255,255,255,.62)' : 'var(--jb-ink-500, #5a6b85)'))
const getHairline = computed(() => (isDarkPanel.value ? 'rgba(255,255,255,.08)' : 'var(--jb-line, #e3e9f2)'))
</script>

<style lang="scss" scoped>
.sidebarLogoFade-enter-active {
  transition: opacity 0.6s ease;
}

.sidebarLogoFade-enter,
.sidebarLogoFade-leave-to {
  opacity: 0;
}

.sidebar-logo-container {
  position: relative;
  height: 50px;
  background: v-bind(getLogoBackground);
  box-shadow: inset 0 -1px 0 v-bind(getHairline);
  overflow: hidden;

  .sidebar-logo-link {
    height: 100%;
    width: 100%;
    /* sidebar.scss 中 `#app .sidebar-container a` 优先级更高，此处必须强制覆盖 */
    display: flex !important;
    align-items: center;
    justify-content: center;
    gap: 10px;

    .sidebar-logo {
      flex: none;
    }

    .sidebar-title {
      display: inline-flex;
      align-items: baseline;
      gap: 8px;
      white-space: nowrap;

      .brand-name {
        color: v-bind(getLogoTextColor);
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 0.5px;
      }

      .brand-divider {
        width: 1px;
        height: 12px;
        background: v-bind(getHairline);
        align-self: center;
      }

      .brand-sub {
        color: v-bind(getLogoSubColor);
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 2px;
      }
    }
  }
}
</style>
