# 风控样本 Labeling 通用 SQL 脚手架与场景适配指南

## 1. 核心底层表依赖 (`Input Data`)

### 1.1 主体基础表：申请 / 授信 / 合同基表

用于圈定样本主体、确定观察时点、保留后续标签锚点。

| 字段           | 含义              | 必要性          |
| ------------ | --------------- | ------------ |
| `party_id`   | 客户统一主键          | 必需           |
| `biz_id`     | 申请号 / 合同号 / 借据号 | 必需           |
| `product_id` | 产品编码            | 建议           |
| `channel_id` | 渠道编码            | 建议           |
| `apply_dt`   | 申请日期            | 常用           |
| `approve_dt` | 审批日期            | 视场景          |
| `loan_dt`    | 放款日期            | 常用           |
| `obs_dt`     | 观察时点            | 必需，通常由业务规则派生 |
| `amt`        | 金额              | 建议           |
| `term_no`    | 期数              | 建议           |
| `status_cd`  | 当前业务状态          | 建议           |

### 1.2 还款 / 逾期快照表：月末或日级资产状态表

用于截取观察时点历史状态、表现期最差表现、当前状态分层。

| 字段              | 含义               | 必要性 |
| --------------- | ---------------- | --- |
| `biz_id`        | 与主体表关联的合同 / 借据主键 | 必需  |
| `snapshot_dt`   | 快照日期             | 必需  |
| `dpd_days`      | 逾期天数             | 必需  |
| `writeoff_flag` | 核销标记             | 建议  |
| `balance_amt`   | 余额               | 建议  |
| `settle_flag`   | 结清标记             | 建议  |

### 1.3 主体映射表：客户号映射到统一主体

用于多系统客户号统一到 `party_id`。

| 字段            | 含义     | 必要性 |
| ------------- | ------ | --- |
| `raw_cust_id` | 原始客户号  | 必需  |
| `party_id`    | 统一主体主键 | 必需  |
| `eff_dt`      | 生效日期   | 建议  |
| `exp_dt`      | 失效日期   | 建议  |

### 1.4 可选资产流水 / 计划表

用于更精细的还款行为、首逾、迁徙、回款节奏刻画。

| 字段          | 含义       | 必要性 |
| ----------- | -------- | --- |
| `biz_id`    | 合同 / 借据号 | 常用  |
| `due_dt`    | 应还日      | 常用  |
| `repay_dt`  | 实还日      | 常用  |
| `due_amt`   | 应还金额     | 建议  |
| `repay_amt` | 实还金额     | 建议  |

### 1.5 最低可运行字段集合

最小可运行 SQL 脚手架需要以下字段即可落地：

* 主体侧：`party_id`、`biz_id`、`apply_dt`、`loan_dt`
* 快照侧：`biz_id`、`snapshot_dt`、`dpd_days`
* 若有多系统客户号：`raw_cust_id -> party_id`

---

## 2. 核心 SQL 模板：统一骨架与字段归属

### 2.1 核心脚手架

以下模板采用 `Hive / Spark SQL` 风格，使用统一的 4 个 `CTE`：

* `CTE_Base_Population`
* `CTE_Observation_Status`
* `CTE_Performance_Window`
* `CTE_Final_Labeling`

这四层结构在绝大多数风控 Labeling 问题中都稳定成立。
差异主要体现在：

* `obs_dt` 如何定义
* `CTE_Observation_Status` 产出哪些字段
* `CTE_Performance_Window` 是否强依赖
* `CTE_Final_Labeling` 的 `CASE WHEN` 如何组装

