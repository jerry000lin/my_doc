# Vue to React：核心机制与底层映射对比

## 1. 状态批处理、渲染快照与闭包失效

Vue 的组件状态通常表现为一组持续存活的响应式对象，底层通过响应式系统跟踪读写；React 函数组件则遵循更强的“渲染快照”语义：触发更新后，React 会再次调用组件函数计算下一帧 UI，而不是在当前调用栈里直接改写当前这次渲染拿到的变量。`setState` / `setXxx` 做的是“提交一次更新请求”，React 会在批处理后进入下一次 render，并按队列顺序计算新状态；当新值与旧值经 `Object.is` 比较后相同，React 可以跳过这次更新结果。这里的核心区别不是语法，而是运行模型：Vue 更像“同一份响应式对象持续变化”，React 更像“每次渲染生成一份新的读取视图”。([Vue.js][1])

因此，React 中最容易误判的一点是：当前 render 读到的 `state` 只是这一帧的快照。凡是“基于旧值继续推导新值”的更新，尤其是连续更新、批处理或异步回调场景，通常都应优先交给 updater function，让 React 在处理状态队列时把最新待处理值传进去，而不是在当前闭包里直接拿旧变量做计算。([React][2])

`useEffect`、事件处理函数、`setTimeout`、`setInterval`、Promise 回调本质上都依赖 JavaScript 闭包。所谓 stale closure，并不是 `useEffect` 特有问题，而是“某个回调继续引用了创建它的那次 render 的变量”。只要回调的生命周期长于那次 render，它读取到的就可能是旧快照。下面这段代码的问题不在于 `setInterval`，而在于定时器回调始终拿着挂载那一帧的 `count`：([React][3])

```jsx
function Counter() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setCount(count + 1);
    }, 1000);

    return () => clearInterval(id);
  }, []);

  return <span>{count}</span>;
}
```

修正方式不是“强行让闭包拿到最新值”，而是把“如何从旧值得到新值”写成 updater function：

```jsx
function Counter() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setCount(prev => prev + 1);
    }, 1000);

    return () => clearInterval(id);
  }, []);

  return <span>{count}</span>;
}
```

这里还有一个经常和闭包问题绑在一起的点：`useEffect` 的 cleanup 不是挂在“整个组件函数”上，而是挂在“上一轮已经生效的那次 effect 执行”上。依赖变化后，React 会先用旧值执行上一轮 cleanup，再用新值执行下一轮 setup；组件卸载时，再执行最后一轮 cleanup。也就是说，cleanup 更接近“上一轮同步任务的收尾”，不是“组件函数级别的统一析构”。这也是为什么定时器只在当前 effect 内部使用时，通常用局部变量就够了，不必为了清理再额外放进 `ref`。([React][3])

## 2. 组件通信、函数 props 与单向数据流

Vue 常见的是父组件通过 `props` 向下传值，子组件通过事件向上通知。React 仍然是同一件事，只是不额外提供模板层事件派发语法：状态放在拥有它的组件中，向下传数据，向下传函数，子组件在交互时调用该函数，把更新请求交回给父组件。React 官方把这套模式称为 one-way data flow 和 lifting state up。([React][4])

```jsx
function Child({ onSubmit }) {
  const [value, setValue] = useState('');

  return (
    <>
      <input value={value} onChange={e => setValue(e.target.value)} />
      <button onClick={() => onSubmit(value)}>提交</button>
    </>
  );
}

function Parent() {
  const [message, setMessage] = useState('');

  return (
    <>
      <Child onSubmit={setMessage} />
      <p>{message}</p>
    </>
  );
}
```

这里的 `onSubmit` 只是一个普通函数引用。执行动作发生在子组件里，状态归属和真正的调度入口仍然在父组件。这样做的直接收益是：状态边界清晰，更新入口集中，数据流向始终单向，排查链路更短。跨层级传递过深时，再考虑 Context 或状态库；但无论是否引入工具，React 的核心模型都没有变。([React][4])

## 3. 状态不可变性、引用比较与更新边界

Vue 的响应式系统可以感知对象属性的变更；React 的状态更新则要求你把对象和数组当成不可变值来处理。官方文档的表述很直接：当状态里存的是对象或数组，不应直接修改原对象，而应创建一个新对象或新数组再交给 state setter。否则，新旧值可能在引用上仍然相同，React 会把它视为“没有变化”或失去明确的变化边界。([React][5])

```jsx
function Profile() {
  const [user, setUser] = useState({ name: 'Alice', age: 20 });

  const update = () => {
    user.age = 21;
    setUser(user);
  };

  return <button onClick={update}>{user.age}</button>;
}
```

