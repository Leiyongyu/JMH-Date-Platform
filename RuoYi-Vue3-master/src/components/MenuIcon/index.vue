<template>
  <component :is="iconComp" v-if="iconComp" :size="size" class="menu-icon" />
  <svg-icon v-else-if="name" :icon-class="name" class="menu-icon menu-icon--legacy" />
</template>

<script setup>
/**
 * MenuIcon — 后台菜单图标
 * 后端 sys_menu.icon 存的是旧雪碧图名称，这里映射到 Solar linear 线性图标，
 * 未收录的名称仍回退到原雪碧图，保证任何菜单都不会缺图标。
 */
import { Home2Icon } from '@solar-icons/vue/linear/home-2'
import { Widget4Icon } from '@solar-icons/vue/linear/widget-4'
import { Widget3Icon } from '@solar-icons/vue/linear/widget-3'
import { Widget2Icon } from '@solar-icons/vue/linear/widget-2'
import { WidgetIcon } from '@solar-icons/vue/linear/widget'
import { SettingsIcon } from '@solar-icons/vue/linear/settings'
import { SettingsMinimalisticIcon } from '@solar-icons/vue/linear/settings-minimalistic'
import { UserIcon } from '@solar-icons/vue/linear/user'
import { UsersGroupRoundedIcon } from '@solar-icons/vue/linear/users-group-rounded'
import { StructureIcon } from '@solar-icons/vue/linear/structure'
import { FolderZipIcon } from '@solar-icons/vue/linear/folder-zip'
import { ClockCircleIcon } from '@solar-icons/vue/linear/clock-circle'
import { CalendarIcon } from '@solar-icons/vue/linear/calendar'
import { DocumentTextIcon } from '@solar-icons/vue/linear/document-text'
import { DocumentAddIcon } from '@solar-icons/vue/linear/document-add'
import { DocumentIcon } from '@solar-icons/vue/linear/document'
import { Chart2Icon } from '@solar-icons/vue/linear/chart-2'
import { GraphUpIcon } from '@solar-icons/vue/linear/graph-up'
import { GraphDownIcon } from '@solar-icons/vue/linear/graph-down'
import { TableIcon } from '@solar-icons/vue/linear/table'
import { ListIcon } from '@solar-icons/vue/linear/list'
import { ListCheckIcon } from '@solar-icons/vue/linear/list-check'
import { PenIcon } from '@solar-icons/vue/linear/pen'
import { DownloadMinimalisticIcon } from '@solar-icons/vue/linear/download-minimalistic'
import { UploadMinimalisticIcon } from '@solar-icons/vue/linear/upload-minimalistic'
import { StarIcon } from '@solar-icons/vue/linear/star'
import { WalletMoneyIcon } from '@solar-icons/vue/linear/wallet-money'
import { CartLargeIcon } from '@solar-icons/vue/linear/cart-large'
import { ServerSquareIcon } from '@solar-icons/vue/linear/server-square'
import { DatabaseIcon } from '@solar-icons/vue/linear/database'
import { CodeSquareIcon } from '@solar-icons/vue/linear/code-square'
import { LetterIcon } from '@solar-icons/vue/linear/letter'
import { PhoneIcon } from '@solar-icons/vue/linear/phone'
import { ChatRoundLineIcon } from '@solar-icons/vue/linear/chat-round-line'
import { QuestionCircleIcon } from '@solar-icons/vue/linear/question-circle'
import { MedalStarIcon } from '@solar-icons/vue/linear/medal-star'
import { SquareAcademicCapIcon } from '@solar-icons/vue/linear/square-academic-cap'
import { ClipboardIcon } from '@solar-icons/vue/linear/clipboard'
import { GlobalIcon } from '@solar-icons/vue/linear/global'
import { LockKeyholeIcon } from '@solar-icons/vue/linear/lock-keyhole'
import { LockPasswordIcon } from '@solar-icons/vue/linear/lock-password'
import { MagnifierIcon } from '@solar-icons/vue/linear/magnifier'
import { PaletteIcon } from '@solar-icons/vue/linear/palette'
import { FullScreenIcon } from '@solar-icons/vue/linear/full-screen'
import { QuitFullScreenIcon } from '@solar-icons/vue/linear/quit-full-screen'
import { AltArrowUpIcon } from '@solar-icons/vue/linear/alt-arrow-up'
import { MoonIcon } from '@solar-icons/vue/linear/moon'
import { SunIcon } from '@solar-icons/vue/linear/sun'
import { BellIcon } from '@solar-icons/vue/linear/bell'
import { BugIcon } from '@solar-icons/vue/linear/bug'
import { LayersIcon } from '@solar-icons/vue/linear/layers'
import { BookIcon } from '@solar-icons/vue/linear/book'
import { MapIcon } from '@solar-icons/vue/linear/map'
import { HashtagIcon } from '@solar-icons/vue/linear/hashtag'
import { RecordCircleIcon } from '@solar-icons/vue/linear/record-circle'
import { Tuning2Icon } from '@solar-icons/vue/linear/tuning-2'
import { CursorIcon } from '@solar-icons/vue/linear/cursor'
import { CheckSquareIcon } from '@solar-icons/vue/linear/check-square'
import { MonitorIcon } from '@solar-icons/vue/linear/monitor'
import { ShieldCheckIcon } from '@solar-icons/vue/linear/shield-check'
import { DangerCircleIcon } from '@solar-icons/vue/linear/danger-circle'
import { MaximizeSquareIcon } from '@solar-icons/vue/linear/maximize-square'
import { KeyIcon } from '@solar-icons/vue/linear/key'
import { LinkIcon } from '@solar-icons/vue/linear/link'
import { EyeIcon } from '@solar-icons/vue/linear/eye'