```sql
-- 参数约定
-- ${obs_start_dt}         样本起始观察日
-- ${obs_end_dt}           样本结束观察日
-- ${data_cutoff_dt}       表现数据最大可用日期（全局快照最新更新日）
-- ${perf_months}          表现期长度，示例：6 / 12
-- ${bad_dpd_threshold}    坏样本阈值，示例：30 / 60
-- ${good_clean_threshold} 好样本清洁阈值，固定为 0 或轻微逾期阈值
-- ${biz_type_filter}      产品/业务线过滤条件，按需替换

WITH

/* CTE_Base_Population
 * 输入：主体基础表
 * 关键过程：圈定样本主体；计算观察时点 obs_dt；保留后续标签锚点 loan_dt
 * 输出：一行一个业务主体的基础样本集
 */
CTE_Base_Population AS (
    SELECT
        b.party_id,
        b.biz_id,
        b.product_id,
        b.channel_id,
        b.apply_dt,
        b.loan_dt,
        /* 观察时点示例：申请前一个月月末 */
        last_day(add_months(b.apply_dt, -1)) AS obs_dt,
        b.amt,
        b.term_no
    FROM dm_app_contract_base b
    WHERE b.apply_dt >= to_date('${obs_start_dt}')
      AND b.apply_dt <= to_date('${obs_end_dt}')
      AND b.loan_dt IS NOT NULL
      AND ${biz_type_filter}
),

/* CTE_Observation_Status
 * 输入：基础样本集 + 历史逾期快照
 * 关键过程：
 *   1. 仅截取 snapshot_dt <= obs_dt 的历史状态
 *   2. 聚合观察时点之前的最坏历史状态
 *   3. 截取观察时点当天真实切片状态 current_dpd
 *   4. 形成观察时点分层、已坏剔除标记、历史痕迹特征
 * 输出：每个样本在观察时点已知的历史状态画像
 */
CTE_Observation_Status AS (
    SELECT
        bp.party_id,
        bp.biz_id,
        bp.obs_dt,
        bp.loan_dt,

        max(CASE WHEN s.snapshot_dt <= bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) AS obs_hist_max_dpd,
        max(CASE WHEN s.snapshot_dt <= bp.obs_dt AND coalesce(s.writeoff_flag, 0) = 1 THEN 1 ELSE 0 END) AS obs_hist_writeoff_flag,
        max(CASE WHEN s.snapshot_dt = bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) AS current_dpd,

        CASE
            WHEN max(CASE WHEN s.snapshot_dt <= bp.obs_dt AND coalesce(s.writeoff_flag, 0) = 1 THEN 1 ELSE 0 END) = 1
              OR max(CASE WHEN s.snapshot_dt <= bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) > 60 THEN 'EVER_60P'
            WHEN max(CASE WHEN s.snapshot_dt <= bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) > 30 THEN 'EVER_30_60P'
            WHEN max(CASE WHEN s.snapshot_dt <= bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) > 0 THEN 'EVER_1_30'
            ELSE 'NEVER_DPD'
        END AS obs_hist_dpd_level,

        CASE
            WHEN max(CASE WHEN s.snapshot_dt <= bp.obs_dt AND coalesce(s.writeoff_flag, 0) = 1 THEN 1 ELSE 0 END) = 1
              OR max(CASE WHEN s.snapshot_dt <= bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) > ${bad_dpd_threshold}
            THEN 1 ELSE 0
        END AS obs_already_bad_flag

    FROM CTE_Base_Population bp
    LEFT JOIN fact_asset_dpd_snapshot s
      ON bp.biz_id = s.biz_id
     AND s.snapshot_dt <= bp.obs_dt
    GROUP BY
        bp.party_id,
        bp.biz_id,
        bp.obs_dt,
        bp.loan_dt
),

/* CTE_Performance_Window
 * 输入：基础样本集 + 表现期快照
 * 关键过程：
 *   1. 严格定义表现期起止边界
 *   2. 仅统计 obs_dt 之后、表现期之内的行为
 *   3. 计算期内最差表现与是否成熟
 * 输出：每个样本在表现期内的结果标签基础字段
 */
CTE_Performance_Window AS (
    SELECT
        bp.party_id,
        bp.biz_id,
        bp.obs_dt,
        bp.loan_dt,

        /* 表现期结束日 */
        last_day(add_months(bp.loan_dt, ${perf_months})) AS perf_end_dt,

        /* 成熟标记：全局快照数据是否覆盖表现期 */
        CASE
            WHEN to_date('${data_cutoff_dt}') >= last_day(add_months(bp.loan_dt, ${perf_months})) THEN 1
            ELSE 0
        END AS perf_matured_flag,

        max(CASE
            WHEN s.snapshot_dt > bp.obs_dt
             AND s.snapshot_dt <= last_day(add_months(bp.loan_dt, ${perf_months}))
            THEN coalesce(s.dpd_days, 0)
            ELSE 0
        END) AS perf_max_dpd,

        max(CASE
            WHEN s.snapshot_dt > bp.obs_dt
             AND s.snapshot_dt <= last_day(add_months(bp.loan_dt, ${perf_months}))
             AND coalesce(s.writeoff_flag, 0) = 1
            THEN 1 ELSE 0
        END) AS perf_writeoff_flag,

        max(CASE
            WHEN s.snapshot_dt > bp.obs_dt
             AND s.snapshot_dt <= last_day(add_months(bp.loan_dt, ${perf_months}))
             AND (
                    coalesce(s.writeoff_flag, 0) = 1
                 OR coalesce(s.dpd_days, 0) > ${bad_dpd_threshold}
                 )
            THEN 1 ELSE 0
        END) AS perf_bad_flag

    FROM CTE_Base_Population bp
    LEFT JOIN fact_asset_dpd_snapshot s
      ON bp.biz_id = s.biz_id
     AND s.snapshot_dt > bp.obs_dt
     AND s.snapshot_dt <= last_day(add_months(bp.loan_dt, ${perf_months}))
    GROUP BY
        bp.party_id,
        bp.biz_id,
        bp.obs_dt,
        bp.loan_dt
),

/* CTE_Final_Labeling
 * 输入：观察时点状态 + 表现期结果
 * 关键过程：
 *   1. 已坏样本先剔除
 *   2. 表现期内达到坏阈值记为 1
 *   3. 表现期成熟且窗口内保持 clean 记为 0
 *   4. 未成熟与中间态记为 null
 * 输出：最终训练标签表
 */
CTE_Final_Labeling AS (
    SELECT
        bp.party_id,
        bp.biz_id,
        bp.product_id,
        bp.channel_id,
        bp.apply_dt,
        bp.loan_dt,
        bp.obs_dt,
        bp.amt,
        bp.term_no,

        os.obs_hist_max_dpd,
        os.obs_hist_writeoff_flag,
        os.current_dpd,
        os.obs_hist_dpd_level,
        os.obs_already_bad_flag,

        pw.perf_end_dt,
        pw.perf_matured_flag,
        pw.perf_max_dpd,
        pw.perf_writeoff_flag,
        pw.perf_bad_flag,

        CASE
            WHEN os.obs_already_bad_flag = 1 THEN NULL
            WHEN pw.perf_bad_flag = 1 THEN 1
            WHEN pw.perf_matured_flag = 1 AND pw.perf_max_dpd <= ${good_clean_threshold} THEN 0
            ELSE NULL
        END AS y_label,

        CASE
            WHEN os.obs_already_bad_flag = 1 THEN 'GRAY_ALREADY_BAD_AT_OBS'
            WHEN pw.perf_bad_flag = 1 THEN 'BAD'
            WHEN pw.perf_matured_flag = 1 AND pw.perf_max_dpd <= ${good_clean_threshold} THEN 'GOOD'
            WHEN pw.perf_matured_flag = 0 THEN 'GRAY_UNMATURE'
            ELSE 'GRAY_MIDDLE'
        END AS sample_type

    FROM CTE_Base_Population bp
    LEFT JOIN CTE_Observation_Status os
      ON bp.biz_id = os.biz_id
    LEFT JOIN CTE_Performance_Window pw
      ON bp.biz_id = pw.biz_id
)

SELECT *
FROM CTE_Final_Labeling
;
```

