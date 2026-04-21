# React 自定义 Hook 实践：为什么这类场景必须使用 useEffect

## 什么是自定义 Hook

自定义 Hook 本质上不是一个特殊语法，它只是一个普通函数，只不过这个函数内部调用了 React Hook，并把一段可复用的状态逻辑封装起来。

在工程里，自定义 Hook 常见的用途有三类：

- 复用一段本地交互状态
- 复用一段和外部系统同步的逻辑
- 把组件里重复出现的状态组织方式抽离出去

对应到这个案例文件 [react_custom_hook_case.tsx](./examples/react_custom_hook_case.tsx)，它讨论的不是“怎么少写代码”，而是一个更具体的问题：

- 当筛选条件保存在 `localStorage` 里
- 当 `storageKey` 会随着业务模块切换而变化
- Hook 需要同时处理“读取”和“写回”

这时自定义 Hook 的关键已经不是状态声明，而是副作用边界。

## 这个案例要解决什么问题

案例里的筛选条件状态如下：

```tsx
type FilterState = {
  keyword: string;
  status: "all" | "running" | "success" | "failed";
  owner: string;
};
```

页面会在不同业务模块之间切换，比如：

- 风控模块使用 `BUGGY_FILTERS_risk`
- 营销模块使用 `BUGGY_FILTERS_marketing`

同一个面板在切换模块时，`storageKey` 会变化。于是 Hook 必须同时满足两件事：

1. `key` 变化时，重新从新的 `localStorage key` 读取数据
2. 当前状态变化时，把最新状态写回当前 `localStorage key`

如果只做其中一半，就会出现状态串写、旧值污染新 key、界面显示与存储不一致的问题。

## React 和 Vue 在这里为什么不一样

这是理解自定义 Hook 的核心前提。

### Vue 的思路

在 Vue 里，组合式函数通常建立在响应式系统之上。你可以把状态放进 `ref` 或 `reactive`，再通过：

- `watch`
- `watchEffect`
- `computed`
- 生命周期钩子

去组织依赖关系。

Vue 的运行模型更接近“这份响应式对象一直存在，依赖变化时，框架帮你触发关联逻辑”。

### React 的思路

React 函数组件和自定义 Hook 都建立在“渲染是纯计算”这个前提上。

React 在一次 render 中做的事情应该是：

- 读取当前 props 和 state
- 计算这次界面该长什么样
- 返回 JSX

它不应该在 render 过程中顺手去做下面这些动作：

- 改 `localStorage`
- 发请求
- 订阅事件
- 操作 DOM
- 启动定时器

原因不是语法限制，而是 React 的运行模型决定了 render 可能被重复执行、提前中断、开发模式额外重放。凡是和 React 外部世界发生交互的动作，都必须放在 effect 阶段。

所以这类问题的准确说法不是“React 写自定义 Hook 一定都要 `useEffect`”，而是：

**只要这个自定义 Hook 要和外部系统同步，在 React 里就必须显式使用 `useEffect` 管理副作用。**

这正是它和 Vue 组合式函数最容易混淆的地方。Vue 开发者很容易把“响应式依赖变化后自动联动”的心智直接带到 React 里，结果把副作用写进 Hook 函数体、`useState` 初始化函数，或者事件回调里，最后出现状态边界错乱。

## 为什么这个案例里必须用 useEffect

这个案例不是纯计算 Hook，而是一个“本地状态 + 外部存储同步”Hook。

`localStorage` 不属于 React 状态树，它是浏览器外部系统。只要 Hook 要负责和它同步，就必须把同步动作放进 `useEffect`。

这里至少有两段 effect 职责：

### 1. key 变化时重读

当 `storageKey` 从 `risk` 切到 `marketing`，当前内存里的 `state` 还是旧值。

如果没有一段 effect 在 `key` 变化后重新执行读取逻辑，组件就会出现两个问题：

- 画面还是旧模块的数据
- 后续写回可能把旧模块状态写进新模块 key

### 2. state 变化时写回

用户修改筛选条件后，新的状态要持久化到 `localStorage`。

这同样不是 render 逻辑，而是“React 状态变化后，同步到浏览器存储”的副作用。

因此它必须写成：

```tsx
useEffect(() => {
  writeStorage(key, state);
}, [key, state]);
```

重点不在“语法上能不能写到别处”，而在“只有 effect 阶段才是 React 允许你做外部同步的地方”。

## 案例里的四种写法分别说明了什么

### 1. `useBuggyLocalStorage`

这版的问题不是不能运行，而是职责不完整。

它把读取逻辑写进了 `useState` 初始化函数：

