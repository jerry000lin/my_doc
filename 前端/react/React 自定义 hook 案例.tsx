import React, { useEffect, useRef, useState } from "react";

type FilterState = {
  keyword: string;
  status: "all" | "running" | "success" | "failed";
  owner: string;
};

const DEFAULT_FILTERS: FilterState = {
  keyword: "",
  status: "all",
  owner: "",
};

function readStorage<T>(key: string, defaultValue: T): T {
  const raw = localStorage.getItem(key);

  if (!raw) {
    return defaultValue;
  }

  try {
    return JSON.parse(raw) as T;
  } catch {
    return defaultValue;
  }
}

function writeStorage<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value));
}

/**
 * 1. 最简单的错误命令式写入
 *
 * 问题：
 * - useState 初始化函数只在首次挂载时执行一次
 * - key 变化后，state 不会自动重读
 * - 切到新 key 时，页面里仍然可能保留旧 state
 */
function useBuggyLocalStorage<T>(
  key: string,
  defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => {
    const storedValue = localStorage.getItem(key);
    return storedValue ? JSON.parse(storedValue) : defaultValue;
  });

  function setLocalStorageState(action: React.SetStateAction<T>) {
    const next =
      typeof action === "function"
        ? (action as (prev: T) => T)(state)
        : action;

    setState(next);
    localStorage.setItem(key, JSON.stringify(next));
  }

  return [state, setLocalStorageState];
}

/**
 * 2. 正确的命令式写入（最简化，不用 useEffect）
 *
 * 这个 hook 本身不处理 key 切换。
 * 它之所以成立，靠的是调用方给组件加 key，让组件在 storageKey 变化时重挂载。
 */
function usePureImperativeLocalStorage<T>(
  key: string,
  defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => readStorage(key, defaultValue));

  function setLocalStorageState(action: React.SetStateAction<T>) {
    const next =
      typeof action === "function"
        ? (action as (prev: T) => T)(state)
        : action;

    setState(next);
    writeStorage(key, next);
  }

  return [state, setLocalStorageState];
}

/**
 * 3. useEffect 错误版
 *
 * 问题：
 * - 它只负责把当前 state 写回当前 key
 * - 但 key 变化后，没有先从新 key 重新读取 state
 * - 结果是旧 state 会带到新 key 上，甚至把旧值写进新 key
 */
function useNaiveEffectLocalStorage<T>(
  key: string,
  defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => readStorage(key, defaultValue));

  useEffect(() => {
    writeStorage(key, state);
  }, [key, state]);

  return [state, setState];
}

/**
 * 4. useEffect 正确版
 *
 * 职责拆成两段：
 * - key 变化：先从新 key 重新读取 state
 * - state 变化：再把当前 state 写回当前 key
 *
 * 还要跳过“切 key 后第一次写回”，避免把旧 state 覆盖到新 key。
 */
function useCompleteEffectLocalStorage<T>(
  key: string,
  defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(() => readStorage(key, defaultValue));
  const currentKeyRef = useRef(key);
  const skipNextWriteRef = useRef(false);

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

  return [state, setState];
}

type HookType = (
  key: string,
  defaultValue: FilterState
) => readonly [FilterState, React.Dispatch<React.SetStateAction<FilterState>>];

type PanelProps = {
  title: string;
  note: string;
  storageKey: string;
  borderColor: string;
  hook: HookType;
  code: string;
};

