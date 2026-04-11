# React 状态管理中的 useReducer：适用边界、设计方法与替代方案

## useReducer 是什么

`useReducer` 用来管理一段组件状态。它把“状态如何变化”从事件处理函数中抽离出来，集中放进一个 reducer 函数。

```tsx
const [state, dispatch] = useReducer(reducer, initialState)

type Reducer<State, Action> = (state: State, action: Action) => State
```

这里的 `state` 指当前这次 action 被处理时的状态。`initialState` 只参与初始化，后续每次 `dispatch(action)`，React 都会把当时那一份 state 传给 reducer。

这个 Hook 适合处理联动规则较多、状态迁移路径需要收口的场景。

---

## 何时值得使用

先看一个简单表单。

### 直接使用 useState

```tsx
import React, { useState } from 'react'

type SearchFormState = {
  keyword: string
  owner: string
}

export default function SearchFormWithState() {
  const [form, setForm] = useState<SearchFormState>({
    keyword: '',
    owner: '',
  })

  return (
    <div>
      <input
        placeholder="关键词"
        value={form.keyword}
        onChange={(e) =>
          setForm((prev) => ({ ...prev, keyword: e.target.value }))
        }
      />

      <input
        placeholder="负责人"
        value={form.owner}
        onChange={(e) =>
          setForm((prev) => ({ ...prev, owner: e.target.value }))
        }
      />

      <pre>{JSON.stringify(form, null, 2)}</pre>
    </div>
  )
}
```

这个场景字段少，联动少，`useState` 足够直接。

再看同一个表单，改成 `useReducer`。

### 抽成 useReducer

```tsx
import React, { useReducer } from 'react'

type SearchState = {
  keyword: string
  owner: string
}

type SearchAction =
  | { type: 'keyword/changed'; payload: string }
  | { type: 'owner/changed'; payload: string }

function searchReducer(
  state: SearchState,
  action: SearchAction
): SearchState {
  switch (action.type) {
    case 'keyword/changed':
      return { ...state, keyword: action.payload }
    case 'owner/changed':
      return { ...state, owner: action.payload }
    default: {
      const _exhaustive: never = action
      return state
    }
  }
}

export default function SearchFormWithReducer() {
  const [state, dispatch] = useReducer(searchReducer, {
    keyword: '',
    owner: '',
  })

  return (
    <div>
      <input
        placeholder="关键词"
        value={state.keyword}
        onChange={(e) =>
          dispatch({ type: 'keyword/changed', payload: e.target.value })
        }
      />

      <input
        placeholder="负责人"
        value={state.owner}
        onChange={(e) =>
          dispatch({ type: 'owner/changed', payload: e.target.value })
        }
      />

      <pre>{JSON.stringify(state, null, 2)}</pre>
    </div>
  )
}
```

这段代码能工作，但收益很有限。它多了 action 类型、多了 reducer、多了 dispatch，复杂度高于 `useState` 版本。

当业务逻辑持续增加后，情况会变掉。常见变化包括：

* 一个动作会同时影响多个字段
* 某个切换动作会顺带清空、重置、禁用其他配置
* 提交前要统一校验多个区域
* 草稿加载、保存、发布会共用同一批状态迁移规则

这时组件里的事件函数会快速膨胀，`useReducer` 开始有价值。

---

## 如何将业务逻辑从组件中抽离

先看一段常见写法。页面里有一个优惠渠道开关，关闭全部渠道时要报错。

```tsx
function handleChannelToggle(channel: Channel) {
  setForm((prev) => {
    const nextChannels = {
      ...prev.channels,
      [channel]: !prev.channels[channel],
    }

    if (!nextChannels.app && !nextChannels.sms && !nextChannels.wechat) {
      setErrors((old) => ({
        ...old,
        channels: '至少保留一个投放渠道',
      }))
    } else {
      setErrors((old) => ({
        ...old,
        channels: '',
      }))
    }

    return {
      ...prev,
      channels: nextChannels,
    }
  })
}
```

这里有两个问题：

* 状态迁移和错误处理写在一个事件函数里
* `setForm` 内部又嵌了 `setErrors`

这种代码一开始还能维护，动作一多就会散掉。

更稳的方式是先把业务逻辑抽成纯函数：

