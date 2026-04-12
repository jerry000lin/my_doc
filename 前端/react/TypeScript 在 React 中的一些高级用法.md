# TypeScript 在 React 中的一些高级用法

本文整理三个在 React 项目里经常会用到的 TypeScript 高级能力：generics（泛型）、React 事件对象类型，以及 Utility Types（工具类型）。这几类能力本质上都在做同一件事：把类型约束沿着组件、Hook、props 和回调继续传下去。很多 React + TypeScript 项目的难点，也集中在这里。

React 官方 TypeScript 指南里提到，props 类型除了普通对象类型，也会用到联合类型，以及 creating types from types（从已有类型创建新类型）这类能力。放到真实代码里，最常见的落点就是下面三类场景。

## 高级用法一：generics（泛型）组件和泛型 Hook

TypeScript 里的 `T`、`K` 这类类型参数，通常用在：结构相同、具体类型不同的一段代码。放到 React 里，这类能力常见的落点就是泛型组件和泛型 Hook。

### 一个泛型组件案例

假设有如下需求：项目里有很多列表页，表格结构基本一致，都是列配置、行数据、行点击、单元格渲染这一套。变化的是每个页面的行数据类型，以及某些列的展示逻辑。希望表格组件能复用，同时在列渲染函数、行点击函数里保留具体业务类型，而不是退化成 `any`。

代码实现：

```tsx
import React from "react";

type TableColumn<T> = {
  key: string;
  title: string;
  width?: number;
  render: (row: T) => React.ReactNode;
};

function createColumn<T, K extends keyof T>(config: {
  key: K;
  title: string;
  width?: number;
  render?: (value: T[K], row: T) => React.ReactNode;
}): TableColumn<T> {
  return {
    key: String(config.key),
    title: config.title,
    width: config.width,
    render: (row) => {
      const value = row[config.key];
      return config.render ? config.render(value, row) : String(value);
    },
  };
}

interface DataTableProps<T> {
  rows: T[];
  rowKey: (row: T) => string;
  columns: Array<TableColumn<T>>;
  onRowClick?: (row: T) => void;
}

export function DataTable<T>(props: DataTableProps<T>) {
  const { rows, rowKey, columns, onRowClick } = props;

  return (
    <table>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key} style={{ width: column.width }}>
              {column.title}
            </th>
          ))}
        </tr>
      </thead>

      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)} onClick={() => onRowClick?.(row)}>
            {columns.map((column) => (
              <td key={column.key}>{column.render(row)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

业务侧类型和使用方式：

```tsx
type StrategyRow = {
  id: string;
  name: string;
  scene: "loan" | "fraud" | "review";
  status: "draft" | "enabled" | "disabled";
  updatedAt: string;
};

const rows: StrategyRow[] = [
  {
    id: "s_1",
    name: "准入A策略",
    scene: "loan",
    status: "enabled",
    updatedAt: "2026-04-12 10:00:00",
  },
];

const columns = [
  createColumn<StrategyRow, "name">({
    key: "name",
    title: "策略名称",
  }),
  createColumn<StrategyRow, "scene">({
    key: "scene",
    title: "场景",
    render: (value, row) => {
      // value 会被推断为 "loan" | "fraud" | "review"
      // row 会被推断为 StrategyRow
      const textMap: Record<StrategyRow["scene"], string> = {
        loan: "贷前",
        fraud: "反欺诈",
        review: "复核",
      };

      return `${textMap[value]} / ${row.name}`;
    },
  }),
  createColumn<StrategyRow, "status">({
    key: "status",
    title: "状态",
    render: (value) => {
      // value 会被推断为 "draft" | "enabled" | "disabled"
      const textMap: Record<StrategyRow["status"], string> = {
        draft: "草稿",
        enabled: "启用",
        disabled: "停用",
      };

      return textMap[value];
    },
  }),
  createColumn<StrategyRow, "updatedAt">({
    key: "updatedAt",
    title: "更新时间",
  }),
];