### 2.2 模块解析

#### `CTE_Base_Population`

**输入：**
主体基础表，至少具备 `party_id`、`biz_id`、`apply_dt`、`loan_dt`。

**关键过程：**
按业务条件圈定主体，计算统一的 `obs_dt`，形成样本基座。

**输出：**
一行一个样本主体，后续所有标签和特征都围绕这个主体展开。

#### 核心约束

* `obs_dt` 在这一层固定。
* 主体唯一性在这一层保证。
* 业务过滤条件在这一层集中管理。

---

#### `CTE_Observation_Status`

**输入：**
基础样本集 + 历史状态快照。

**关键过程：**
仅截取 `snapshot_dt <= obs_dt` 的记录，聚合观察时点之前的历史最坏状态；同时截取 `snapshot_dt = obs_dt` 的当日快照，生成 `current_dpd`，用于刻画观察时点当天的真实切片状态。

**输出：**
每个样本在观察时点的历史状态画像，例如 `obs_hist_max_dpd`、`current_dpd`、`obs_hist_dpd_level`、`obs_already_bad_flag`。

#### 核心约束

* 所有 observation-side 字段都来自 `obs_dt` 及之前。
* `current_dpd` 归属于 observation-side。
* `obs_already_bad_flag` 为灰样本隔离提供入口。