function FilterPanel(props: PanelProps) {
  const { title, note, storageKey, borderColor, hook, code } = props;
  const [filters, setFilters] = hook(storageKey, DEFAULT_FILTERS);

  function updateField<K extends keyof FilterState>(
    field: K,
    value: FilterState[K]
  ) {
    setFilters((prev) => ({
      ...prev,
      [field]: value,
    }));
  }

  return (
    <div
      style={{

        flex: 1,
        border: `2px solid ${borderColor}`,
        borderRadius: 8,
        padding: 16,
        boxSizing: "border-box",
        background: "#fff",
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 8 }}>{title}</h3>

      <div
        style={{
          fontSize: 12,
          color: "#666",
          lineHeight: 1.6,
          marginBottom: 12,
        }}
      >
        <div>
          当前 storage key: <code>{storageKey}</code>
        </div>
        <div>{note}</div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: "block", marginBottom: 4 }}>关键词</label>
        <input
          value={filters.keyword}
          onChange={(e) => updateField("keyword", e.target.value)}
          placeholder="例如：预审、放款、逾期"
          style={{ width: "100%", boxSizing: "border-box" }}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: "block", marginBottom: 4 }}>状态</label>
        <select
          value={filters.status}
          onChange={(e) =>
            updateField(
              "status",
              e.target.value as FilterState["status"]
            )
          }
          style={{ width: "100%" }}
        >
          <option value="all">全部</option>
          <option value="running">处理中</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
        </select>
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: "block", marginBottom: 4 }}>负责人</label>
        <input
          value={filters.owner}
          onChange={(e) => updateField("owner", e.target.value)}
          placeholder="例如：张三、李四"
          style={{ width: "100%", boxSizing: "border-box" }}
        />
      </div>

      <pre
        style={{
          background: "#f6f6f6",
          padding: 12,
          borderRadius: 6,
          fontSize: 12,
          lineHeight: 1.5,
          overflow: "auto",
        }}
      >
        {JSON.stringify(filters, null, 2)}
      </pre>

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", userSelect: "none" }}>
          查看对应代码
        </summary>
        <pre
          style={{
            marginTop: 12,
            background: "#1f1f1f",
            color: "#f5f5f5",
            padding: 12,
            borderRadius: 6,
            fontSize: 12,
            lineHeight: 1.6,
            overflow: "auto",
            whiteSpace: "pre-wrap",
          }}
        >
          {code}
        </pre>
      </details>
    </div>
  );
}

function PureImperativePanel(props: {
  storageKey: string;
  code: string;
}) {
  return (
    <FilterPanel
      title="2. 正确命令式写入"
      note="关键不在 hook 内部，而在调用时给组件加 key，让它跟着 storageKey 重挂载。"
      storageKey={props.storageKey}
      borderColor="#096dd9"
      hook={usePureImperativeLocalStorage}
      code={props.code}
    />
  );
}

const BUGGY_CODE = `
function useBuggyLocalStorage<T>(
    key: string,
    defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
    const [state, setState] = useState<T>(() => {
        const storedValue = localStorage.getItem(key);
        return storedValue ? JSON.parse(storedValue) : defaultValue;
    });

    function setLocalStorageState(action: React.SetStateAction<T>) {
        const next =
            typeof action === "function"
                ? (action as (prev: T) => T)(state)
                : action;

        setState(next);
        localStorage.setItem(key, JSON.stringify(next));
    }

    return [state, setLocalStorageState];
}

// 问题：key 变化后，useState 初始化函数不会重新执行。
// 页面还是旧 state，但你已经在操作新的 storage key。
`.trim();

const PURE_IMPERATIVE_CODE = `
function usePureImperativeLocalStorage<T>(
    key: string,
    defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
    const [state, setState] = useState<T>(() => readStorage(key, defaultValue));

    function setLocalStorageState(action: React.SetStateAction<T>) {
        const next =
            typeof action === "function"
                ? (action as (prev: T) => T)(state)
                : action;

        setState(next);
        writeStorage(key, next);
    }

    return [state, setLocalStorageState];
}

// 关键差异不在 hook 内部，而在调用方式：
<PureImperativePanel
    key={storageKey}
    storageKey={storageKey}
    code={PURE_IMPERATIVE_CODE}
/>

// 给组件加 key 后，storageKey 一变，组件会重挂载。
// useState 初始化函数重新执行，于是会重新读取新 key 对应的数据。
`.trim();

const NAIVE_EFFECT_CODE = `
function useNaiveEffectLocalStorage<T>(
    key: string,
    defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
    const [state, setState] = useState<T>(() => readStorage(key, defaultValue));

    useEffect(() => {
        writeStorage(key, state);
    }, [key, state]);

    return [state, setState];
}

// 问题：它只做了“写回”，没做“key 变化后的重读”。
// 切到新 key 时，旧 state 还在，effect 还会把旧 state 写进新 key。
`.trim();

const COMPLETE_EFFECT_CODE = `
function useCompleteEffectLocalStorage<T>(
    key: string,
    defaultValue: T
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
    const [state, setState] = useState<T>(() => readStorage(key, defaultValue));
    const currentKeyRef = useRef(key);
    const skipNextWriteRef = useRef(false);

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

    return [state, setState];
}

// 这版把职责补齐了：
// 1. key 变化，先重读
// 2. state 变化，再写回
`.trim();