符合 React 约束的写法是返回新引用：

```jsx
function Profile() {
  const [user, setUser] = useState({ name: 'Alice', age: 20 });

  const update = () => {
    setUser(prev => ({ ...prev, age: 21 }));
  };

  return <button onClick={update}>{user.age}</button>;
}
```

扩展运算符、`map`、`filter`、`slice` 这些写法的共同目标不是“写得更函数式”，而是明确创建新引用，让 React 能稳定判断状态边界。这个规则不仅影响 `useState`，也会影响 `memo`、`useMemo`、Context value 比较以及外部 store 的订阅优化。React 的 Context 也是用 `Object.is` 比较前后 `value`，只要 Provider 的 `value` 变了，所有读取这个 Context 的组件都会收到新值并重新渲染。([React][16])

## 4. JSX 结构表达：条件、列表与 Key

Vue 把条件渲染和列表渲染放在模板指令层；React 直接把这件事交给 JavaScript 表达式。条件渲染没有额外模板语法，`if`、`&&`、三元表达式、返回 `null` 都是标准写法。`null` 表示这次 render 不把这段子树放进 UI 树；`style={{ display: 'none' }}` 则只是让节点继续存在但变为不可见。前者影响挂载、卸载与局部状态归属，后者只影响显示。([React][6])

```jsx
function Panel({ ready, visible }) {
  return ready ? (
    <section style={{ display: visible ? 'block' : 'none' }}>
      Content
    </section>
  ) : null;
}
```

列表渲染同样没有模板层特权，直接使用 `map()` 生成一组节点。真正关键的不是 `map`，而是 `key`。React 用位置、类型和 `key` 共同判断一个节点在前后两次渲染里是否还是“同一个节点”；稳定的 `key` 能帮助 React 正确保留局部状态，不稳定的 `key` 会让节点身份漂移。官方文档明确建议优先使用数据库 ID 或稳定唯一标识，而不是把数组索引当作默认方案。([React][7])

```jsx
function UserList({ users }) {
  return (
    <ul>
      {users.map(user => (
        <li key={user.id}>{user.name}</li>
      ))}
    </ul>
  );
}
```

当列表只追加、不重排、不删除时，索引 key 偶尔不会立刻出问题；一旦发生插入、删除或排序，旧状态就可能被错误复用到新位置。输入框内容错位、动画状态串位、局部 effect 归属错乱，本质上都属于“节点身份判定错了”。([React][7])

## 5. 生命周期映射：组件生命周期与 Effect 生命周期不是一回事

Vue 组件实例有比较明确的实例生命周期；React 函数组件没有把“生命周期钩子”作为一等接口继续保留，而是把函数组件的执行和 effect 的同步过程拆开理解。React 的 render phase 本质上就是再次调用组件函数来计算 UI；effect 则发生在 commit 之后，用来和 React 之外的系统做同步。Vue 的 `setup()` 是组件实例的入口，而 React 函数组件的函数体会在每次 render 时重新执行，因此它只能和 `setup()` 做粗略类比，不能直接等同于 `created`。([React][8])

下表可以作为迁移时的心智映射，但只能按“用途近似”理解，不能按“同名生命周期一一对应”理解：([Vue.js][9])

| Vue                                                 | React 中更接近的写法                             | 说明                                     |
| --------------------------------------------------- | ----------------------------------------- | -------------------------------------- |
| `setup()`                                           | 函数组件函数体、`useState` 懒初始化、`useRef` 初始化      | React 函数组件函数体会在每次 render 时重跑，不是一次性创建钩子 |
| `onMounted`                                         | `useEffect(fn, [])`                       | 首次 commit 后执行                          |
| `onUpdated`                                         | `useEffect(fn)` 或 `useEffect(fn, [deps])` | React 没有单独的“更新钩子”，而是按依赖重新同步            |
| `onBeforeUnmount` / `onUnmounted`                   | `useEffect` 返回的 cleanup                   | 只在 `[]` effect 中，cleanup 才近似只发生在卸载时    |
| `watch(source, cb)`                                 | `useEffect(fn, [dep])`                    | 都能对变化做副作用处理，但 Vue `watch` 基于显式 source，回调还能拿到新旧值 |
| `watch(..., { immediate: true })`                   | `useEffect(fn, [dep])`                    | 都会在初次建立同步时先执行一次，但 React 不直接提供 `oldValue`      |
| `watchEffect()`                                     | `useEffect(fn)`                           | 都会先执行再随依赖变化重跑，但 Vue 会自动追踪依赖，React 需要显式声明依赖 |

