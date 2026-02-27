/**
 * Vitest Setup File
 * 
 * Configures global test environment including:
 * - Element Plus mocks
 * - Vue Router mocks
 * - Pinia setup
 * - Global stubs for browser APIs
 */

import { config } from '@vue/test-utils'
import { vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// ═══════════════════════════════════════════════════════════════════
// 1. ELEMENT PLUS MOCKS
// ═══════════════════════════════════════════════════════════════════

// Mock Element Plus components
const ElementPlusMocks = {
  ElButton: {
    name: 'ElButton',
    template: '<button><slot /></button>',
  },
  ElInput: {
    name: 'ElInput',
    template: '<input />',
    props: ['modelValue', 'placeholder', 'disabled'],
  },
  ElSelect: {
    name: 'ElSelect',
    template: '<select><slot /></select>',
    props: ['modelValue'],
  },
  ElOption: {
    name: 'ElOption',
    template: '<option><slot /></option>',
    props: ['value', 'label'],
  },
  ElTable: {
    name: 'ElTable',
    template: '<table><slot /></table>',
    props: ['data'],
  },
  ElTableColumn: {
    name: 'ElTableColumn',
    template: '<td><slot /></td>',
    props: ['prop', 'label'],
  },
  ElForm: {
    name: 'ElForm',
    template: '<form><slot /></form>',
    props: ['model', 'rules'],
  },
  ElFormItem: {
    name: 'ElFormItem',
    template: '<div class="form-item"><slot /></div>',
    props: ['label', 'prop'],
  },
  ElCard: {
    name: 'ElCard',
    template: '<div class="card"><slot /></div>',
  },
  ElTabs: {
    name: 'ElTabs',
    template: '<div class="tabs"><slot /></div>',
    props: ['modelValue'],
  },
  ElTabPane: {
    name: 'ElTabPane',
    template: '<div class="tab-pane"><slot /></div>',
    props: ['label', 'name'],
  },
  ElProgress: {
    name: 'ElProgress',
    template: '<div class="progress" />',
    props: ['percentage', 'status'],
  },
  ElTag: {
    name: 'ElTag',
    template: '<span class="tag"><slot /></span>',
    props: ['type'],
  },
  ElDropdown: {
    name: 'ElDropdown',
    template: '<div class="dropdown"><slot /></div>',
  },
  ElDropdownMenu: {
    name: 'ElDropdownMenu',
    template: '<div class="dropdown-menu"><slot /></div>',
  },
  ElDropdownItem: {
    name: 'ElDropdownItem',
    template: '<div class="dropdown-item"><slot /></div>',
  },
  ElDialog: {
    name: 'ElDialog',
    template: '<div class="dialog"><slot /></div>',
    props: ['modelValue', 'title'],
  },
  ElCollapse: {
    name: 'ElCollapse',
    template: '<div class="collapse"><slot /></div>',
    props: ['modelValue'],
  },
  ElCollapseItem: {
    name: 'ElCollapseItem',
    template: '<div class="collapse-item"><slot /></div>',
    props: ['title', 'name'],
  },
  ElLoading: {
    name: 'ElLoading',
    template: '<div class="loading"><slot /></div>',
  },
  ElEmpty: {
    name: 'ElEmpty',
    template: '<div class="empty"><slot /></div>',
    props: ['description'],
  },
  ElBadge: {
    name: 'ElBadge',
    template: '<span class="badge"><slot /></span>',
    props: ['value'],
  },
  ElAlert: {
    name: 'ElAlert',
    template: '<div class="alert"><slot /></div>',
    props: ['title', 'type'],
  },
  ElTooltip: {
    name: 'ElTooltip',
    template: '<span><slot /></span>',
    props: ['content'],
  },
  ElDescriptions: {
    name: 'ElDescriptions',
    template: '<div class="descriptions"><slot /></div>',
  },
  ElDescriptionsItem: {
    name: 'ElDescriptionsItem',
    template: '<div class="desc-item"><slot /></div>',
    props: ['label'],
  },
  ElMessage: vi.fn(),
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue({}),
    alert: vi.fn().mockResolvedValue({}),
  },
  ElNotification: vi.fn(),
}

// Register Element Plus mocks globally
config.global.stubs = {
  ...config.global.stubs,
  ...ElementPlusMocks,
}

// Mock Element Plus icons
const iconMock = {
  template: '<span class="icon" />',
}

config.global.stubs.Setting = iconMock
config.global.stubs.Refresh = iconMock
config.global.stubs.Download = iconMock
config.global.stubs.Search = iconMock
config.global.stubs.ArrowDown = iconMock
config.global.stubs.Plus = iconMock
config.global.stubs.Delete = iconMock
config.global.stubs.Edit = iconMock
config.global.stubs.View = iconMock
config.global.stubs.Document = iconMock
config.global.stubs.Folder = iconMock

// ═══════════════════════════════════════════════════════════════════
// 2. VUE ROUTER MOCKS
// ═══════════════════════════════════════════════════════════════════

// Mock vue-router
const mockRouter = {
  push: vi.fn(),
  replace: vi.fn(),
  go: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  currentRoute: {
    value: {
      path: '/',
      params: {},
      query: {},
      name: 'home',
    },
  },
}

const mockRoute = {
  path: '/',
  params: {},
  query: {},
  name: 'home',
}

vi.mock('vue-router', () => ({
  useRouter: () => mockRouter,
  useRoute: () => mockRoute,
  RouterLink: {
    template: '<a><slot /></a>',
    props: ['to'],
  },
  RouterView: {
    template: '<div class="router-view"><slot /></div>',
  },
}))

// ═══════════════════════════════════════════════════════════════════
// 3. PINIA SETUP
// ═══════════════════════════════════════════════════════════════════

// Create fresh pinia for each test
beforeEach(() => {
  setActivePinia(createPinia())
})

// ═══════════════════════════════════════════════════════════════════
// 4. BROWSER API MOCKS
// ═══════════════════════════════════════════════════════════════════

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock IntersectionObserver
global.IntersectionObserver = class {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Mock ResizeObserver
global.ResizeObserver = class {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
    readText: vi.fn().mockResolvedValue(''),
  },
})

// ═══════════════════════════════════════════════════════════════════
// 5. ECHARTS MOCKS
// ═══════════════════════════════════════════════════════════════════

// Mock vue-echarts component
config.global.stubs.VChart = {
  name: 'VChart',
  template: '<div class="v-chart" />',
  props: ['option', 'autoresize'],
}

// Mock echarts module
vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    getOption: vi.fn(() => ({})),
    on: vi.fn(),
    off: vi.fn(),
  })),
  use: vi.fn(),
  registerTheme: vi.fn(),
}))

// ═══════════════════════════════════════════════════════════════════
// 6. FETCH MOCKS
// ═══════════════════════════════════════════════════════════════════

// Default fetch mock
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ code: 200, data: {}, message: 'ok' }),
    text: () => Promise.resolve(''),
    headers: new Headers(),
  })
)

// ═══════════════════════════════════════════════════════════════════
// 7. CONSOLE SUPPRESSION (optional)
// ═══════════════════════════════════════════════════════════════════

// Suppress console.error for cleaner test output (uncomment if needed)
// const originalError = console.error
// beforeAll(() => {
//   console.error = (...args) => {
//     if (typeof args[0] === 'string' && args[0].includes('[Vue warn]')) {
//       return
//     }
//     originalError.call(console, ...args)
//   }
// })
// afterAll(() => {
//   console.error = originalError
// })

// Export mocks for direct use in tests
export { mockRouter, mockRoute, ElementPlusMocks }