```tsx
function toggleChannel(state: StrategyState, channel: Channel): StrategyState {
  const nextChannels = {
    ...state.channels,
    [channel]: !state.channels[channel],
  }

  const hasEnabledChannel =
    nextChannels.app || nextChannels.sms || nextChannels.wechat

  return {
    ...state,
    channels: nextChannels,
    errors: {
      ...state.errors,
      channels: hasEnabledChannel ? '' : '至少保留一个投放渠道',
    },
    dirty: true,
  }
}
```

如果页面还比较轻，可以继续留在 `useState`：

```tsx
const [state, setState] = useState(initialState)

function handleChannelToggle(channel: Channel) {
  setState((prev) => toggleChannel(prev, channel))
}
```

如果动作已经很多，再切到 `useReducer`：

```tsx
case 'channel/toggled':
  return toggleChannel(state, action.payload)
```

组件里只剩：

```tsx
dispatch({ type: 'channel/toggled', payload: 'sms' })
```

这就是 `useReducer` 最稳定的使用方式：先抽纯函数，再决定是否引入 reducer。

---

## 实战案例：预授信策略配置页

这个页面承接的是本地编辑态，不把服务端查询结果、版本列表、发布记录混进来。页面需求包括：

* 编辑策略名称、优先级、发布方式
* 配置投放渠道
* 配置客群准入规则
* 配置额度、利率、期数
* 配置 A/B 分桶
* 支持草稿加载、保存、发布
* 发布前统一校验

这类页面有两个实现约束需要先定下来。

第一，state 只保存原始业务数据和流程状态。
第二，派生结果不进 reducer state。

例如下面这些值：

* 启用渠道数
* 规则条数
* A/B 分桶总和
* 当前是否允许发布

都可以从当前 state 推出来，直接在 render 阶段计算；计算量较大时再配合 `useMemo`。不要把这些值再存回 reducer state。

### 类型定义

```tsx
import React, { useMemo, useReducer } from 'react'

type Channel = 'app' | 'sms' | 'wechat'
type PublishMode = 'manual' | 'scheduled'
type AudienceField = 'city' | 'creditScore' | 'aumLevel' | 'insuranceFlag'
type AudienceOperator = 'eq' | 'in' | 'gt' | 'lt'

type AudienceCondition = {
  id: string
  field: AudienceField
  operator: AudienceOperator
  value: string | number | string[]
}

type StrategyState = {
  base: {
    name: string
    priority: number
    publishMode: PublishMode
    publishAt: string | null
  }
  channels: Record<Channel, boolean>
  audience: AudienceCondition[]
  limitRule: {
    minAmount: number
    maxAmount: number
    rate: number
    term: number
  }
  abTest: {
    enabled: boolean
    buckets: number[]
  }
  errors: Record<string, string>
  isSaving: boolean
  isPublishing: boolean
  dirty: boolean
}

type StrategyAction =
  | { type: 'base/nameChanged'; payload: string }
  | { type: 'base/priorityChanged'; payload: number }
  | { type: 'base/publishModeChanged'; payload: PublishMode }
  | { type: 'base/publishAtChanged'; payload: string | null }
  | { type: 'channel/toggled'; payload: Channel }
  | { type: 'audience/added'; payload: AudienceCondition }
  | {
      type: 'audience/updated'
      payload: { id: string; patch: Partial<Omit<AudienceCondition, 'id'>> }
    }
  | { type: 'audience/removed'; payload: { id: string } }
  | {
      type: 'limitRule/changed'
      payload: Partial<StrategyState['limitRule']>
    }
  | { type: 'abTest/toggled'; payload: boolean }
  | { type: 'abTest/bucketsChanged'; payload: number[] }
  | { type: 'validation/performed'; payload: Record<string, string> }
  | {
      type: 'draft/loaded'
      payload: Omit<StrategyState, 'errors' | 'isSaving' | 'isPublishing' | 'dirty'>
    }
  | { type: 'save/started' }
  | { type: 'save/finished' }
  | { type: 'publish/started' }
  | { type: 'publish/failed'; payload: string }
  | { type: 'publish/succeeded' }
```

### 纯函数