React 官方对 effect 的定义很明确：组件有 mount、update、unmount；effect 只有“开始同步”和“停止同步”两个动作，而且这个过程会随着依赖变化反复发生。因此，`useEffect` 的 cleanup 不应被理解为单纯的 `onUnmount`。只要依赖发生变化，React 就会先执行上一轮 cleanup，再执行下一轮 effect。只有 `[]` 依赖的 effect，cleanup 才近似等于卸载清理。这个模型其实和 Vue 的 watcher invalidation 更接近：Vue 的 `watch` / `watchEffect` 也提供 cleanup 机制，在 watcher 即将重新执行时做失效清理。([React][10])

这也是前面那段关于 cleanup 的关键结论：cleanup 绑定的是“上一轮已提交 effect 的闭包”，不是“整个组件函数”。开发环境下如果启用了 `StrictMode`，React 还会额外执行一次 setup + cleanup 周期来帮助发现副作用问题，所以你会看到比生产环境更多的一次 effect 往返。([React][3])

另外，React 没有对应 Vue `onBeforeMount`、`onBeforeUpdate` 的常规替代物。原因不是功能缺失，而是 React 要求 render phase 保持纯净；如果只是根据当前 props/state 计算派生值，应直接写在 render 里，必要时再用 `useMemo` 缓存，而不是先 render 再进 effect 回填一次状态。官方把这类场景明确归为 “You Might Not Need an Effect”。([React][11])

## 6. 现代 React 架构：把服务端状态、客户端状态与副作用拆开

现代 React 的主线不是“尽量多写 Hooks”，而是更严格地区分三类东西：纯渲染计算、客户端本地交互状态、需要和外部系统同步的副作用。React 官方对 `useEffect` 的定位一直很克制：它是 escape hatch，用来同步计时器、事件订阅、网络、浏览器 API、第三方库，而不是默认的数据流中枢。凡是不涉及外部系统的派生逻辑，优先留在 render、事件处理或 memo 里。([React][11])

服务端状态这条线，TanStack Query 解决的不是“帮你发请求”这么简单，而是把异步数据从组件局部状态里拿出来，交给 query cache 管理。它基于 `queryKey` 管理缓存；stale 数据会按配置触发后台重新获取；query function 会收到 `AbortSignal`，当查询过期或失活时这个 signal 会被置为 aborted，而当你在 `queryFn` 中消费它时，请求就可以被取消；结构共享默认开启，未变化的数据引用会被保留，从而减少不必要的重新渲染。这个模型比 `useEffect + useState + loading/error` 更适合长期维护的服务端状态。([TanStack][12])

客户端跨组件 UI 状态这条线，Zustand 的价值不在于“绕过 React”，而在于把 store 放到 React 组件树之外，再让组件按 selector 订阅自己关心的切片。Zustand 文档明确推荐 selector 作为订阅入口，并提供 `useShallow` 等工具来减少无意义的重渲染；React 本身也为这种外部 store 集成提供了 `useSyncExternalStore`。相比之下，Context 的 `value` 变化会让所有消费这个 Context 的后代收到更新，因此当状态频繁变化、消费面较广时，外部 store 往往更容易收缩更新范围。这里的准确表述是“缩小订阅面和重渲染范围”，不是“完全绕过 React 渲染”。([zustand.docs.pmnd.rs][13])

首屏数据获取与运行时环境拆分这条线，Next.js App Router 已把 React Server Components 纳入默认架构：layouts 和 pages 默认就是 Server Components，可以在服务端获取数据、缓存结果并流式发送到客户端；只有确实需要交互和浏览器 API 时，再显式进入 Client Components。这意味着一部分原本写在客户端 effect 里的数据获取逻辑，可以前移到服务端完成。([Next.js][14])

### 防抖案例：组件局部 effect 与外部状态拆分

防抖是最容易把这些边界混在一起的场景。组件局部防抖时，传统 `useEffect` 写法完全成立，而且实现并不复杂：

```tsx
import { useEffect, useState } from 'react';

export function TraditionalSearch() {
  const [keyword, setKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedKeyword(keyword);
    }, 500);

    return () => {
      clearTimeout(timer);
    };
  }, [keyword]);

  return <input value={keyword} onChange={e => setKeyword(e.target.value)} />;
}
```