---

#### `CTE_Performance_Window`

**输入：**
基础样本集 + 表现期快照。

**关键过程：**
严格圈定 `obs_dt` 之后到表现期结束日之间的窗口，计算窗口内最差表现、坏事件与成熟标记。

**输出：**
每个样本在表现期内的结果字段，例如 `perf_max_dpd`、`perf_bad_flag`、`perf_matured_flag`。

#### 核心约束

* outcome-side 只使用 `snapshot_dt > obs_dt` 的数据。
* `perf_matured_flag` 使用 `to_date('${data_cutoff_dt}')` 判断。
* 成熟度判断依赖全局数据边界，不依赖圈样边界。
* 最近月份未成熟样本由这一层控制。

---

#### `CTE_Final_Labeling`

**输入：**
observation-side 字段 + outcome-side 字段。

**关键过程：**
按业务规则将样本归入 `1 / 0 / NULL`，并同步产出 `sample_type` 作为审计和排查字段。

**输出：**
最终可供建模使用的标签表。

#### 核心约束

* `1` 与 `0` 的边界在这一层集中定义。
* `NULL` 明确承接已坏、未成熟和中间态。
* 路线差异主要体现在这一层的 `CASE WHEN`。

---

## 3. 标签定义路线：固定观察窗、当前状态与短期快坏

这一节描述的是**同一模板上的多种标签口径**。
差异体现在 `Y` 的定义方式，不体现在 SQL 骨架是否更换。

### 3.1 路线总览

| 路线    | 核心目标          | 主要依赖字段                                                  | 适合任务               | 主要代价             |
| ----- | ------------- | ------------------------------------------------------- | ------------------ | ---------------- |
| 固定观察窗 | 预测固定未来窗口内的坏表现 | `perf_bad_flag`、`perf_max_dpd`、`perf_matured_flag`      | 准入、审批、标准风险模型       | 未成熟样本多，近期样本可用率下降 |
| 当前状态  | 表达当前时点风险状态    | `current_dpd`、`obs_hist_max_dpd`、`obs_already_bad_flag` | 当前名单治理、存量经营、当前经营筛客 | 不直接表达固定未来窗口风险    |
| 短期快坏  | 识别短期快速出险      | `perf_bad_flag` + 短窗口参数                                 | 快速放量前筛客、短期稳定性控制    | 中后期风险覆盖较弱        |

### 3.2 固定观察窗标签

#### 适用目标

* 申请前准入
* 授信前审批
* 标准评分卡
* 需要固定未来窗口标签的模型

#### 定义方式

* `obs_dt` 固定后
* 从 outcome-side 取固定表现期窗口
* 用 `perf_bad_flag`、`perf_max_dpd`、`perf_matured_flag` 生成 `Y`

#### 局部变量修改

**`6M / 30+`**

```sql
${perf_months} = 6
${bad_dpd_threshold} = 30
${good_clean_threshold} = 0
```

**`12M / 60+`**

```sql
${perf_months} = 12
${bad_dpd_threshold} = 60
${good_clean_threshold} = 0
```