export function StrategyTableDemo() {
  return (
    <DataTable
      rows={rows}
      rowKey={(row) => row.id}
      columns={columns}
      onRowClick={(row) => {
        // row 会被推断为 StrategyRow
        console.log(row.scene);
        console.log(row.status);

        // 编辑器会提示 row.scene 只能是 "loan" | "fraud" | "review"
        // 下面这行会报类型错误
        // const bad: number = row.status;
      }}
    />
  );
}
```

这里的关键点不在 `DataTable<T>` 这一个写法本身，而在类型是怎么一路传下去的。

`DataTableProps<T>` 把 `rows`、`rowKey`、`columns`、`onRowClick` 绑在同一个 `T` 上。这样一来，只要调用方传入的是 `StrategyRow[]`，`onRowClick` 里的 `row` 就一定是 `StrategyRow`。
`createColumn<T, K extends keyof T>` 又把“列字段”和“字段值类型”绑在一起。这里的 `K` 是具体字段，比如 `"scene"`，那 `T[K]` 就会被推断成 `StrategyRow["scene"]`，也就是 `"loan" | "fraud" | "review"`。所以 `render` 里的 `value` 不会退化成宽泛的 `string`。

这一类写法适合放在表格、树、列表、选择器这类组件里。它们的共同点是：骨架稳定，数据类型会变化，回调里又需要把具体业务类型继续保留下去。

### 一个泛型 Hook 案例

假设有如下需求：多个列表页都需要维护查询条件、分页、loading、请求和刷新逻辑。页面之间的差异主要在于查询参数类型和返回列表项类型。希望把这部分状态流抽成一个 Hook，同时保留不同页面自己的类型信息。

代码实现：

```tsx
import { useCallback, useEffect, useRef, useState } from "react";

export interface PageQuery {
  page: number;
  pageSize: number;
}

export interface PageResult<T> {
  list: T[];
  total: number;
}

interface UsePagedQueryOptions<TQuery extends PageQuery, TItem> {
  initialQuery: TQuery;
  fetcher: (
    query: TQuery,
    signal: AbortSignal
  ) => Promise<PageResult<TItem>>;
}

