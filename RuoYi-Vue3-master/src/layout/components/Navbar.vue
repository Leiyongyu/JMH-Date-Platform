<template>
  <div class="navbar" :class="'nav' + settingsStore.navType">
    <hamburger id="hamburger-container" :is-active="appStore.sidebar.opened" class="hamburger-container" @toggleClick="toggleSideBar" />
    <breadcrumb v-if="settingsStore.navType == 1" id="breadcrumb-container" class="breadcrumb-container" />
    <top-nav v-if="settingsStore.navType == 2" id="topmenu-container" class="topmenu-container" />
    <template v-if="settingsStore.navType == 3">
      <logo v-show="settingsStore.sidebarLogo" :collapse="false"></logo>
      <top-bar id="topbar-container" class="topbar-container" />
    </template>

    <div class="right-menu">
      <template v-if="appStore.device !== 'mobile'">
        <!-- 数据校准按钮隐藏
        <el-tooltip content="数据校准" effect="dark" placement="bottom" v-hasPermi="['operations:ebayReplenishment:sync']">
          <div class="right-menu-item hover-effect" @click="openCalibration" style="font-size:16px;padding:0 8px;cursor:pointer">
            <svg-icon icon-class="tool" />
          </div>
        </el-tooltip>
        -->

        <ai-assistant id="ai-assistant" class="right-menu-item" />

        <!-- 源码地址、文档地址隐藏 -->

        <screenfull id="screenfull" class="right-menu-item hover-effect" />

        <el-tooltip content="主题模式" effect="dark" placement="bottom">
          <div class="right-menu-item hover-effect theme-switch-wrapper" @click="toggleTheme">
            <SunIcon v-if="settingsStore.isDark" :size="18" color="#f5b545" secondary-color="#f7d9a0" />
            <MoonIcon v-else :size="18" color="#5a6b85" secondary-color="#c4d2e8" />
          </div>
        </el-tooltip>

        <el-tooltip content="布局大小" effect="dark" placement="bottom">
          <size-select id="size-select" class="right-menu-item hover-effect" />
        </el-tooltip>

        <el-tooltip content="消息通知" effect="dark" placement="bottom">
          <header-notice id="header-notice" class="right-menu-item hover-effect" />
        </el-tooltip>
      </template>

      <el-dropdown @command="handleCommand" class="avatar-container right-menu-item hover-effect" trigger="hover">
        <div class="avatar-wrapper">
          <img :src="userStore.avatar" class="user-avatar" />
          <span class="user-nickname">{{ userStore.nickName }}</span>
          <AltArrowDownIcon :size="12" class="avatar-caret" />
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <router-link to="/user/profile">
              <el-dropdown-item>个人中心</el-dropdown-item>
            </router-link>
            <el-dropdown-item command="setLayout" v-if="settingsStore.showSettings">
                <span>布局设置</span>
            </el-dropdown-item>
            <el-dropdown-item command="lockScreen">
                <span>锁定屏幕</span>
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <span>退出登录</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { ElMessageBox } from 'element-plus'
import Breadcrumb from '@/components/Breadcrumb'
import TopNav from './TopNav'
import TopBar from './TopBar'
import Logo from './Sidebar/Logo'
import Hamburger from '@/components/Hamburger'
import Screenfull from '@/components/Screenfull'
import SizeSelect from '@/components/SizeSelect'
import AiAssistant from '@/components/AiAssistant'
import RuoYiGit from '@/components/RuoYi/Git'
import RuoYiDoc from '@/components/RuoYi/Doc'
import useAppStore from '@/store/modules/app'
import useUserStore from '@/store/modules/user'
import useLockStore from '@/store/modules/lock'
import useSettingsStore from '@/store/modules/settings'
import HeaderNotice from './HeaderNotice'
import { SunIcon } from '@solar-icons/vue/bold-duotone/sun'
import { MoonIcon } from '@solar-icons/vue/bold-duotone/moon'
import { AltArrowDownIcon } from '@solar-icons/vue/linear/alt-arrow-down'
import { runDataCalibration } from '@/api/operations/sync'
import { getCurrentInstance } from 'vue'

const { proxy } = getCurrentInstance()
const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()
const lockStore = useLockStore()
const settingsStore = useSettingsStore()

function toggleSideBar() {
  appStore.toggleSideBar()
}

function handleCommand(command) {
  switch (command) {
    case "setLayout":
      setLayout()
      break
    case "lockScreen":
      lockScreen()
      break
    case "logout":
      logout()
      break
    default:
      break
  }
}

function logout() {
  ElMessageBox.confirm('确定注销并退出系统吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logOut().then(() => {
      location.href = '/index'
    })
  }).catch(() => { })
}