```tsx
const [state, setState] = useState<T>(() => {
  const storedValue = localStorage.getItem(key);
  return storedValue ? JSON.parse(storedValue) : defaultValue;
});
```

这个初始化函数只在首次挂载时运行一次。`key` 后续变化时，它不会重新读取。

因此这版的问题是：

- 初次挂载能拿到值
- 后续切换 key，状态不会自动切换
- 继续编辑时，逻辑上下文已经变成新 key，但内存还是旧 state

这类写法在 Vue 开发者迁移到 React 时很常见，因为直觉上会觉得“依赖变了就该重新取一次”，但 React 的 `useState` 初始化根本不是 watcher。

### 2. `usePureImperativeLocalStorage`

这版表面上没用 `useEffect`，但它成立的前提非常苛刻：

```tsx
<PureImperativePanel
  key={storageKey}
  storageKey={storageKey}
  code={PURE_IMPERATIVE_CODE}
/>
```

这里真正起作用的不是 Hook 本身，而是调用方人为给组件加了 `key`，强制组件在 `storageKey` 变化时整棵重挂载。

重挂载后：

- `useState` 初始化重新执行
- Hook 重新从新 key 读取数据

这说明什么？

- 这不是 Hook 自己处理了 key 切换
- 而是调用方通过重挂载规避了 Hook 的同步责任

这个方案可以用，但边界非常明确：

- 适合临时演示或明确接受重挂载语义的页面
- 不适合做成通用可复用 Hook
- 一旦调用方忘记补 `key`，Hook 就立刻失效

从工程设计上看，这不算一个完整的抽象，因为它把关键约束泄漏给了组件调用方。

## 3. `useNaiveEffectLocalStorage`

这版已经意识到要用 `useEffect` 写回：

```tsx
useEffect(() => {
  writeStorage(key, state);
}, [key, state]);
```

但它仍然是错的，因为它只做了“写回”，没有做“key 变化后的重读”。

于是流程会变成：

1. 当前内存里还是旧模块 state
2. `key` 切到新模块
3. effect 触发，把旧 state 写进新 key

这版最能说明一个工程原则：

**自定义 Hook 里用了 `useEffect`，不代表副作用设计就正确。**

关键不是有没有 effect，而是 effect 的职责是否完整、依赖是否对应真实的数据流。

### 4. `useCompleteEffectLocalStorage`

这一版才是完整设计。

它把同步动作拆成两段：

```tsx
useEffect(() => {
  if (currentKeyRef.current !== key) {
    currentKeyRef.current = key;
    skipNextWriteRef.current = true;
    setState(readStorage(key, defaultValue));
  }
}, [key, defaultValue]);

useEffect(() => {
  if (skipNextWriteRef.current) {
    skipNextWriteRef.current = false;
    return;
  }

  writeStorage(key, state);
}, [key, state]);
```

它解决了三个问题：

1. `key` 变化后先重读新值
2. `state` 变化后再写回当前 key
3. 切 key 之后跳过第一次写回，避免旧值覆盖新值

这才是 React 自定义 Hook 里 effect 的正确使用方式：把副作用按职责拆开，而不是把所有同步动作堆进一个 `useEffect`。

## 设计这类自定义 Hook 的方法

写 React 自定义 Hook，先不要急着写代码，先把边界画出来。

### 第一步：先分清哪些是 React 内部状态，哪些是外部系统

在这个案例里：

- `state` 是 React 内部状态
- `localStorage` 是外部系统
- `key` 是同步边界

只要你识别出“有外部系统”，基本就可以判断这不是纯 `useState` 问题，而是 effect 问题。

### 第二步：拆分读取和写回

很多人第一次写这类 Hook，喜欢把“读”和“写”放进一个 effect。

问题在于这两个动作的触发条件不同：

- 重读由 `key` 变化触发
- 写回由 `state` 变化触发

触发条件不同，就应该拆成不同 effect。这样依赖数组才对应真实数据流。

### 第三步：考虑切换瞬间的中间态

切换 `key` 不是一个静态赋值，而是一个过程：

1. 旧 state 仍在内存中
2. 新 key 已经生效
3. 新数据尚未读回

很多 bug 就发生在这个短暂窗口里。

因此通用设计问题应该问成：

- 切 key 后，先读还是先写
- 第一次写回要不要跳过
- 旧 state 能不能直接复用
- 默认值变化时要不要重新初始化

这类问题如果不先想清楚，代码通常会“能跑，但不稳定”。

## 什么时候不需要 useEffect

这里必须把边界说清楚，否则很容易把规则说死。