export function usePagedQuery<TQuery extends PageQuery, TItem>(
  options: UsePagedQueryOptions<TQuery, TItem>
) {
  const { initialQuery, fetcher } = options;

  const [query, setQuery] = useState<TQuery>(initialQuery);
  const [data, setData] = useState<PageResult<TItem>>({
    list: [],
    total: 0,
  });
  const [loading, setLoading] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);

  const requestSeqRef = useRef(0);

  const patchQuery = useCallback((patch: Partial<TQuery>) => {
    setQuery((prev) => ({ ...prev, ...patch }));
  }, []);

  const reload = useCallback(() => {
    setReloadVersion((prev) => prev + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const currentSeq = ++requestSeqRef.current;

    setLoading(true);

    void fetcher(query, controller.signal)
      .then((result) => {
        if (currentSeq !== requestSeqRef.current) {
          return;
        }
        setData(result);
      })
      .finally(() => {
        if (currentSeq !== requestSeqRef.current) {
          return;
        }
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [query, reloadVersion, fetcher]);

  return {
    query,
    setQuery,
    patchQuery,
    reload,
    list: data.list,
    total: data.total,
    loading,
  };
}
```

业务侧类型和使用方式：

```tsx
type StrategyQuery = {
  keyword: string;
  scene?: "loan" | "fraud" | "review";
  status?: "draft" | "enabled" | "disabled";
  page: number;
  pageSize: number;
};

type StrategyRow = {
  id: string;
  name: string;
  scene: "loan" | "fraud" | "review";
  status: "draft" | "enabled" | "disabled";
  updatedAt: string;
};

async function fetchStrategyPage(
  query: StrategyQuery,
  signal: AbortSignal
): Promise<PageResult<StrategyRow>> {
  const response = await fetch("/api/strategy/page", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(query),
    signal,
  });

  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }

  return response.json() as Promise<PageResult<StrategyRow>>;
}

export function StrategyPage() {
  const { query, patchQuery, reload, list, total, loading } = usePagedQuery<
    StrategyQuery,
    StrategyRow
  >({
    initialQuery: {
      keyword: "",
      page: 1,
      pageSize: 20,
    },
    fetcher: fetchStrategyPage,
  });

  return (
    <section>
      <div>总数：{total}</div>
      <div>状态：{loading ? "加载中" : "空闲"}</div>

      <button
        onClick={() => {
          patchQuery({
            keyword: "黑名单命中",
            page: 1,
          });

          // patchQuery 的参数类型是 Partial<StrategyQuery>
          // 这里只能传 StrategyQuery 的一部分字段
          // 下面这行会报类型错误
          // patchQuery({ xxx: 1 });
        }}
      >
        更新查询条件
      </button>

      <button onClick={reload}>刷新</button>

      <div>
        {list.map((item) => {
          // item 会被推断为 StrategyRow
          return (
            <div key={item.id}>
              {item.name} / {item.scene} / {item.status}
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

将 `usePagedQuery` 抽成 Hook，可以把查询状态、分页、loading、刷新和请求更新链路统一下来；结合泛型，查询参数类型和返回结果类型都可以替换，页面里拿到的 `query`、`patchQuery`、`list` 仍然是精确类型。

---

## 高级用法二：React 事件对象类型

React 里常用的事件类型，通常有三种写法：参数类型、函数类型、从原生元素 props 中取类型。

### 常用写法对照

| 场景                    | 参数类型                                     | 函数类型                                            | 从原生元素 props 中取类型                                         |
| --------------------- | ---------------------------------------- | ----------------------------------------------- | -------------------------------------------------------- |
| input 的 `onChange`    | `React.ChangeEvent<HTMLInputElement>`    | `React.ChangeEventHandler<HTMLInputElement>`    | `React.ComponentPropsWithoutRef<"input">["onChange"]`    |
| textarea 的 `onChange` | `React.ChangeEvent<HTMLTextAreaElement>` | `React.ChangeEventHandler<HTMLTextAreaElement>` | `React.ComponentPropsWithoutRef<"textarea">["onChange"]` |
| select 的 `onChange`   | `React.ChangeEvent<HTMLSelectElement>`   | `React.ChangeEventHandler<HTMLSelectElement>`   | `React.ComponentPropsWithoutRef<"select">["onChange"]`   |
| button 的 `onClick`    | `React.MouseEvent<HTMLButtonElement>`    | `React.MouseEventHandler<HTMLButtonElement>`    | `React.ComponentPropsWithoutRef<"button">["onClick"]`    |
| form 的 `onSubmit`     | `React.FormEvent<HTMLFormElement>`       | `React.FormEventHandler<HTMLFormElement>`       | `React.ComponentPropsWithoutRef<"form">["onSubmit"]`     |
| input 的 `onKeyDown`   | `React.KeyboardEvent<HTMLInputElement>`  | `React.KeyboardEventHandler<HTMLInputElement>`  | `React.ComponentPropsWithoutRef<"input">["onKeyDown"]`   |
| input 的 `onBlur`      | `React.FocusEvent<HTMLInputElement>`     | `React.FocusEventHandler<HTMLInputElement>`     | `React.ComponentPropsWithoutRef<"input">["onBlur"]`      |
| div 的 `onDrop`        | `React.DragEvent<HTMLDivElement>`        | `React.DragEventHandler<HTMLDivElement>`        | `React.ComponentPropsWithoutRef<"div">["onDrop"]`        |

三种写法的区别如下：

* 参数类型：适合组件内部的普通处理函数
* 函数类型：适合写 handler 变量、props 类型
* 从原生元素 props 中取类型：适合封装接近原生语义的基础组件，避免手写一遍 DOM props

### 一个筛选区案例

```tsx
import React from "react";

type StrategyQuery = {
  keyword: string;
  scene?: "loan" | "fraud" | "review";
  page: number;
  pageSize: number;
};

interface FilterBarProps {
  query: StrategyQuery;
  onPatch: (patch: Partial<StrategyQuery>) => void;
  onSearch: () => void;
  onImport: (file: File) => void;
}

export function FilterBar(props: FilterBarProps) {
  const { query, onPatch, onSearch, onImport } = props;

  const handleKeywordChange: React.ChangeEventHandler<HTMLInputElement> = (
    event
  ) => {
    // event.currentTarget.value 会被推断为 string
    onPatch({
      keyword: event.currentTarget.value,
      page: 1,
    });
  };

  const handleSceneChange = (
    event: React.ChangeEvent<HTMLSelectElement>
  ) => {
    // event.currentTarget.value 会被推断为 string
    const value = event.currentTarget.value as StrategyQuery["scene"] | "";

    onPatch({
      scene: value || undefined,
      page: 1,
    });

    // 下面这行会报类型错误
    // onPatch({ scene: 1 });
  };

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    onSearch();
  };

  const handleFileChange: React.ComponentPropsWithoutRef<"input">["onChange"] =
    (event) => {
      const file = event.currentTarget.files?.[0];

      if (!file) {
        return;
      }

      // file 会被推断为 File
      onImport(file);

      event.currentTarget.value = "";
    };

  return (
    <form onSubmit={handleSubmit}>
      <input
        value={query.keyword}
        onChange={handleKeywordChange}
        placeholder="策略名称 / 策略ID"
      />

      <select value={query.scene ?? ""} onChange={handleSceneChange}>
        <option value="">全部场景</option>
        <option value="loan">贷前</option>
        <option value="fraud">反欺诈</option>
        <option value="review">复核</option>
      </select>

      <button type="submit">查询</button>

      <input type="file" accept=".json" onChange={handleFileChange} />
    </form>
  );
}
```

这里的核心不是记住 API 名字，而是让事件处理函数和真实元素对齐。输入框就拿到 `HTMLInputElement` 的事件，下拉框就拿到 `HTMLSelectElement` 的事件，文件上传就能安全访问 `files`。一旦写错，编辑器会先给出告警。

---

## 高级用法三：TypeScript 常用 Utility Types（工具类型）

TypeScript 常用的 Utility Types（工具类型）如下。

| 类型工具                                    | 常见用途         | React 中常见落点         |
| --------------------------------------- | ------------ | ------------------- |
| `Pick<T, K>`                            | 从大类型里挑出一部分字段 | 表格行类型、详情卡片、表单值      |
| `Omit<T, K>`                            | 从大类型里去掉一部分字段 | 封装按钮、输入框，重写某些 props |
| `Partial<T>`                            | 把所有字段变成可选    | 表单局部更新、查询条件 patch   |
| `Required<T>`                           | 把所有字段变成必选    | 编辑模式提交参数、模式收窄后的类型   |
| `Record<K, V>`                          | 构造映射表        | 状态文案映射、场景映射、权限码映射   |
| `Readonly<T>`                           | 只读对象         | 静态配置、常量表、只读 props   |
| `React.ComponentPropsWithoutRef<"tag">` | 继承原生元素 props | 基础按钮、基础输入框、链接组件     |

### `Pick`

`Pick` 常用于从接口类型 pick 出前端需要的字段。

```tsx
type StrategyDTO = {
  id: string;
  name: string;
  scene: "loan" | "fraud" | "review";
  status: "draft" | "enabled" | "disabled";
  expression: string;
  version: number;
  creatorName: string;
  updatedAt: string;
};

// 这里 pick 出表格真正需要的字段
type StrategyTableRow = Pick<
  StrategyDTO,
  "id" | "name" | "scene" | "status" | "updatedAt"
>;

// 这里 pick 出表单真正需要的字段
type StrategyFormValue = Pick<
  StrategyDTO,
  "name" | "scene" | "status" | "expression"
>;
```

### `Omit`

`Omit` 常用于从现有类型里排除一部分字段，也常用来扩展第三方组件 props，同时覆盖其中的某个属性类型。

```tsx
import React from "react";

type ThirdPartyButtonProps = {
  size?: "small" | "middle" | "large";
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  children?: React.ReactNode;
};

function ThirdPartyButton(props: ThirdPartyButtonProps) {
  const { size = "middle", children, ...rest } = props;
  return (
    <button data-size={size} {...rest}>
      {children}
    </button>
  );
}

// 这里 Omit（排除）掉第三方组件原来的 size 和 children
// 然后在包装层重新定义自己的 size 和 text
type ActionButtonProps = Omit<ThirdPartyButtonProps, "size" | "children"> & {
  size?: "sm" | "md" | "lg";
  text: string;
};

const sizeMap: Record<
  NonNullable<ActionButtonProps["size"]>,
  ThirdPartyButtonProps["size"]
> = {
  sm: "small",
  md: "middle",
  lg: "large",
};

export function ActionButton(props: ActionButtonProps) {
  const { size = "md", text, ...rest } = props;

  return (
    <ThirdPartyButton {...rest} size={sizeMap[size]}>
      {text}
    </ThirdPartyButton>
  );
}
```

### `Partial`

`Partial` 常用于局部更新。传入的数据可以理解为“完整对象的一部分”。

```tsx
type StrategyFormValue = {
  name: string;
  scene: "loan" | "fraud" | "review";
  status: "draft" | "enabled" | "disabled";
  expression: string;
};

interface StrategyFormProps {
  value: StrategyFormValue;
  // 这里表示 onChange 接收的是 StrategyFormValue 的一部分字段
  onChange: (patch: Partial<StrategyFormValue>) => void;
}

export function StrategyForm(props: StrategyFormProps) {
  const { value, onChange } = props;

  return (
    <section>
      <input
        value={value.name}
        onChange={(event) => onChange({ name: event.currentTarget.value })}
      />

      <textarea
        value={value.expression}
        onChange={(event) =>
          onChange({ expression: event.currentTarget.value })
        }
      />
    </section>
  );
}
```

`Partial<T>` 很适合 patch 场景。下面这段代码更容易看出区别：

```tsx
type UserForm = {
  name: string;
  mobile: string;
  deptId: string;
};

function updateDraft(patch: Partial<UserForm>) {
  // 合法，只更新一部分字段
  console.log(patch);
}

updateDraft({ name: "张三" });
updateDraft({ mobile: "13800000000" });

// 如果最终提交接口要求完整字段，就不应该继续用 Partial<UserForm>
function submitForm(payload: UserForm) {
  console.log(payload);
}

// 下面这行会报类型错误，因为缺少 mobile 和 deptId
// submitForm({ name: "张三" });
```

### `Required`

`Required` 常用于编辑模式这类必须补齐字段的场景。

```tsx
type StrategyCreatePayload = StrategyFormValue;

// 这里表示更新接口除了表单字段外，id 也必须存在
type StrategyUpdatePayload = Required<Pick<StrategyDTO, "id">> &
  StrategyFormValue;
```

### `Record`

`Record` 常用于做状态映射和配置映射。

```tsx
type StrategyScene = "loan" | "fraud" | "review";

// Record 会要求 key 集合完整
const sceneTextMap: Record<StrategyScene, string> = {
  loan: "贷前",
  fraud: "反欺诈",
  review: "复核",
};

// 普通对象如果没有显式约束，通常不会自动要求 key 完整
const looseSceneMap = {
  loan: "贷前",
  fraud: "反欺诈",
};

// 下面这个函数要求传入完整的 StrategyScene
function getSceneText(scene: StrategyScene) {
  return sceneTextMap[scene];
}
```

如果后面 `StrategyScene` 新增了 `"manual_review"`，`sceneTextMap` 会立刻报错，提醒你把映射补齐。`Record` 的价值就在这里：key 集合和 value 类型都被写进类型系统了。

### `Readonly`

`Readonly` 常用于静态配置。

```tsx
type ActionConfig = Readonly<{
  code: "create" | "edit" | "delete";
  text: string;
}>;

const actionList: ReadonlyArray<ActionConfig> = [
  { code: "create", text: "新建" },
  { code: "edit", text: "编辑" },
  { code: "delete", text: "删除" },
];

// 下面这行会报类型错误
// actionList[0].text = "修改";
```

---

## 常见面试题

### 如何在 React 中编写一个泛型组件（Generic Component）？

一个能在面试里拿得出手的答案，通常至少要说清楚三层。

第一层，组件本身要有泛型参数。例如：

```tsx
function DataTable<T>(props: DataTableProps<T>) {
  ...
}
```

这里的 `T` 表示“当前这张表的行数据类型”。

第二层，泛型参数要和 props 绑定。例如：

```tsx
interface DataTableProps<T> {
  rows: T[];
  rowKey: (row: T) => string;
  columns: Array<TableColumn<T>>;
  onRowClick?: (row: T) => void;
}
```

这一步完成之后，只要调用方传入的是 `StrategyRow[]`，`rowKey` 和 `onRowClick` 里的 `row` 就都会自动变成 `StrategyRow`。

第三层，列渲染这种更细粒度的位置，还要继续把“字段”和“字段值类型”绑定起来。前面的 `createColumn<T, K extends keyof T>` 就是在做这件事：

```tsx
function createColumn<T, K extends keyof T>(config: {
  key: K;
  render?: (value: T[K], row: T) => React.ReactNode;
}): TableColumn<T> {
  ...
}
```

这里的 `K` 是具体字段，`T[K]` 是该字段对应的值类型。
如果 `K` 是 `"scene"`，那 `T[K]` 就会变成 `"loan" | "fraud" | "review"`。这样列渲染函数里拿到的 `value` 才是精确类型。

面试时可以直接顺着这个链路回答：
`DataTable<T>` 定义行类型，`DataTableProps<T>` 把这个行类型传到 rows 和回调，`createColumn<T, K extends keyof T>` 再把字段和值类型继续往下收窄。这样类型才能从组件入口一路传到 render 和点击回调里。

### 如何扩展第三方库的组件 Props，同时覆盖其中的某个属性类型？

常见答案就是 `Omit + 重新定义 + 映射回原组件`。

先看代码：

```tsx
type ThirdPartyButtonProps = {
  size?: "small" | "middle" | "large";
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  children?: React.ReactNode;
};

type ActionButtonProps = Omit<ThirdPartyButtonProps, "size" | "children"> & {
  size?: "sm" | "md" | "lg";
  text: string;
};
```

这里先 `Omit` 原来的 `size` 和 `children`，是为了避免同名属性冲突，也避免包装层同时暴露两套语义。
如果不先去掉原字段，再重新定义同名属性，最终 props 契约会变得很混乱：外部到底该传 `"small"` 还是 `"sm"`，该传 `children` 还是 `text`，都会失去控制。

然后包装层再把新类型映射回第三方组件原来的 props：

```tsx
const sizeMap: Record<
  NonNullable<ActionButtonProps["size"]>,
  ThirdPartyButtonProps["size"]
> = {
  sm: "small",
  md: "middle",
  lg: "large",
};

function ActionButton(props: ActionButtonProps) {
  const { size = "md", text, ...rest } = props;

  return (
    <ThirdPartyButton {...rest} size={sizeMap[size]}>
      {text}
    </ThirdPartyButton>
  );
}
```

这段代码里，外部调用方面对的是业务侧的新接口，底层第三方组件拿到的仍然是它原本认识的 `size` 类型。
回答这道题时，最好把这两点都说出来：先 `Omit` 是为了收回原字段定义权，再映射回原组件是为了让包装层和底层组件都能保持各自稳定的契约。

### 高阶组件（HOC）在 TypeScript 中如何正确推导 Props 类型？

这类题的关键点通常有两个：注入型 props 怎么声明，外部调用方怎么避免重复传入被注入的字段。

代码实现：

```tsx
import React from "react";

type InjectedAuthProps = {
  canEdit: boolean;
};

function withPermission<P extends InjectedAuthProps>(
  WrappedComponent: React.ComponentType<P>
) {
  type OuterProps = Omit<P, keyof InjectedAuthProps>;

  return function PermissionComponent(props: OuterProps) {
    const canEdit = true;

    return (
      <WrappedComponent
        {...(props as P)}
        canEdit={canEdit}
      />
    );
  };
}

type StrategyEditorProps = {
  id: string;
  canEdit: boolean;
};

function StrategyEditor(props: StrategyEditorProps) {
  return <div>{props.canEdit ? "可编辑" : "只读"}</div>;
}

const StrategyEditorWithPermission = withPermission(StrategyEditor);

export function Demo() {
  return <StrategyEditorWithPermission id="s_1" />;
}
```

这里 `P extends InjectedAuthProps` 表示：被包装组件至少要接受 `canEdit` 这个 prop。
`OuterProps = Omit<P, keyof InjectedAuthProps>` 表示：对外暴露的新组件，不再要求调用方传 `canEdit`。这个字段会在 HOC 内部被注入。

如果没有这一步 `Omit`，外部调用方就还得自己传一遍 `canEdit`，那这个 HOC 的类型设计就没有完成闭环。

### `Partial<T>` 适合哪些场景，不适合哪些场景？

适合 patch、草稿保存、查询条件局部更新这类场景。因为这类场景本来就只会改动一部分字段。

例如：

```tsx
type SearchForm = {
  keyword: string;
  status: "enabled" | "disabled";
  deptId: string;
};

function patchSearchForm(patch: Partial<SearchForm>) {
  console.log(patch);
}

patchSearchForm({ keyword: "张三" });
patchSearchForm({ status: "enabled" });
```

这时候 `Partial<SearchForm>` 非常合适，因为传入的数据本来就是完整表单的一部分。

不适合最终提交这类要求完整字段的场景。例如：

```tsx
type CreateUserPayload = {
  name: string;
  mobile: string;
  deptId: string;
};

function createUser(payload: CreateUserPayload) {
  console.log(payload);
}

// 下面这行会报类型错误，因为字段不完整
// createUser({ name: "张三" });
```

如果这里还用 `Partial<CreateUserPayload>`，缺字段的问题就会被拖到运行时。

### `Record` 和普通对象字面量相比，有什么优势？

`Record` 的优势在于：它会要求 key 集合完整，并且把 value 类型也约束住。

例如：

```tsx
type Status = "draft" | "enabled" | "disabled";

const statusTextMap: Record<Status, string> = {
  draft: "草稿",
  enabled: "启用",
  disabled: "停用",
};
```

这里如果 `Status` 新增了 `"archived"`，这张映射表会立刻报错，提醒你补齐。

对比普通对象字面量：

```tsx
const looseStatusMap = {
  draft: "草稿",
  enabled: "启用",
};
```

这段代码本身通常不会主动提示“缺少 disabled”。
所以当你处理的是“枚举值到文案”“状态到颜色”“场景到权限码”这类一一映射关系时，`Record` 的表达力会更强。