这段代码的关键不是“用 effect 模拟生命周期”，而是“用 effect 同步一个外部计时器”。同时，cleanup 的理解要和前文保持一致：这里不需要在 effect 开头再额外 `clearTimeout` 一次，因为 React 在依赖变化后本来就会先执行上一轮 cleanup，再执行这一轮 setup。`timer` 也不需要放进 `ref`，因为它只在当前这次 effect 执行及其 cleanup 中使用；只有当你要在 effect 外部主动取消它时，`ref` 才有必要。([React][3])

当防抖不再只是当前组件自己的本地节流，而是要和跨组件共享输入状态、服务端缓存、请求取消、结果复用一起协同时，拆分边界会更清晰：用 Zustand 维护输入控制流，用 TanStack Query 管服务端状态。

```tsx
import { create } from 'zustand';
import { debounce } from 'lodash';
import { useQuery } from '@tanstack/react-query';

const useSearchStore = create((set) => {
  const debouncedSet = debounce((value) => {
    set({ debouncedKeyword: value });
  }, 500);

  return {
    keyword: '',
    debouncedKeyword: '',
    setKeyword: (value) => {
      set({ keyword: value });
      debouncedSet(value);
    },
  };
});

export function ModernSearch() {
  const keyword = useSearchStore(state => state.keyword);
  const debouncedKeyword = useSearchStore(state => state.debouncedKeyword);
  const setKeyword = useSearchStore(state => state.setKeyword);

  useQuery({
    queryKey: ['search', debouncedKeyword],
    enabled: !!debouncedKeyword,
    queryFn: async ({ signal }) => {
      const res = await fetch(
        `/api/search?q=${encodeURIComponent(debouncedKeyword)}`,
        { signal }
      );
      return res.json();
    },
  });

  return <input value={keyword} onChange={e => setKeyword(e.target.value)} />;
}
```

这套写法的变化点有两个。第一，输入值和防抖值属于客户端控制流，它们不必绑定在某个组件的 effect 生命周期上；store 可以独立存在，组件只是订阅它。第二，真正的异步数据获取不再由组件自己手搓 `loading/error/cancel/cache`，而是交给 Query 通过 `queryKey`、缓存、取消和结构共享来管理。这样一来，React 组件重新回到“描述 UI + 订阅状态”的位置，防抖逻辑和服务端状态逻辑不再互相挤压。([zustand.docs.pmnd.rs][15])

最终应当形成的判断标准不是“`useEffect` 过时了”或“状态库一定更高级”，而是按职责选择位置：

* 纯渲染派生值：放在 render / `useMemo`
* 组件局部、短生命周期的外部同步：`useEffect`
* 跨组件共享的客户端 UI 状态：Context 或外部 store
* 服务端异步数据、缓存、取消、复用：TanStack Query
* 可前移到服务端的数据获取与首屏拼装：Server Components / App Router

React 的工程化重点，不是把所有逻辑都塞进组件，而是把不同性质的状态和副作用放回各自最合适的位置。([React][11])

[1]: https://vuejs.org/guide/extras/reactivity-in-depth?utm_source=chatgpt.com "Reactivity in Depth"
[2]: https://react.dev/reference/react/useState?utm_source=chatgpt.com "useState"
[3]: https://react.dev/reference/react/useEffect "useEffect – React"
[4]: https://react.dev/learn/sharing-state-between-components?utm_source=chatgpt.com "Sharing State Between Components"
[5]: https://react.dev/learn/updating-objects-in-state "Updating Objects in State – React"
[6]: https://react.dev/learn/conditional-rendering?utm_source=chatgpt.com "Conditional Rendering"
[7]: https://react.dev/learn/rendering-lists "Rendering Lists – React"
[8]: https://react.dev/learn/render-and-commit?utm_source=chatgpt.com "Render and Commit"
[9]: https://vuejs.org/api/composition-api-lifecycle.html?utm_source=chatgpt.com "Composition API: Lifecycle Hooks"
[10]: https://react.dev/learn/lifecycle-of-reactive-effects "Lifecycle of Reactive Effects – React"
[11]: https://react.dev/learn/you-might-not-need-an-effect?utm_source=chatgpt.com "You Might Not Need an Effect"
[12]: https://tanstack.com/query/latest/docs/framework/react/guides/query-keys?utm_source=chatgpt.com "Query Keys | TanStack Query React Docs"
[13]: https://zustand.docs.pmnd.rs/learn/guides/prevent-rerenders-with-use-shallow?utm_source=chatgpt.com "Prevent rerenders with useShallow - Zustand"
[14]: https://nextjs.org/docs/app "Next.js Docs: App Router | Next.js"
[15]: https://zustand.docs.pmnd.rs/?utm_source=chatgpt.com "Zustand: Introduction"
[16]: https://react.dev/reference/react/useContext "useContext – React"