/** 数据校准弹窗 */
function openCalibration() {
  ElMessageBox.confirm(
    '<div><p>将拉取全量历史数据并刷新快照，耗时较长。</p>' +
    '<p>默认勾选eBay+AMZ，可选库存采购/谷仓。</p>' +
    '<p>结果可到同步日志查看。</p></div>',
    '数据校准全量拉取',
    { confirmButtonText: '开始校准', cancelButtonText: '取消', type: 'warning',
      dangerouslyUseHTMLString: true }
  ).then(() => {
    const start = prompt('开始日期 (yyyy-MM-dd)', '2024-01-01')
    const end = prompt('结束日期 (yyyy-MM-dd)', new Date().toISOString().slice(0,10))
    if (!start || !end) return
    proxy.$modal.loading('数据校准执行中，请勿关闭页面...')
    runDataCalibration({ start, end, ebay: true, amz: true, inventoryPurchase: true, goodcang: true })
      .then(r => {
        proxy.$modal.closeLoading()
        if (r.code === 200) proxy.$modal.msgSuccess(r.msg || '校准完成')
        else proxy.$modal.msgError(r.msg || '校准失败')
      })
      .catch(e => { proxy.$modal.closeLoading(); proxy.$modal.msgError('校准失败: ' + (e.message||e)) })
  }).catch(() => {})
}

const emits = defineEmits(['setLayout'])
function setLayout() {
  emits('setLayout')
}

function lockScreen() {
  const currentPath = route.fullPath
  lockStore.lockScreen(currentPath)
  router.push('/lock')
}

async function toggleTheme(event) {
  const x = event?.clientX || window.innerWidth / 2
  const y = event?.clientY || window.innerHeight / 2
  const wasDark = settingsStore.isDark

  const isReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  const isSupported = document.startViewTransition && !isReducedMotion

  if (!isSupported) {
    settingsStore.toggleTheme()
    return
  }

  try {
    const transition = document.startViewTransition(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10))
      settingsStore.toggleTheme()
      await nextTick()
    })
    await transition.ready

    const endRadius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    const clipPath = [`circle(0px at ${x}px ${y}px)`, `circle(${endRadius}px at ${x}px ${y}px)`]
    document.documentElement.animate(
      {
        clipPath: !wasDark ? [...clipPath].reverse() : clipPath
      }, {
        duration: 650,
        easing: "cubic-bezier(0.4, 0, 0.2, 1)",
        fill: "forwards",
        pseudoElement: !wasDark ? "::view-transition-old(root)" : "::view-transition-new(root)"
      }
    )
    await transition.finished
  } catch (error) {
    console.warn("View transition failed, falling back to immediate toggle:", error)
    settingsStore.toggleTheme()
  }
}
</script>

<style lang='scss' scoped>
.navbar.nav3 {
  .hamburger-container {
    display: none !important;
  }
}

.navbar {
  height: 50px;
  overflow: hidden;
  position: relative;
  background: var(--navbar-bg);
  border-bottom: 1px solid var(--jb-line, #e3e9f2);
  display: flex;
  align-items: center;
  box-sizing: border-box;

  .hamburger-container {
    height: 32px;
    margin-left: 10px;
    margin-right: 6px;
    padding: 0 7px;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.2s ease, color 0.2s ease;
    -webkit-tap-highlight-color: transparent;
    display: flex;
    align-items: center;
    flex-shrink: 0;
    color: var(--jb-ink-500, #5a6b85);

    &:hover {
      background: var(--jb-hover, #eef3fb);
      color: var(--jb-ink-700, #24334a);
    }
  }

  .breadcrumb-container {
    flex-shrink: 0;
  }

  .topmenu-container {
    position: absolute;
    left: 50px;
  }

  .topbar-container {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    overflow: hidden;
    margin-left: 8px;
  }

  .right-menu {
    height: 100%;
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
    padding-right: 10px;

    &:focus {
      outline: none;
    }

    .right-menu-item {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      height: 32px;
      min-width: 32px;
      padding: 0 6px;
      border-radius: 8px;
      font-size: 18px;
      color: var(--jb-ink-500, #5a6b85);

      &.hover-effect {
        cursor: pointer;
        transition: background-color 0.2s ease, color 0.2s ease;

        &:hover {
          background: var(--jb-hover, #eef3fb);
          color: var(--jb-ink-700, #24334a);
        }
      }

      &.theme-switch-wrapper {
        svg {
          transition: transform 0.3s;

          &:hover {
            transform: scale(1.12) rotate(8deg);
          }
        }
      }
    }

    .avatar-container {
      margin-left: 4px;
      padding: 0 8px !important;

      .avatar-wrapper {
        display: flex;
        align-items: center;
        gap: 8px;

        .user-avatar {
          cursor: pointer;
          width: 30px;
          height: 30px;
          border-radius: 50%;
          box-shadow: 0 0 0 2px var(--jb-brand-100, #e7efff);
        }

        .user-nickname {
          font-size: 13px;
          font-weight: 600;
          color: var(--jb-ink-700, #24334a);
        }

        .avatar-caret {
          color: var(--jb-ink-400, #8a99b0);
        }
      }
    }
  }
}
</style>