#### 关键取舍

* **`6M / 30+`**：成熟快、样本量大、对早期快坏更敏感。
* **`12M / 60+`**：标签更稳、更接近强坏、中后期风险覆盖更完整。

---

### 3.3 当前状态与历史痕迹分层

#### 适用目标

* 当前名单治理
* 存量客户经营
* 代理样本构造
* 当前可经营性分层

#### 定义方式

* `obs_dt` 直接取当前最新快照时点
* 当前状态从 `CTE_Observation_Status` 中提取 `current_dpd`
* 历史痕迹从 `obs_hist_max_dpd`、`obs_hist_dpd_level` 中提取
* `CTE_Performance_Window` 退化为成熟度或辅助变量

#### 局部代码修改

**观察时点改为当前最新时点**

```sql
-- 在 CTE_Base_Population 中
obs_dt = to_date('${current_snapshot_dt}')
```

**在 `CTE_Observation_Status` 中计算 `current_dpd`**

```sql
max(CASE
    WHEN s.snapshot_dt = bp.obs_dt THEN coalesce(s.dpd_days, 0)
    ELSE 0
END) AS current_dpd
```

**保留历史痕迹分层**

```sql
CASE
    WHEN obs_hist_writeoff_flag = 1 OR obs_hist_max_dpd > 60 THEN 'EVER_60P'
    WHEN obs_hist_max_dpd > 30 THEN 'EVER_30_60P'
    WHEN obs_hist_max_dpd > 0 THEN 'EVER_1_30'
    ELSE 'NEVER_DPD'
END AS obs_hist_dpd_level
```

**将 `CTE_Performance_Window` 弱化为成熟度辅助层**

```sql
months_between(to_date('${current_snapshot_dt}'), loan_dt) AS mob_months
```

**将 `CTE_Final_Labeling` 改为状态分层**

```sql
CASE
    WHEN current_dpd > 60 THEN 'CUR_BAD_60P'
    WHEN current_dpd > 30 THEN 'CUR_BAD_30_60P'
    WHEN current_dpd > 0 THEN 'CUR_DPD_1_30'
    WHEN mob_months <= 6 THEN 'UNMATURE_LE_6M'
    WHEN current_dpd = 0 AND obs_hist_max_dpd = 0 THEN 'CUR_GOOD_HIST_CLEAN'
    WHEN current_dpd = 0 AND obs_hist_max_dpd > 0 AND obs_hist_max_dpd <= 30 THEN 'CUR_GOOD_HIST_EVER_1_30'
    WHEN current_dpd = 0 AND obs_hist_max_dpd > 30 AND obs_hist_max_dpd <= 60 THEN 'CUR_GOOD_HIST_EVER_30_60P'
    ELSE 'CUR_GOOD_HIST_EVER_60P'
END AS sample_type
```

#### 关键取舍

* 这类标签适合当前可经营性判断和代理样本构造。
* 这类标签表达的是 observation-side 分层结果。
* 这类标签不表达固定未来窗口的真实违约率。

---

### 3.4 短期快坏标签

#### 适用目标

* 快速放量前筛掉前期容易出险的人
* 预授信 / 营销名单的短期稳定性控制
* 关注放款后前几个月的风险暴露

#### 定义方式

* 仍然使用固定窗口骨架
* 缩短表现期
* 保留标准 `y=1 / 0 / NULL` 逻辑
* 强化近期样本成熟度截断

#### 局部变量修改

**`3M / 30+`**

```sql
${perf_months} = 3
${bad_dpd_threshold} = 30
${good_clean_threshold} = 0
```

**`6M / 30+`**

```sql
${perf_months} = 6
${bad_dpd_threshold} = 30
${good_clean_threshold} = 0
```

#### 关键取舍

* 对短期快坏最敏感。
* 样本成熟快，第一版更容易启动。
* 中后期风险覆盖较弱。
* 对训练集时间截断要求更高。

---

## 4. 样本主体与标签归属边界

### 4.1 样本主体如何选

样本主体由业务动作决定。