export default function LocalStorageHooksFourCasesDemo() {
  const [moduleId, setModuleId] = useState<"risk" | "marketing">("risk");
  const [, forceRender] = useState({});

  const buggyKey = `BUGGY_FILTERS_${moduleId}`;
  const pureImperativeKey = `PURE_IMPERATIVE_FILTERS_${moduleId}`;
  const naiveEffectKey = `NAIVE_EFFECT_FILTERS_${moduleId}`;
  const completeEffectKey = `COMPLETE_EFFECT_FILTERS_${moduleId}`;

  function seedData() {
    localStorage.setItem(
      "BUGGY_FILTERS_risk",
      JSON.stringify({
        keyword: "逾期客户",
        status: "running",
        owner: "张三",
      })
    );
    localStorage.setItem(
      "BUGGY_FILTERS_marketing",
      JSON.stringify({
        keyword: "高价值客户",
        status: "success",
        owner: "李四",
      })
    );

    localStorage.setItem(
      "PURE_IMPERATIVE_FILTERS_risk",
      JSON.stringify({
        keyword: "逾期客户",
        status: "running",
        owner: "张三",
      })
    );
    localStorage.setItem(
      "PURE_IMPERATIVE_FILTERS_marketing",
      JSON.stringify({
        keyword: "高价值客户",
        status: "success",
        owner: "李四",
      })
    );

    localStorage.setItem(
      "NAIVE_EFFECT_FILTERS_risk",
      JSON.stringify({
        keyword: "逾期客户",
        status: "running",
        owner: "张三",
      })
    );
    localStorage.setItem(
      "NAIVE_EFFECT_FILTERS_marketing",
      JSON.stringify({
        keyword: "高价值客户",
        status: "success",
        owner: "李四",
      })
    );

    localStorage.setItem(
      "COMPLETE_EFFECT_FILTERS_risk",
      JSON.stringify({
        keyword: "逾期客户",
        status: "running",
        owner: "张三",
      })
    );
    localStorage.setItem(
      "COMPLETE_EFFECT_FILTERS_marketing",
      JSON.stringify({
        keyword: "高价值客户",
        status: "success",
        owner: "李四",
      })
    );

    forceRender({});
  }

  function clearData() {
    [
      "BUGGY_FILTERS_risk",
      "BUGGY_FILTERS_marketing",
      "PURE_IMPERATIVE_FILTERS_risk",
      "PURE_IMPERATIVE_FILTERS_marketing",
      "NAIVE_EFFECT_FILTERS_risk",
      "NAIVE_EFFECT_FILTERS_marketing",
      "COMPLETE_EFFECT_FILTERS_risk",
      "COMPLETE_EFFECT_FILTERS_marketing",
    ].forEach((key) => localStorage.removeItem(key));

    forceRender({});
  }

  return (
    <div
      style={{
        padding: 24,
        fontFamily: "Arial, sans-serif",
        background: "#fafafa",
        minHeight: "100vh",
        boxSizing: "border-box",
      }}
    >
      <h2 style={{ marginTop: 0 }}>
        LocalStorage Hook 四种写法对比
      </h2>

      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          padding: 16,
          marginBottom: 20,
          lineHeight: 1.8,
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 8 }}>建议操作步骤</div>
        <ol style={{ marginTop: 0, marginBottom: 12 }}>
          <li>先点击“写入演示数据”。</li>
          <li>保持当前模块为“风控工作台”，四个面板都会先显示风控自己的缓存。</li>
          <li>切换到“营销工作台”。</li>
          <li>观察四个面板里的输入框内容。</li>
          <li>再滚动到最下方，点击“刷新下方 LocalStorage 观察区”。</li>
          <li>对比哪几种写法把新 key 的缓存处理对了，哪几种写法把旧 state 带过去了。</li>
        </ol>

        <div style={{ fontWeight: 700, marginBottom: 8 }}>预期现象</div>
        <div>
          1. 错误命令式写入：界面还会残留旧模块的 state。
          <br />
          2. 正确命令式写入：因为组件跟着 storageKey 重挂载，会直接读到新 key 的值。
          <br />
          3. useEffect 错误版：旧 state 没重读，还可能被写进新 key。
          <br />
          4. useEffect 正确版：会在 key 变化后先重读，再按当前 key 写回。
        </div>
      </div>

      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          padding: 16,
          marginBottom: 20,
        }}
      >
        <div style={{ marginBottom: 12 }}>
          <button onClick={seedData} style={{ marginRight: 12 }}>
            写入演示数据
          </button>
          <button onClick={clearData}>
            清空演示数据
          </button>
        </div>

        <div>
          <strong>当前模块：</strong>
          <label style={{ marginLeft: 12, marginRight: 12 }}>
            <input
              type="radio"
              checked={moduleId === "risk"}
              onChange={() => setModuleId("risk")}
            />
            风控工作台
          </label>
          <label>
            <input
              type="radio"
              checked={moduleId === "marketing"}
              onChange={() => setModuleId("marketing")}
            />
            营销工作台
          </label>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "flex-start",
          overflowX: "auto",
          paddingBottom: 8,
          marginBottom: 20,
        }}
      >
        <FilterPanel
          title="1. 错误命令式写入"
          note="Vue 风格很常见。简单直接，但 key 切换后不会自动重读。"
          storageKey={buggyKey}
          borderColor="#cf1322"
          hook={useBuggyLocalStorage}
          code={BUGGY_CODE}
        />

        <PureImperativePanel
          key={pureImperativeKey}
          storageKey={pureImperativeKey}
          code={PURE_IMPERATIVE_CODE}
        />

        <FilterPanel
          title="3. useEffect 错误版"
          note="只做写回，不做 key 切换后的重读。"
          storageKey={naiveEffectKey}
          borderColor="#d48806"
          hook={useNaiveEffectLocalStorage}
          code={NAIVE_EFFECT_CODE}
        />

        <FilterPanel
          title="4. useEffect 正确版"
          note="key 变化先重读，state 变化再写回。"
          storageKey={completeEffectKey}
          borderColor="#389e0d"
          hook={useCompleteEffectLocalStorage}
          code={COMPLETE_EFFECT_CODE}
        />
      </div>

      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          padding: 16,
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 16,
            overflowX: "auto",
            paddingBottom: 8,
          }}
        >
          <pre
            style={{
              flex: 1,
              background: "#1f1f1f",
              color: "#ffccc7",
              padding: 16,
              borderRadius: 8,
              overflow: "auto",
              lineHeight: 1.6,
              boxSizing: "border-box",
              margin: 0,
            }}
          >
            {`[1. 错误命令式写入]
BUGGY_FILTERS_risk:
${localStorage.getItem("BUGGY_FILTERS_risk") || "空"}

BUGGY_FILTERS_marketing:
${localStorage.getItem("BUGGY_FILTERS_marketing") || "空"}`}
          </pre>

          <pre
            style={{
              flex: 1,
              background: "#1f1f1f",
              color: "#91caff",
              padding: 16,
              borderRadius: 8,
              overflow: "auto",
              lineHeight: 1.6,
              boxSizing: "border-box",
              margin: 0,
            }}
          >
            {`[2. 正确命令式写入]
PURE_IMPERATIVE_FILTERS_risk:
${localStorage.getItem("PURE_IMPERATIVE_FILTERS_risk") || "空"}

PURE_IMPERATIVE_FILTERS_marketing:
${localStorage.getItem("PURE_IMPERATIVE_FILTERS_marketing") || "空"}`}
          </pre>

          <pre
            style={{
              flex: 1,
              background: "#1f1f1f",
              color: "#ffe58f",
              padding: 16,
              borderRadius: 8,
              overflow: "auto",
              lineHeight: 1.6,
              boxSizing: "border-box",
              margin: 0,
            }}
          >
            {`[3. useEffect 错误版]
NAIVE_EFFECT_FILTERS_risk:
${localStorage.getItem("NAIVE_EFFECT_FILTERS_risk") || "空"}

NAIVE_EFFECT_FILTERS_marketing:
${localStorage.getItem("NAIVE_EFFECT_FILTERS_marketing") || "空"}`}
          </pre>

          <pre
            style={{
              flex: 1,
              background: "#1f1f1f",
              color: "#b7eb8f",
              padding: 16,
              borderRadius: 8,
              overflow: "auto",
              lineHeight: 1.6,
              boxSizing: "border-box",
              margin: 0,
            }}
          >
            {`[4. useEffect 正确版]
COMPLETE_EFFECT_FILTERS_risk:
${localStorage.getItem("COMPLETE_EFFECT_FILTERS_risk") || "空"}

COMPLETE_EFFECT_FILTERS_marketing:
${localStorage.getItem("COMPLETE_EFFECT_FILTERS_marketing") || "空"}`}
          </pre>
        </div>

        <div style={{ marginTop: 16 }}>
          <button onClick={() => forceRender({})}>
            刷新 LocalStorage 观察区
          </button>
        </div>
      </div>
    </div>
  );
}