```tsx
function normalizeBuckets(enabled: boolean, buckets: number[]): number[] {
  if (!enabled) return []
  return buckets.map((value) => Math.max(0, Math.floor(value)))
}

function validateStrategy(state: StrategyState): Record<string, string> {
  const errors: Record<string, string> = {}

  if (!state.base.name.trim()) {
    errors.name = '策略名称不能为空'
  }

  if (
    !state.channels.app &&
    !state.channels.sms &&
    !state.channels.wechat
  ) {
    errors.channels = '至少保留一个投放渠道'
  }

  if (state.audience.length === 0) {
    errors.audience = '至少配置一条客群规则'
  }

  if (state.limitRule.minAmount > state.limitRule.maxAmount) {
    errors.limitRule = '额度下限不能大于额度上限'
  }

  if (state.base.publishMode === 'scheduled' && !state.base.publishAt) {
    errors.publishAt = '定时发布需要填写发布时间'
  }

  if (state.abTest.enabled) {
    const total = state.abTest.buckets.reduce((sum, n) => sum + n, 0)
    if (total !== 100) {
      errors.abTest = 'A/B 分桶总和必须等于 100'
    }
  }

  return errors
}

function toggleChannel(
  state: StrategyState,
  channel: Channel
): StrategyState {
  const nextChannels = {
    ...state.channels,
    [channel]: !state.channels[channel],
  }

  const hasEnabledChannel =
    nextChannels.app || nextChannels.sms || nextChannels.wechat

  return {
    ...state,
    channels: nextChannels,
    errors: {
      ...state.errors,
      channels: hasEnabledChannel ? '' : '至少保留一个投放渠道',
    },
    dirty: true,
  }
}
```

### Reducer

```tsx
function strategyReducer(
  state: StrategyState,
  action: StrategyAction
): StrategyState {
  switch (action.type) {
    case 'base/nameChanged':
      return {
        ...state,
        base: {
          ...state.base,
          name: action.payload,
        },
        dirty: true,
      }

    case 'base/priorityChanged':
      return {
        ...state,
        base: {
          ...state.base,
          priority: action.payload,
        },
        dirty: true,
      }

    case 'base/publishModeChanged':
      return {
        ...state,
        base: {
          ...state.base,
          publishMode: action.payload,
          publishAt: action.payload === 'manual' ? null : state.base.publishAt,
        },
        dirty: true,
      }

    case 'base/publishAtChanged':
      return {
        ...state,
        base: {
          ...state.base,
          publishAt: action.payload,
        },
        dirty: true,
      }

    case 'channel/toggled':
      return toggleChannel(state, action.payload)

    case 'audience/added':
      return {
        ...state,
        audience: [...state.audience, action.payload],
        dirty: true,
      }

    case 'audience/updated':
      return {
        ...state,
        audience: state.audience.map((item) =>
          item.id === action.payload.id
            ? { ...item, ...action.payload.patch }
            : item
        ),
        dirty: true,
      }

    case 'audience/removed':
      return {
        ...state,
        audience: state.audience.filter((item) => item.id !== action.payload.id),
        dirty: true,
      }

    case 'limitRule/changed':
      return {
        ...state,
        limitRule: {
          ...state.limitRule,
          ...action.payload,
        },
        dirty: true,
      }

    case 'abTest/toggled':
      return {
        ...state,
        abTest: {
          ...state.abTest,
          enabled: action.payload,
          buckets: normalizeBuckets(action.payload, state.abTest.buckets),
        },
        dirty: true,
      }

    case 'abTest/bucketsChanged':
      return {
        ...state,
        abTest: {
          ...state.abTest,
          buckets: normalizeBuckets(state.abTest.enabled, action.payload),
        },
        dirty: true,
      }

    case 'validation/performed':
      return {
        ...state,
        errors: action.payload,
      }

    case 'draft/loaded':
      return {
        ...action.payload,
        errors: {},
        isSaving: false,
        isPublishing: false,
        dirty: false,
      }

    case 'save/started':
      return {
        ...state,
        isSaving: true,
      }

    case 'save/finished':
      return {
        ...state,
        isSaving: false,
        dirty: false,
      }

    case 'publish/started':
      return {
        ...state,
        isPublishing: true,
        errors: {
          ...state.errors,
          submit: '',
        },
      }

    case 'publish/failed':
      return {
        ...state,
        isPublishing: false,
        errors: {
          ...state.errors,
          submit: action.payload,
        },
      }

    case 'publish/succeeded':
      return {
        ...state,
        isPublishing: false,
        dirty: false,
      }

    default: {
      const _exhaustive: never = action
      return state
    }
  }
}
```

`default` 分支里的 `never` 用来做穷举检查。新增了 action 类型，但忘了在 reducer 里补分支时，TypeScript 会直接报错。