| 业务问题        | 推荐主体                                     |
| ----------- | ---------------------------------------- |
| 审批 / 准入     | `申请级` / `授信级`                            |
| 贷中预警        | `合同级` / `借据级`                            |
| 存量经营 / 名单圈选 | `party_id + feature_dt`                  |
| 多产品客户经营     | `party_id + obs_dt` 或 `party_id + month` |

### 4.2 `observation-side` 与 `outcome-side` 如何划分

| 类型                 | 典型字段                                                                         | 作用                  |
| ------------------ | ---------------------------------------------------------------------------- | ------------------- |
| `observation-side` | `current_dpd`、`obs_hist_max_dpd`、`obs_hist_dpd_level`、`obs_already_bad_flag` | 描述 `obs_dt` 及之前已知状态 |
| `outcome-side`     | `perf_max_dpd`、`perf_bad_flag`、`perf_matured_flag`                           | 描述 `obs_dt` 之后的表现结果 |

### 4.3 归属边界的使用原则

* 当前状态标签主要依赖 `observation-side`
* 固定观察窗标签主要依赖 `outcome-side`
* 代理标签通常同时使用两边信息，但需要明确其口径归属和业务用途
* `current_dpd` 属于观察时点当天状态，不属于表现期结果
* `perf_bad_flag` 属于观察时点之后的结果，不属于观察时点状态

---

## 5. 标签路线适配：修改哪些局部变量与代码块

### 5.1 固定观察窗标签时，修改哪些变量

#### 核心变量

* `${perf_months}`
* `${bad_dpd_threshold}`
* `${good_clean_threshold}`

#### 主要改动位置

* `CTE_Performance_Window`
* `CTE_Final_Labeling`

#### 示例

```sql
-- 12M / 60+
${perf_months} = 12
${bad_dpd_threshold} = 60
${good_clean_threshold} = 0
```

---

### 5.2 当前状态 / 代理标签时，修改哪些字段归属

#### 核心变量

* `obs_dt`
* `current_dpd`
* `obs_hist_max_dpd`
* `obs_hist_dpd_level`

#### 主要改动位置

* `CTE_Base_Population`
* `CTE_Observation_Status`
* `CTE_Final_Labeling`

#### 示例

```sql
-- 当前最新快照日
obs_dt = to_date('${current_snapshot_dt}')

-- observation-side 增加当前状态
max(CASE WHEN s.snapshot_dt = bp.obs_dt THEN coalesce(s.dpd_days, 0) ELSE 0 END) AS current_dpd
```

---

### 5.3 短期快坏标签时，调整哪些时间变量

#### 核心变量

* `${perf_months}`
* `${data_cutoff_dt}` 对应的时间截断策略
* `${bad_dpd_threshold}`

#### 主要改动位置

* `CTE_Performance_Window`
* 训练集圈样 SQL 的时间过滤条件

#### 示例

```sql
-- 6M / 30+
${perf_months} = 6
${bad_dpd_threshold} = 30
```

#### 配套要求

当标签使用短期窗口时，训练样本通常需要额外增加一层时间过滤，确保最近月份不因未成熟而大量缺失 `0` 样本。

---

## 6. 最终使用原则

### 6.1 核心 SQL 模板只有一套

文档中的 SQL 骨架始终固定为：

* `CTE_Base_Population`
* `CTE_Observation_Status`
* `CTE_Performance_Window`
* `CTE_Final_Labeling`

### 6.2 标签定义可以有多条路线

* 固定观察窗
* 当前状态
* 短期快坏

这些都属于同一套模板上的不同标签口径。

### 6.3 真正需要变化的维度

真正需要变化的是：

* 样本主体
* `obs_dt`
* `observation-side` 字段
* `outcome-side` 字段
* `CTE_Final_Labeling` 的 `CASE WHEN`

### 6.4 推荐使用顺序

1. 先确定**业务动作**
2. 再确定**样本主体**
3. 再确定**观察时点**
4. 再确定**标签路线**
5. 最后修改局部变量和 `CASE WHEN`

这套顺序能够稳定覆盖多数风控 Labeling 场景。
