/**
 * 图标注册表（Solar 版）
 * ------------------------------------------------------------
 * 语义名 → Solar linear 线性图标组件（动作/工具/业务图标的主力）
 *
 * 为什么用语义名而不是组件名？
 *   <icon-btn icon="refresh" />  比  <icon-btn icon="RefreshIcon" />  更好读、更好记，
 *   而且将来更换图标库时只改这张表，页面代码不用动。
 *
 * 命名约定：
 *   - 小驼峰 / 短横线   → 走本表（Solar linear）
 *   - PascalCase        → 走 @element-plus/icons-vue（如 Refresh、Promotion）
 *   - 两者都匹配不到     → 走 src/assets/icons/svg 雪碧图（如 shopping、money）
 *
 * 注意：Solar 为 CC BY 4.0 图标授权，需在致谢中署名 480 Design。
 */
import { RefreshIcon } from '@solar-icons/vue/linear/refresh'
import { HamburgerMenuIcon } from '@solar-icons/vue/linear/hamburger-menu'
import { RefreshCircleIcon } from '@solar-icons/vue/linear/refresh-circle'
import { DownloadMinimalisticIcon } from '@solar-icons/vue/linear/download-minimalistic'
import { UploadMinimalisticIcon } from '@solar-icons/vue/linear/upload-minimalistic'
import { DisketteIcon } from '@solar-icons/vue/linear/diskette'
import { UndoLeftIcon } from '@solar-icons/vue/linear/undo-left'
import { FilterIcon } from '@solar-icons/vue/linear/filter'
import { MagnifierIcon } from '@solar-icons/vue/linear/magnifier'
import { EyeIcon } from '@solar-icons/vue/linear/eye'
import { EyeClosedIcon } from '@solar-icons/vue/linear/eye-closed'
import { TableColumnsSplitIcon } from '@solar-icons/vue/linear/table-columns-split'
import { TableRowsSplitIcon } from '@solar-icons/vue/linear/table-rows-split'
import { FullScreenIcon } from '@solar-icons/vue/linear/full-screen'
import { QuitFullScreenIcon } from '@solar-icons/vue/linear/quit-full-screen'
import { MenuDotsIcon } from '@solar-icons/vue/linear/menu-dots'
import { MenuDotsVerticalIcon } from '@solar-icons/vue/linear/menu-dots-vertical'
import { SettingsMinimalisticIcon } from '@solar-icons/vue/linear/settings-minimalistic'
import { SettingsIcon } from '@solar-icons/vue/linear/settings'
import { Tuning2Icon } from '@solar-icons/vue/linear/tuning-2'
import { SortFromTopToBottomIcon } from '@solar-icons/vue/linear/sort-from-top-to-bottom'
import { SortFromBottomToTopIcon } from '@solar-icons/vue/linear/sort-from-bottom-to-top'
import { AddCircleIcon } from '@solar-icons/vue/linear/add-circle'
import { MinusCircleIcon } from '@solar-icons/vue/linear/minus-circle'
import { CloseCircleIcon } from '@solar-icons/vue/linear/close-circle'
import { CheckIcon } from '@solar-icons/vue/linear/check'
import { CheckCircleIcon } from '@solar-icons/vue/linear/check-circle'
import { PenIcon } from '@solar-icons/vue/linear/pen'
import { TrashBinMinimalisticIcon } from '@solar-icons/vue/linear/trash-bin-minimalistic'
import { CopyIcon } from '@solar-icons/vue/linear/copy'
import { PrinterMinimalisticIcon } from '@solar-icons/vue/linear/printer-minimalistic'
import { LinkIcon } from '@solar-icons/vue/linear/link'
import { ShareIcon } from '@solar-icons/vue/linear/share'
import { SquareArrowRightUpIcon } from '@solar-icons/vue/linear/square-arrow-right-up'
import { SendSquareIcon } from '@solar-icons/vue/linear/send-square'
import { PinIcon } from '@solar-icons/vue/linear/pin'
import { StarIcon } from '@solar-icons/vue/linear/star'
import { HistoryIcon } from '@solar-icons/vue/linear/history'
import { ClipboardListIcon } from '@solar-icons/vue/linear/clipboard-list'
import { DocumentTextIcon } from '@solar-icons/vue/linear/document-text'
import { DocumentIcon } from '@solar-icons/vue/linear/document'
import { DangerTriangleIcon } from '@solar-icons/vue/linear/danger-triangle'
import { InfoCircleIcon } from '@solar-icons/vue/linear/info-circle'
import { QuestionCircleIcon } from '@solar-icons/vue/linear/question-circle'
import { GalleryIcon } from '@solar-icons/vue/linear/gallery'
import { Widget4Icon } from '@solar-icons/vue/linear/widget-4'
import { WidgetIcon } from '@solar-icons/vue/linear/widget'
import { BoxIcon } from '@solar-icons/vue/linear/box'
import { BoxMinimalisticIcon } from '@solar-icons/vue/linear/box-minimalistic'
import { GarageIcon } from '@solar-icons/vue/linear/garage'
import { Cart3Icon } from '@solar-icons/vue/linear/cart-3'
import { BagIcon } from '@solar-icons/vue/linear/bag'
import { DeliveryIcon } from '@solar-icons/vue/linear/delivery'
import { RouteIcon } from '@solar-icons/vue/linear/route'
import { BanknoteIcon } from '@solar-icons/vue/linear/banknote'
import { WalletMoneyIcon } from '@solar-icons/vue/linear/wallet-money'
import { MoneyBagIcon } from '@solar-icons/vue/linear/money-bag'
import { CardIcon } from '@solar-icons/vue/linear/card'
import { PercentIcon } from '@solar-icons/vue/linear/percent'
import { TagPriceIcon } from '@solar-icons/vue/linear/tag-price'
import { GraphUpIcon } from '@solar-icons/vue/linear/graph-up'
import { GraphDownIcon } from '@solar-icons/vue/linear/graph-down'
import { Chart2Icon } from '@solar-icons/vue/linear/chart-2'
import { PieChart2Icon } from '@solar-icons/vue/linear/pie-chart-2'
import { CalculatorIcon } from '@solar-icons/vue/linear/calculator'
import { BillIcon } from '@solar-icons/vue/linear/bill'
import { UsersGroupRoundedIcon } from '@solar-icons/vue/linear/users-group-rounded'
import { UserIcon } from '@solar-icons/vue/linear/user'
import { Buildings2Icon } from '@solar-icons/vue/linear/buildings-2'
import { Buildings3Icon } from '@solar-icons/vue/linear/buildings-3'
import { ShopIcon } from '@solar-icons/vue/linear/shop'
import { GlobalIcon } from '@solar-icons/vue/linear/global'
import { CalendarIcon } from '@solar-icons/vue/linear/calendar'
import { ClockCircleIcon } from '@solar-icons/vue/linear/clock-circle'
import { BellIcon } from '@solar-icons/vue/linear/bell'
import { LetterIcon } from '@solar-icons/vue/linear/letter'
import { PhoneIcon } from '@solar-icons/vue/linear/phone'
import { ChatRoundLineIcon } from '@solar-icons/vue/linear/chat-round-line'
import { KeyIcon } from '@solar-icons/vue/linear/key'
import { LockKeyholeIcon } from '@solar-icons/vue/linear/lock-keyhole'
import { FolderOpenIcon } from '@solar-icons/vue/linear/folder-open'
import { ListIcon } from '@solar-icons/vue/linear/list'
import { TableIcon } from '@solar-icons/vue/linear/table'
import { Home2Icon } from '@solar-icons/vue/linear/home-2'
import { DatabaseIcon } from '@solar-icons/vue/linear/database'
import { MapPointIcon } from '@solar-icons/vue/linear/map-point'
import { AltArrowDownIcon } from '@solar-icons/vue/linear/alt-arrow-down'
import { AltArrowRightIcon } from '@solar-icons/vue/linear/alt-arrow-right'
import { AltArrowLeftIcon } from '@solar-icons/vue/linear/alt-arrow-left'
import { ArrowLeftIcon } from '@solar-icons/vue/linear/arrow-left'
import { ArrowRightIcon } from '@solar-icons/vue/linear/arrow-right'
import { SidebarMinimalisticIcon } from '@solar-icons/vue/linear/sidebar-minimalistic'