### 组件

```tsx
const initialState: StrategyState = {
  base: {
    name: '',
    priority: 1,
    publishMode: 'manual',
    publishAt: null,
  },
  channels: {
    app: true,
    sms: false,
    wechat: false,
  },
  audience: [],
  limitRule: {
    minAmount: 1000,
    maxAmount: 50000,
    rate: 0.06,
    term: 12,
  },
  abTest: {
    enabled: false,
    buckets: [],
  },
  errors: {},
  isSaving: false,
  isPublishing: false,
  dirty: false,
}

export default function StrategyEditorPage() {
  const [state, dispatch] = useReducer(strategyReducer, initialState)

  const enabledChannelCount = useMemo(
    () => Object.values(state.channels).filter(Boolean).length,
    [state.channels]
  )

  const audienceCount = state.audience.length

  const abBucketTotal = useMemo(
    () => state.abTest.buckets.reduce((sum, n) => sum + n, 0),
    [state.abTest.buckets]
  )

  const canPublish = useMemo(() => {
    const errors = validateStrategy(state)
    return Object.keys(errors).length === 0
  }, [state])

  async function handlePublish() {
    const errors = validateStrategy(state)
    dispatch({ type: 'validation/performed', payload: errors })

    if (Object.keys(errors).length > 0) {
      return
    }

    dispatch({ type: 'publish/started' })

    try {
      await publishStrategy({
        base: state.base,
        channels: state.channels,
        audience: state.audience,
        limitRule: state.limitRule,
        abTest: state.abTest,
      })

      dispatch({ type: 'publish/succeeded' })
    } catch {
      dispatch({
        type: 'publish/failed',
        payload: '发布失败，请稍后重试',
      })
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <h2>{state.base.name || '未命名策略'}</h2>

      <section>
        <div>启用渠道数：{enabledChannelCount}</div>
        <div>客群规则数：{audienceCount}</div>
        <div>A/B 分桶总和：{abBucketTotal}</div>
      </section>

      <section style={{ marginTop: 16 }}>
        <input
          placeholder="策略名称"
          value={state.base.name}
          onChange={(e) =>
            dispatch({ type: 'base/nameChanged', payload: e.target.value })
          }
        />

        <select
          value={state.base.publishMode}
          onChange={(e) =>
            dispatch({
              type: 'base/publishModeChanged',
              payload: e.target.value as PublishMode,
            })
          }
        >
          <option value="manual">手动发布</option>
          <option value="scheduled">定时发布</option>
        </select>

        {state.base.publishMode === 'scheduled' && (
          <input
            placeholder="发布时间"
            value={state.base.publishAt ?? ''}
            onChange={(e) =>
              dispatch({
                type: 'base/publishAtChanged',
                payload: e.target.value || null,
              })
            }
          />
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <button
          onClick={() => dispatch({ type: 'channel/toggled', payload: 'app' })}
        >
          APP：{state.channels.app ? '开启' : '关闭'}
        </button>

        <button
          onClick={() => dispatch({ type: 'channel/toggled', payload: 'sms' })}
        >
          短信：{state.channels.sms ? '开启' : '关闭'}
        </button>

        <button
          onClick={() =>
            dispatch({ type: 'channel/toggled', payload: 'wechat' })
          }
        >
          微信：{state.channels.wechat ? '开启' : '关闭'}
        </button>

        {state.errors.channels && (
          <div style={{ color: 'red' }}>{state.errors.channels}</div>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <button
          onClick={() =>
            dispatch({
              type: 'audience/added',
              payload: {
                id: String(Date.now()),
                field: 'creditScore',
                operator: 'gt',
                value: 650,
              },
            })
          }
        >
          新增规则
        </button>

        <ul>
          {state.audience.map((item) => (
            <li key={item.id}>
              {item.field} {item.operator} {String(item.value)}
              <button
                onClick={() =>
                  dispatch({
                    type: 'audience/removed',
                    payload: { id: item.id },
                  })
                }
              >
                删除
              </button>
            </li>
          ))}
        </ul>

        {state.errors.audience && (
          <div style={{ color: 'red' }}>{state.errors.audience}</div>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <button onClick={handlePublish} disabled={!canPublish || state.isPublishing}>
          {state.isPublishing ? '发布中...' : '发布策略'}
        </button>

        {state.errors.submit && (
          <div style={{ color: 'red' }}>{state.errors.submit}</div>
        )}
      </section>
    </div>
  )
}

async function publishStrategy(_: unknown) {
  return new Promise((resolve) => setTimeout(resolve, 500))
}
```

