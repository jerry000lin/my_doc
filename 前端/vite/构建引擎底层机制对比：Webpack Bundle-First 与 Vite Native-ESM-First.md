# 构建引擎底层机制对比：Webpack Bundle-First 与 Vite Native-ESM-First

## 核心构建哲学与开发模型差异

[Webpack](https://webpack.js.org/concepts/) 的开发链路以 **Compiler** 为控制中心。系统从 **Entry** 出发构建内部 **Dependency Graph**，执行 loader / plugin 转换，完成模块编号、chunk 归并、bundle 组织与 runtime 注入，再将编译产物交付浏览器执行。由此，**Module Graph** 在 Webpack 中承担产物生成、chunk 切分、运行时寻址与增量编译 bookkeeping 的统一职责，浏览器消费的核心对象是编译后的静态资源与配套 runtime。

[Vite](https://vite.dev/guide/why) 的开发链路以 **Native ESM** 为加载契约，以开发服务器为解析与转换中枢。系统首先对变化频率低的依赖执行预构建与 URL 重写，然后在浏览器发起模块请求时按需触发 `resolveId / load / transform`，直接返回可执行的 ESM 模块。由此，**Module Graph** 在 Vite 中承担导入分析、URL 解析、转换缓存、失效传播与 HMR 定位职责，浏览器通过原生 ESM 图按页面访问路径驱动模块加载顺序与请求范围。

两套模型的分界点在于开发期主控权的归属。Webpack 将模块组织权、更新产物生成权与执行时补丁管理权集中在 **Compiler + Runtime** 一侧；Vite 将源码模块的装载时机交由浏览器 ESM 图驱动，将服务端职责收敛到依赖预处理、请求时转换与图级失效管理。Vite 在生产阶段进入 [build pipeline](https://vite.dev/guide/why) 并输出 application bundle；当前主版本的官方迁移文档已明确，Vite 8 使用基于 [Rolldown 和 Oxc 的工具链](https://cn.vite.dev/guide/migration)。

## HMR 机制演进与边界控制

[Webpack HMR](https://webpack.js.org/concepts/hot-module-replacement/) 依赖 **Compiler** 与 **HMR Runtime** 的双侧协作。文件变更后，编译器会为新旧版本之间的差量生成 **updated manifest** 与 **updated chunks**；运行时通过 `check` / `apply` 流程拉取更新、比对已加载 chunk、下载补丁并应用到当前模块系统。运行时内部维护模块的 `parents` / `children` 关系，并沿导入链向上执行失效传播；当某个模块或其父模块存在可接收更新的 handler 时，更新在该边界内完成；当导入链传播至入口点仍未命中接收边界时，流程回退为整页刷新。Webpack 的 HMR 单位是编译器生成的补丁产物与 runtime 中的模块替换过程。

[Vite HMR](https://vite.dev/guide/api-hmr) 建立在 **`import.meta.hot` API** 与 **Native ESM** 请求模型之上。模块只有在源代码中显式出现 `import.meta.hot.accept(` 时，才会被静态分析识别为可接收更新的 **HMR 边界**。更新命中边界后，Vite 通过 WebSocket 下发变更指令，浏览器重新请求相关模块 URL，边界模块在回调中接收新的模块实例；当模块逻辑无法在当前边界内闭合处理时，可通过 `invalidate()` 将失效继续向导入者传播。官方文档对边界语义给出了明确约束：边界模块若承担 re-export 责任，需要自行维护重新导出的绑定与副作用清理。`dispose`、`prune` 与 `data` 共同负责边界内副作用释放、模块移除清理与跨版本状态传递。

两者的 HMR 控制面由此形成明确分层。Webpack 通过 **Runtime 补丁应用** 管理模块替换；Vite 通过 **边界声明 + 失效传播 + 浏览器重新请求模块** 管理更新闭环。前者的关键对象是 **update manifest / update chunk / runtime state machine**，后者的关键对象是 **HMR boundary / import analysis / invalidation propagation / module re-request**。

## 性能特征溯源：冷启动与热更新

**冷启动** 的性能差异来自前置工作量的分配方式。[Webpack](https://webpack.js.org/concepts/) 的 bundle-first 开发模型要求在服务可用前完成入口出发的依赖图建立、模块转换与 bundle 组织，因此启动延迟天然受 **模块总量、转换链长度、chunk 组织复杂度** 影响。[Vite](https://vite.dev/guide/why) 将依赖与源码拆分处理：依赖执行一次预构建，源码仅在请求到达时触发转换，因此官方文档将其描述为启动几乎不受应用规模影响，页面首屏只加载当前路由实际命中的模块集合。

**热更新** 的性能差异来自更新范围的裁剪方式。[Webpack HMR](https://webpack.js.org/concepts/hot-module-replacement/) 的单次更新需要经过编译器失效标记、差量产物生成、manifest / chunk 下载与 runtime 应用，更新时延与受影响模块、相关父子链路以及需要重新生成的补丁产物共同相关。[Vite HMR](https://vite.dev/guide/api-hmr) 的更新路径集中在受影响文件、其导入者链路与命中的 **HMR 边界**；依赖预构建与强缓存已经提前消化了大部分稳定依赖成本，源码更新通常只触发局部模块重新请求与局部回调执行。**因此，Vite 的更新时延与受影响的模块子图规模正相关，与项目总规模解耦。**

依赖预构建进一步放大了这组差异。[Vite 的官方文档](https://vite.dev/guide/dep-pre-bundling) 将其目的定义为两项：其一，将 **CommonJS / UMD** 依赖转换为 ESM；其二，将内部模块极多的依赖收敛为更少的请求单元，降低浏览器侧并发请求拥塞。该机制直接削减了开发期的模块碎片化网络开销，并将稳定依赖的处理代价前移到首次启动与缓存命中阶段。

## 附录：Webpack vs Vite 开发/生产链路对照表

| 维度                     | Webpack                                                                                                             | Vite                                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **开发期驱动核心**            | [**Compiler** 驱动的 **Dependency Graph → transform → chunk / bundle → runtime** 链路](https://webpack.js.org/concepts/) | [**Native ESM** 驱动的 **dependency pre-bundling + on-demand transform** 链路](https://vite.dev/guide/why)     |
| **开发期模块交付单位**          | 编译后的 **bundle / chunk** 与配套 **runtime**                                                                             | 浏览器请求到的 **单个 ESM 模块**                                                                                     |
| **Module Graph 的主要目标** | 产物生成、chunk 切分、模块编号、runtime 寻址、增量编译管理                                                                                | 导入分析、URL 解析、转换缓存、失效传播、HMR 定位                                                                              |
| **源码转换触发时机**           | 编译阶段集中执行，更新时重新进入编译流水线                                                                                               | 请求到达时按模块触发 `resolveId / load / transform`                                                                 |
| **HMR 控制对象**           | [**updated manifest + updated chunks + HMR Runtime**](https://webpack.js.org/concepts/hot-module-replacement/)      | [**HMR boundary + `import.meta.hot` + invalidation propagation**](https://vite.dev/guide/api-hmr)         |
| **HMR 边界定义方式**         | `module.hot` handler 命中模块或其父链路上的接收边界                                                                                | 源码中显式出现 `import.meta.hot.accept(` 的模块边界                                                                   |
| **更新传播模型**             | runtime 沿 `parents / children` 关系向上冒泡，直到命中接收边界或入口点                                                                  | 沿导入链传播到可接收边界；边界可继续 `invalidate()` 向上失效                                                                    |
| **冷启动瓶颈来源**            | 全量依赖遍历、转换链执行、bundle / chunk 组织                                                                                      | 首次依赖预构建与首屏命中模块转换                                                                                          |
| **热更新时间决定因素**          | 受影响模块链路、补丁产物生成、runtime 应用成本                                                                                         | 受影响模块子图规模、边界数量、局部重新请求与回调执行成本                                                                              |
| **生产期构建链路**            | [统一 bundle-oriented build pipeline，输出优化后的静态资源](https://webpack.js.org/guides/production/)                           | [`vite build` 输出 application bundle；Vite 8 使用基于 Rolldown 和 Oxc 的工具链](https://cn.vite.dev/guide/migration) |