export const iconRegistry = {
  /* ---------- 动作 ---------- */
  refresh: RefreshIcon,
  drag: HamburgerMenuIcon,
  resync: RefreshCircleIcon,
  export: DownloadMinimalisticIcon,
  download: DownloadMinimalisticIcon,
  import: UploadMinimalisticIcon,
  upload: UploadMinimalisticIcon,
  save: DisketteIcon,
  undo: UndoLeftIcon,
  filter: FilterIcon,
  search: MagnifierIcon,
  eye: EyeIcon,
  eyeOff: EyeClosedIcon,
  columns: TableColumnsSplitIcon,
  density: TableRowsSplitIcon,
  fullscreen: FullScreenIcon,
  exitFullscreen: QuitFullScreenIcon,
  more: MenuDotsIcon,
  moreVertical: MenuDotsVerticalIcon,
  settings: SettingsMinimalisticIcon,
  sliders: Tuning2Icon,
  sort: SortFromTopToBottomIcon,
  sortAsc: SortFromTopToBottomIcon,
  sortDesc: SortFromBottomToTopIcon,
  plus: AddCircleIcon,
  minus: MinusCircleIcon,
  close: CloseCircleIcon,
  check: CheckIcon,
  edit: PenIcon,
  delete: TrashBinMinimalisticIcon,
  copy: CopyIcon,
  print: PrinterMinimalisticIcon,
  link: LinkIcon,
  share: ShareIcon,
  external: SquareArrowRightUpIcon,
  send: SendSquareIcon,
  pin: PinIcon,
  star: StarIcon,
  history: HistoryIcon,
  clipboard: ClipboardListIcon,
  log: DocumentTextIcon,

  /* ---------- 状态 ---------- */
  success: CheckCircleIcon,
  warning: DangerTriangleIcon,
  danger: CloseCircleIcon,
  info: InfoCircleIcon,
  help: QuestionCircleIcon,
  image: GalleryIcon,
  alert: DangerTriangleIcon,
  loading: RefreshIcon,

  /* ---------- 业务 ---------- */
  dashboard: Widget4Icon,
  box: BoxIcon,
  boxes: BoxMinimalisticIcon,
  warehouse: GarageIcon,
  cart: Cart3Icon,
  bag: BagIcon,
  truck: DeliveryIcon,
  ship: RouteIcon,
  route: RouteIcon,
  money: BanknoteIcon,
  wallet: WalletMoneyIcon,
  coins: MoneyBagIcon,
  card: CardIcon,
  percent: PercentIcon,
  tag: TagPriceIcon,
  trendUp: GraphUpIcon,
  trendDown: GraphDownIcon,
  chart: GraphUpIcon,
  chartBar: Chart2Icon,
  chartPie: PieChart2Icon,
  calculate: CalculatorIcon,
  receipt: BillIcon,

  /* ---------- 通用 ---------- */
  users: UsersGroupRoundedIcon,
  user: UserIcon,
  building: Buildings2Icon,
  store: ShopIcon,
  globe: GlobalIcon,
  calendar: CalendarIcon,
  clock: ClockCircleIcon,
  bell: BellIcon,
  mail: LetterIcon,
  phone: PhoneIcon,
  message: ChatRoundLineIcon,
  key: KeyIcon,
  lock: LockKeyholeIcon,
  file: DocumentTextIcon,
  excel: DocumentIcon,
  folder: FolderOpenIcon,
  list: ListIcon,
  table: TableIcon,
  grid: WidgetIcon,
  home: Home2Icon,
  database: DatabaseIcon,
  location: MapPointIcon,
  config: SettingsIcon,

  /* ---------- 导航 ---------- */
  chevronDown: AltArrowDownIcon,
  chevronRight: AltArrowRightIcon,
  chevronLeft: AltArrowLeftIcon,
  arrowLeft: ArrowLeftIcon,
  arrowRight: ArrowRightIcon,
  panelLeft: SidebarMinimalisticIcon
}

/** 判断是否为本表登记的语义图标 */
export function resolveLucide(name) {
  return Object.prototype.hasOwnProperty.call(iconRegistry, name) ? iconRegistry[name] : null
}

/** 供文档/调试查看全部可用语义名 */
export const iconNames = Object.keys(iconRegistry)