defineOptions({ name: 'MenuIcon' })

const props = defineProps({
  /** 旧雪碧图图标名（sys_menu.icon） */
  name: { type: String, default: '' },
  size: { type: [Number, String], default: 18 }
})

const MAP = {
  '404': DangerCircleIcon,
  bell: BellIcon,
  bug: BugIcon,
  build: SettingsMinimalisticIcon,
  button: CursorIcon,
  cascader: LayersIcon,
  chart: Chart2Icon,
  checkbox: CheckSquareIcon,
  clipboard: ClipboardIcon,
  code: CodeSquareIcon,
  color: PaletteIcon,
  component: Widget3Icon,
  dashboard: Widget4Icon,
  'date-range': CalendarIcon,
  date: CalendarIcon,
  dict: BookIcon,
  documentation: DocumentTextIcon,
  download: DownloadMinimalisticIcon,
  drag: CursorIcon,
  druid: DatabaseIcon,
  edit: PenIcon,
  education: SquareAcademicCapIcon,
  email: LetterIcon,
  example: WidgetIcon,
  excel: DocumentTextIcon,
  'exit-fullscreen': QuitFullScreenIcon,
  'eye-open': EyeIcon,
  eye: EyeIcon,
  form: DocumentAddIcon,
  fullscreen: FullScreenIcon,
  guide: MapIcon,
  icon: Widget2Icon,
  input: CursorIcon,
  international: GlobalIcon,
  job: ClockCircleIcon,
  key: KeyIcon,
  language: GlobalIcon,
  link: LinkIcon,
  list: ListIcon,
  lock: LockKeyholeIcon,
  log: DocumentTextIcon,
  logininfor: DocumentTextIcon,
  message: ChatRoundLineIcon,
  money: WalletMoneyIcon,
  monitor: MonitorIcon,
  moon: MoonIcon,
  'more-up': AltArrowUpIcon,
  nested: LayersIcon,
  number: HashtagIcon,
  online: UsersGroupRoundedIcon,
  password: LockPasswordIcon,
  pdf: DocumentIcon,
  people: UserIcon,
  peoples: UsersGroupRoundedIcon,
  phone: PhoneIcon,
  question: QuestionCircleIcon,
  radio: RecordCircleIcon,
  rate: StarIcon,
  'redis-list': DatabaseIcon,
  redis: DatabaseIcon,
  row: TableIcon,
  search: MagnifierIcon,
  select: ListCheckIcon,
  server: ServerSquareIcon,
  shopping: CartLargeIcon,
  size: MaximizeSquareIcon,
  skill: MedalStarIcon,
  slider: Tuning2Icon,
  star: StarIcon,
  sunny: SunIcon,
  swagger: CodeSquareIcon,
  switch: Tuning2Icon,
  system: SettingsIcon,
  tab: LayersIcon,
  table: TableIcon,
  textarea: DocumentTextIcon,
  theme: PaletteIcon,
  'time-range': ClockCircleIcon,
  time: ClockCircleIcon,
  tool: SettingsMinimalisticIcon,
  'tree-table': TableIcon,
  tree: StructureIcon,
  upload: UploadMinimalisticIcon,
  user: UserIcon,
  validCode: ShieldCheckIcon,
  zip: FolderZipIcon,
  home: Home2Icon,
  'trend-up': GraphUpIcon,
  'trend-down': GraphDownIcon
}

const iconComp = computed(() => MAP[props.name] || null)
</script>

<style scoped>
.menu-icon {
  flex: none;
  margin-right: 10px;
  color: inherit;
}
</style>