不是所有 React 自定义 Hook 都要 `useEffect`。

下面这些 Hook 就可以不需要：

- 只做状态组合的 Hook
- 只做纯派生计算的 Hook
- 只包装 `useState` / `useReducer` 事件分发的 Hook
- 只返回若干回调函数和计算值的 Hook

例如：

```tsx
function useFilterForm(initialKeyword = "") {
  const [keyword, setKeyword] = useState(initialKeyword);
  const [status, setStatus] = useState<"all" | "running">("all");

  const isEmpty = keyword === "" && status === "all";

  function reset() {
    setKeyword(initialKeyword);
    setStatus("all");
  }

  return {
    keyword,
    status,
    isEmpty,
    setKeyword,
    setStatus,
    reset,
  };
}
```

这个 Hook 没有和外部系统同步，它只是组织组件内部状态，所以不需要 `useEffect`。

因此更准确的判断标准是：

- 纯状态组织，不需要 `useEffect`
- 涉及副作用同步，必须用 `useEffect`

## Vue 开发者迁移到 React 时最容易犯的错误

### 错误一：把 `useState` 初始化函数当成响应式重算入口

它只在首次挂载执行一次，后续依赖变化不会重新运行。

### 错误二：把副作用写进 Hook 函数体

Hook 函数体属于 render 过程，应该保持纯净。直接在里面操作 `localStorage`、请求、DOM，都属于越界。

### 错误三：用一个 effect 包办所有同步动作

这会让依赖数组失真，后期很难判断是哪一个依赖触发了哪一段行为。

### 错误四：以为“能跑”就说明 Hook 抽象成立

像案例里的“靠组件 `key` 重挂载”方案，本质上是把正确性转嫁给调用方，不是真正自洽的 Hook 设计。

## 这类 Hook 的替代方案

### 方案一：让调用方通过 `key` 强制重挂载

优点：

- 实现最简单
- 容易演示

成本：

- 正确性依赖调用方
- 组件局部状态会整体丢失
- 不适合通用封装

### 方案二：在 Hook 内部显式用 `useEffect` 管读取和写回

优点：

- 责任边界完整
- 调用方负担最小
- 更适合沉淀为公共 Hook

成本：

- 需要仔细处理依赖和切换瞬间
- 需要考虑首次写回、重复写回和默认值变化

### 方案三：不要让 Hook 直接碰 `localStorage`，改由外层状态管理统一持久化

适合场景：

- 多页面共享筛选条件
- 持久化策略不止 `localStorage`
- 还要接入 URL、服务端草稿、权限控制

这时可以把持久化下沉到：

- 全局 store
- 路由层
- 服务层

自定义 Hook 只负责订阅和分发。

## 实际工程建议

如果你在 React 里写自定义 Hook，先问自己三个问题：

1. 这个 Hook 只是复用状态组织，还是要同步外部系统
2. 如果依赖变化，哪些值应该重读，哪些值应该写回
3. 正确性是 Hook 自己保证，还是偷偷依赖调用方约束

对这个案例，推荐结论很明确：

- 如果要做成可复用 Hook，应该采用 `useCompleteEffectLocalStorage`
- 如果只是一次性 demo，可以接受 `key` 重挂载方案
- 不要使用只初始化一次或只负责写回的半成品实现

## 复习问题

### 问题一

为什么 `useState(() => readStorage(key))` 不能在 `key` 变化时自动重新读取？

因为这个初始化函数只在首次挂载执行，不是响应式监听器。

### 问题二

为什么 `localStorage` 的读写不应该直接写在 Hook 函数体里？

因为 Hook 函数体属于 render 阶段，render 应保持纯净；`localStorage` 读写属于和外部系统同步的副作用。

### 问题三

为什么“只写回不重读”的 effect 仍然是错误设计？

因为它没有覆盖完整数据流。`key` 变化后，旧 state 会在新 key 上被错误写回。

### 问题四

什么情况下 React 自定义 Hook 可以不使用 `useEffect`？

当 Hook 只组织 React 内部状态或纯派生逻辑，不和外部系统发生同步时。

## 快速结论

这个案例最值得记住的不是某一段代码，而是一条边界规则：

在 React 里，自定义 Hook 不是 Vue 组合式函数的直接翻版。React 的 render 必须保持纯净。只要 Hook 要和 `localStorage`、请求、订阅、定时器、DOM 这类外部系统同步，就必须显式使用 `useEffect` 管理副作用。

这个案例里真正完整的实现只有一种：把“`key` 变化时重读”和“`state` 变化时写回”拆成两段 effect，并处理切换瞬间的覆盖问题。