这个例子里有两个点值得注意。

一个是派生值没有回写进 state。
另一个是异步请求没有写进 reducer。`handlePublish` 负责发请求，reducer 只负责同步状态迁移。

### 性能边界

`useReducer` 解决的是结构问题，不是订阅粒度问题。

只要这段 state 挂在父组件上，每次 `dispatch`，父组件都会重新执行 render。页面越大，这种影响越明显。左侧规则树、右侧配置表单、底部预览都在同一个组件树下面时，任意一次本地更新都有可能带着大片子组件一起跑。

这类页面经常会改成 Zustand 之类的外部 store。原因很直接：组件可以按 selector 订阅局部切片，渲染范围更容易收住。

---

## 替代方案与架构选型

### useState + 领域纯函数

很多页面根本不用一步到位改成 `useReducer`。
先把业务逻辑抽成纯函数，已经能解决大部分维护问题。

```tsx
function changePublishMode(
  state: StrategyState,
  mode: PublishMode
): StrategyState {
  return {
    ...state,
    base: {
      ...state.base,
      publishMode: mode,
      publishAt: mode === 'manual' ? null : state.base.publishAt,
    },
    dirty: true,
  }
}

const [state, setState] = useState(initialState)

function handlePublishModeChange(mode: PublishMode) {
  setState((prev) => changePublishMode(prev, mode))
}
```

这一步已经把逻辑从组件里抽走了。

### 自定义 Hook

状态还局限在单页里，但动作已经比较稳定时，可以先封成 Hook。

```tsx
function useStrategyEditor(initialState: StrategyState) {
  const [state, setState] = useState(initialState)

  const changeName = (name: string) => {
    setState((prev) => ({
      ...prev,
      base: { ...prev.base, name },
      dirty: true,
    }))
  }

  const toggleChannelAction = (channel: Channel) => {
    setState((prev) => toggleChannel(prev, channel))
  }

  return {
    state,
    changeName,
    toggleChannelAction,
  }
}
```

页面拿到的是一组动作，不是散落的 setter。

### Zustand

页面已经接近一个小型应用时，Zustand 会更合适。典型信号包括：

* 多个区域共享同一份状态
* 很多子组件只关心一小块数据
* 父组件太大，任意一次更新都带着一片树重渲染

这时局部订阅的收益会很明显。

```tsx
const useStrategyStore = create<{
  channels: Record<Channel, boolean>
  toggleChannel: (channel: Channel) => void
}>((set) => ({
  channels: { app: true, sms: false, wechat: false },
  toggleChannel: (channel) =>
    set((state) => ({
      channels: {
        ...state.channels,
        [channel]: !state.channels[channel],
      },
    })),
}))

function ChannelPanel() {
  const channels = useStrategyStore((s) => s.channels)
  const toggleChannel = useStrategyStore((s) => s.toggleChannel)

  return (
    <div>
      <button onClick={() => toggleChannel('sms')}>
        短信：{channels.sms ? '开启' : '关闭'}
      </button>
    </div>
  )
}
```

### 一套实用的判断顺序

更稳的顺序是：

先抽纯函数。
页面内联动增多后，再考虑 `useReducer`。
渲染范围大、局部订阅需求明确时，再考虑 Zustand。

这个顺序更贴近真实项目的演进过程。

---

## 渐进式重构

### 第一阶段：面条代码

```tsx
function handlePublishModeChange(mode: PublishMode) {
  setForm((prev) => {
    const next = {
      ...prev,
      publishMode: mode,
      publishAt: mode === 'manual' ? null : prev.publishAt,
    }

    if (mode === 'scheduled' && !next.publishAt) {
      setErrors((old) => ({
        ...old,
        publishAt: '定时发布需要填写发布时间',
      }))
    }

    return next
  })
}
```

症状很明显：

* 一个 handler 里同时处理状态迁移和校验
* `setForm` 里嵌 `setErrors`
* 同类逻辑会复制到保存、发布、切换配置等多个入口

### 第二阶段：先抽纯函数

```tsx
function changePublishMode(
  state: StrategyState,
  mode: PublishMode
): StrategyState {
  return {
    ...state,
    base: {
      ...state.base,
      publishMode: mode,
      publishAt: mode === 'manual' ? null : state.base.publishAt,
    },
    dirty: true,
  }
}

const [state, setState] = useState(initialState)

function handlePublishModeChange(mode: PublishMode) {
  setState((prev) => changePublishMode(prev, mode))
}
```

做到这里，组件层已经轻了很多。很多页面其实停在这一步就够用。

### 第三阶段：动作越来越多，再切 useReducer

```tsx
type StrategyAction =
  | { type: 'base/publishModeChanged'; payload: PublishMode }
  | { type: 'channel/toggled'; payload: Channel }
  | { type: 'audience/added'; payload: AudienceCondition }

function handlePublishModeChange(mode: PublishMode) {
  dispatch({ type: 'base/publishModeChanged', payload: mode })
}
```

这一层的收益在于：

* 每个动作都有统一命名
* 状态迁移入口收口
* reducer 可以做穷举检查
* 逻辑继续增长时更容易维护

前提一直没变：先有纯函数，再谈 reducer。

---

## 面试中的典型问题

### Reducer 里能不能发异步请求

技术上能写，工程上不建议。

Reducer 的职责是根据当前 state 和 action 返回新 state。请求、埋点、跳转这类副作用放进去之后，状态迁移和外部行为会耦合在一起。调试、测试、复用都会变差。

可以直接拿上面的策略发布流程举例。`handlePublish` 负责发请求：

```tsx
async function handlePublish() {
  const errors = validateStrategy(state)
  dispatch({ type: 'validation/performed', payload: errors })

  if (Object.keys(errors).length > 0) {
    return
  }

  dispatch({ type: 'publish/started' })

  try {
    await publishStrategy(state)
    dispatch({ type: 'publish/succeeded' })
  } catch {
    dispatch({ type: 'publish/failed', payload: '发布失败，请稍后重试' })
  }
}
```

这段代码里，异步请求和同步状态迁移的边界很清楚。

### useReducer 和 useState 性能有区别吗

讨论这个问题时，先区分结构收益和渲染成本。

`useReducer` 的收益主要体现在结构上：逻辑集中、动作统一、迁移路径清楚。
它不会因为名字换成了 reducer，就自动变成局部订阅模型。

如果状态挂在一个大父组件上，`useState` 和 `useReducer` 都会让这个父组件重新 render。页面卡顿更多是组件拆分、状态边界、派生状态设计和 props 引用的问题。

可以继续用策略配置页举例。页面挂了：

* 基本信息区
* 规则列表区
* 额度配置区
* 发布预览区

任意一次 `dispatch` 都让整个父组件重新执行，这才是性能热点。
这类问题通常靠组件拆分、`React.memo`、外部 store 局部订阅来解。

### 复杂表单已经用了 useReducer，页面还是卡，先查什么

先查三件事。

第一，看有没有把派生状态存进 reducer。
例如“启用渠道数”“A/B 总和”“当前能否发布”这类值，完全可以从当前 state 算出来，不该再单独存一份。

第二，看是不是把整页状态都集中在一个大父组件里。
如果左中右三个区域都依赖同一个 reducer，任意一次 dispatch 都可能把整个页面带起来。

第三，看局部订阅需求是不是已经明确。
如果很多组件只关心一小块状态，外部 store 往往比单点 reducer 更合适。

### 为什么要加 never 穷举检查

可以看一个很具体的例子。

今天你新增了一个 action：

```tsx
type StrategyAction =
  | { type: 'channel/toggled'; payload: Channel }
  | { type: 'abTest/reset' }
```

如果 reducer 里忘了补 `'abTest/reset'`，没有穷举检查时，这个遗漏要到运行时才暴露。
加上：

```tsx
default: {
  const _exhaustive: never = action
  return state
}
```

TypeScript 会在编译阶段直接提示这个分支没处理掉。
这对动作越来越多的 reducer 很有价值。

---

## 结尾

`useReducer` 管的是一段复杂的本地编辑态。它适合联动规则较多、状态迁移路径需要收口的页面。

写这类页面时，更重要的是这几个顺序：

* 先区分原始业务状态和派生结果
* 先把业务逻辑抽成纯函数
* 再决定容器是 `useState`、`useReducer` 还是 Zustand

顺序对了，代码会稳很多。后面要拆 Hook、拆 Store、做性能优化，也都会轻松不少。
