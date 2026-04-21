# PySpark 常用导入

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import *
```

---

# 1. 创建 SparkSession

```python
spark = (
    SparkSession.builder
    .appName("demo_app")
    .enableHiveSupport()   # 如果需要读 hive 表
    .getOrCreate()
)
```

---

# 2. 读数据

## 2.1 读 Hive 表

```python
df = spark.table("dw.test_table")
df = spark.sql("""
    select *
    from dw.test_table
    where dt = '20260401'
""")
```

## 2.2 读 CSV

```python
df = (
    spark.read
    .option("header", True)
    .option("inferSchema", True)
    .csv("/path/to/file.csv")
)
```

## 2.3 读 Parquet

```python
df = spark.read.parquet("/path/to/file.parquet")
```

## 2.4 读 JSON

```python
df = spark.read.json("/path/to/file.json")
```

## 2.5 指定 Schema 读取

```python
schema = StructType([
    StructField("id", StringType(), True),
    StructField("age", IntegerType(), True),
    StructField("amount", DoubleType(), True),
])

df = (
    spark.read
    .schema(schema)
    .option("header", True)
    .csv("/path/to/file.csv")
)
```

---

# 3. 看数据

## 3.1 查看前几行

```python
df.show()
df.show(20, truncate=False)
```

## 3.2 看字段和类型

```python
df.printSchema()
print(df.columns)
print(df.dtypes)
```

## 3.3 行数

```python
df.count()
```

## 3.4 预览执行计划

```python
df.explain()
df.explain(True)
```

---

# 4. 选列

## 4.1 select

```python
df2 = df.select("id", "name", "age")
```

## 4.2 表达式选列

```python
df2 = df.select(
    "id",
    F.col("amount") * 1000,
    F.lit("A").alias("tag")
)
```

## 4.3 重命名列

```python
df2 = df.withColumnRenamed("old_name", "new_name")
```

## 4.4 批量改列名

```python
new_cols = [c.lower() for c in df.columns]
df2 = df.toDF(*new_cols)
```

---

# 5. 过滤

## 5.1 where / filter

```python
df2 = df.filter(F.col("age") >= 18)
df2 = df.where("age >= 18")
```

## 5.2 多条件

```python
df2 = df.filter(
    (F.col("age") >= 18) &
    (F.col("score") > 60)
)
```

## 5.3 isin

```python
df2 = df.filter(F.col("city").isin("深圳", "上海", "北京"))
```

## 5.4 like / rlike

```python
df2 = df.filter(F.col("name").like("%张%"))
df2 = df.filter(F.col("name").rlike("^张.*"))
```

## 5.5 空值过滤

```python
df2 = df.filter(F.col("id").isNotNull())
df2 = df.filter(F.col("id").isNull())
```

---

# 6. 新增列 / 修改列

## 6.1 withColumn

```python
df2 = df.withColumn("amount2", F.col("amount") * 2)
```

## 6.2 条件列 when / otherwise

```python
df2 = df.withColumn(
    "level",
    F.when(F.col("score") >= 90, "A")
     .when(F.col("score") >= 80, "B")
     .otherwise("C")
)
```

## 6.3 类型转换 cast

```python
df2 = df.withColumn("age", F.col("age").cast("int"))
df2 = df.withColumn("amount", F.col("amount").cast("double"))
```

## 6.4 截取 / 拼接字符串

```python
df2 = df.withColumn("prefix", F.substring("id", 1, 3))

df2 = df.withColumn(
    "full_name",
    F.concat_ws("-", F.col("first_name"), F.col("last_name"))
)
```

---

# 7. 排序

```python
df2 = df.orderBy("age")
df2 = df.orderBy(F.col("age").desc(), F.col("score").asc())
```

---

# 8. 去重

## 8.1 全表去重

```python
df2 = df.distinct()
```

## 8.2 指定列去重

```python
df2 = df.dropDuplicates(["id"])
df2 = df.dropDuplicates(["id", "dt"])
```

---

# 9. 聚合

## 9.1 groupBy + agg

```python
df2 = (
    df.groupBy("city")
      .agg(
          F.count("*").alias("row_cnt"),
          F.countDistinct("user_id").alias("user_cnt"),
          F.sum("amount").alias("amount_sum"),
          F.avg("amount").alias("amount_avg"),
          F.max("amount").alias("amount_max")
      )
)
```

## 9.2 直接聚合

```python
df2 = df.agg(
    F.count("*").alias("row_cnt"),
    F.sum("amount").alias("amount_sum")
)
```

---

# 10. join

## 10.1 inner join

```python
df3 = df1.join(df2, on="id", how="inner")
```

## 10.2 left join

```python
df3 = df1.join(df2, on="id", how="left")
```

## 10.3 多条件 join

```python
df3 = df1.alias("a").join(
    df2.alias("b"),
    on=[
        F.col("a.id") == F.col("b.id"),
        F.col("a.dt") == F.col("b.dt")
    ],
    how="left"
)
```

## 10.4 选 join 后的列，避免重名混乱

```python
df3 = (
    df1.alias("a")
    .join(df2.alias("b"), F.col("a.id") == F.col("b.id"), "left")
    .select(
        F.col("a.id"),
        F.col("a.name"),
        F.col("b.score").alias("score")
    )
)
```

## 10.5 广播小表

```python
from pyspark.sql.functions import broadcast

df3 = df_big.join(broadcast(df_small), on="id", how="left")
```

---

# 11. union

## 11.1 按列顺序 union

```python
df3 = df1.union(df2)
```

## 11.2 按列名 union

```python
df3 = df1.unionByName(df2)
```

## 11.3 允许缺列

```python
df3 = df1.unionByName(df2, allowMissingColumns=True)
```

---

# 12. null 处理

## 12.1 fillna

```python
df2 = df.fillna(0)
df2 = df.fillna({"age": 0, "name": "未知"})
```

## 12.2 dropna

```python
df2 = df.dropna()
df2 = df.dropna(subset=["id", "name"])
```

## 12.3 coalesce

```python
df2 = df.withColumn("name2", F.coalesce("name", "nickname", F.lit("未知")))
```

---

# 13. 时间处理

## 13.1 转日期

```python
df2 = df.withColumn("date1", F.to_date("date_str", "yyyy-MM-dd"))
df2 = df.withColumn("ts1", F.to_timestamp("ts_str", "yyyy-MM-dd HH:mm:ss"))
```

## 13.2 日期加减

```python
df2 = df.withColumn("next_day", F.date_add("date1", 1))
df2 = df.withColumn("prev_day", F.date_sub("date1", 1))
```

## 13.3 取年月日

```python
df2 = (
    df.withColumn("year", F.year("date1"))
      .withColumn("month", F.month("date1"))
      .withColumn("day", F.dayofmonth("date1"))
)
```

## 13.4 月初 / 月末

```python
df2 = df.withColumn("month_begin", F.trunc("date1", "month"))
df2 = df.withColumn("month_end", F.last_day("date1"))
```

## 13.5 日期差

```python
df2 = df.withColumn("days_diff", F.datediff("end_date", "start_date"))
```

---

# 14. 字符串处理

## 14.1 trim / upper / lower

```python
df2 = (
    df.withColumn("name_trim", F.trim("name"))
      .withColumn("name_upper", F.upper("name"))
      .withColumn("name_lower", F.lower("name"))
)
```

## 14.2 replace

```python
df2 = df.withColumn("mobile2", F.regexp_replace("mobile", "-", ""))
```

## 14.3 split

```python
df2 = df.withColumn("arr", F.split("tag_str", ","))
```

## 14.4 长度

```python
df2 = df.withColumn("name_len", F.length("name"))
```

---

# 15. 条件判断与 SQL 风格表达式

## 15.1 expr

```python
df2 = df.withColumn("flag", F.expr("case when score >= 60 then 1 else 0 end"))
```

## 15.2 多条件逻辑

```python
df2 = df.withColumn(
    "label",
    F.when((F.col("age") >= 18) & (F.col("score") >= 60), "pass")
     .otherwise("reject")
)
```

---

# 16. 窗口函数

这个很常用，尤其是去重、取最新一条、组内排序。

## 16.1 row_number

```python
w = Window.partitionBy("user_id").orderBy(F.col("dt").desc())

df2 = df.withColumn("rn", F.row_number().over(w))
df_latest = df2.filter(F.col("rn") == 1).drop("rn")
```

## 16.2 rank / dense_rank

```python
w = Window.partitionBy("group_id").orderBy(F.col("score").desc())

df2 = (
    df.withColumn("rk", F.rank().over(w))
      .withColumn("drk", F.dense_rank().over(w))
)
```

## 16.3 组内累计

```python
w = (
    Window.partitionBy("user_id")
    .orderBy("dt")
    .rowsBetween(Window.unboundedPreceding, Window.currentRow)
)

df2 = df.withColumn("cum_amt", F.sum("amount").over(w))
```

## 16.4 lag / lead

```python
w = Window.partitionBy("user_id").orderBy("dt")

df2 = (
    df.withColumn("prev_amt", F.lag("amount", 1).over(w))
      .withColumn("next_amt", F.lead("amount", 1).over(w))
)
```

---

# 17. pivot

```python
df2 = (
    df.groupBy("user_id")
      .pivot("month")
      .agg(F.sum("amount"))
)
```

---

# 18. array / map 常用操作

## 18.1 explode

```python
df2 = df.withColumn("item", F.explode("arr_col"))
```

## 18.2 size

```python
df2 = df.withColumn("arr_size", F.size("arr_col"))
```

## 18.3 array_contains

```python
df2 = df.filter(F.array_contains("arr_col", "A"))
```

---

# 19. 样本抽样

## 19.1 sample

```python
df_sample = df.sample(withReplacement=False, fraction=0.1, seed=42)
```

## 19.2 limit

```python
df_small = df.limit(1000)
```

---

# 20. 分区相关

## 20.1 repartition

```python
df2 = df.repartition(100)
df2 = df.repartition(100, "dt")
```

## 20.2 coalesce

```python
df2 = df.coalesce(10)
```

区别很简单：

* `repartition`：会触发 shuffle，适合重新均匀分布
* `coalesce`：通常用于减少分区，代价更小

---

# 21. cache / persist

```python
df.cache()
df.count()   # 触发一次执行，真正缓存

# 或者
from pyspark import StorageLevel
df.persist(StorageLevel.MEMORY_AND_DISK)
df.count()

df.unpersist()
```

---

# 22. 写数据

## 22.1 写 Parquet

```python
(
    df.write
    .mode("overwrite")
    .parquet("/path/to/output")
)
```

## 22.2 写 CSV

```python
(
    df.write
    .mode("overwrite")
    .option("header", True)
    .csv("/path/to/output_csv")
)
```

## 22.3 写 Hive 表

```python
(
    df.write
    .mode("overwrite")
    .saveAsTable("app.tmp_table")
)
```

## 22.4 分区写入

```python
(
    df.write
    .mode("overwrite")
    .partitionBy("dt")
    .format("parquet")
    .save("/path/to/output")
)
```

## 22.5 insertInto 已有 Hive 分区表

```python
spark.sql("set hive.exec.dynamic.partition=true")
spark.sql("set hive.exec.dynamic.partition.mode=nonstrict")

(
    df.write
    .mode("overwrite")
    .insertInto("app.target_table")
)
```

---

# 23. UDF

一般来说，**能不用 UDF 就不用**，优先用内置函数。
因为 UDF 往往更慢，也更不利于优化。

## 23.1 普通 UDF

```python
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

@udf(StringType())
def to_upper_py(x):
    if x is None:
        return None
    return x.upper()

df2 = df.withColumn("name2", to_upper_py("name"))
```

---

# 24. 常见实用代码块

## 24.1 按主键取最新一条

```python
w = Window.partitionBy("id").orderBy(F.col("update_time").desc())

df_latest = (
    df.withColumn("rn", F.row_number().over(w))
      .filter(F.col("rn") == 1)
      .drop("rn")
)
```

## 24.2 统计每列空值数

```python
null_stat = df.select([
    F.sum(F.when(F.col(c).isNull(), 1).otherwise(0)).alias(c)
    for c in df.columns
])

null_stat.show(truncate=False)
```

## 24.3 统计每列去重数

```python
distinct_stat = df.select([
    F.countDistinct(F.col(c)).alias(c)
    for c in df.columns
])

distinct_stat.show(truncate=False)
```

## 24.4 批量转字符串

```python
df2 = df.select([
    F.col(c).cast("string").alias(c)
    for c in df.columns
])
```

## 24.5 批量 trim 字符串列

```python
string_cols = [c for c, t in df.dtypes if t == "string"]

df2 = df.select([
    F.trim(F.col(c)).alias(c) if c in string_cols else F.col(c)
    for c in df.columns
])
```

## 24.6 join 后查看匹配率

```python
df_join = df_a.join(df_b.select("id").distinct(), on="id", how="left")

match_stat = df_join.select(
    F.count("*").alias("row_cnt"),
    F.sum(F.when(F.col("id").isNotNull(), 1).otherwise(0)).alias("matched_row_cnt")
)

match_stat.show()
```

更严谨一点，通常会在右表加标记列：

```python
df_b_tag = df_b.select("id").distinct().withColumn("is_match", F.lit(1))

df_join = df_a.join(df_b_tag, on="id", how="left")

df_join.select(
    F.count("*").alias("row_cnt"),
    F.sum(F.when(F.col("is_match") == 1, 1).otherwise(0)).alias("matched_cnt")
).show()
```

## 24.7 按分组统计 Top1 占比

```python
df_stat = (
    df.groupBy("feature")
      .count()
      .withColumn(
          "rn",
          F.row_number().over(Window.partitionBy().orderBy(F.col("count").desc()))
      )
)
```

如果是每个字段内部的 Top1 占比，一般要先转成长表再算。

---

# 25. SQL 和 DataFrame 混用

很多时候 DataFrame 和 SQL 混着写最顺手。

## 25.1 注册临时表

```python
df.createOrReplaceTempView("tmp_df")
```

## 25.2 用 SQL 查询

```python
result = spark.sql("""
    select city, count(*) as cnt
    from tmp_df
    group by city
""")
```

---

# 26. 常见坑

## 26.1 and / or 不能直接用

错：

```python
df.filter(F.col("age") > 18 and F.col("score") > 60)
```

对：

```python
df.filter((F.col("age") > 18) & (F.col("score") > 60))
```

## 26.2 列运算要用 F.col

错：

```python
df.withColumn("x", "amount" * 2)
```

对：

```python
df.withColumn("x", F.col("amount") * 2)
```

## 26.3 join 后重名列容易乱

join 后尽量：

* 先 `alias`
* 再 `select`
* 不要直接 `select("*")`

## 26.4 count 很贵

```python
df.count()
```

这是全表 action，大表上很慢。不要没事就跑。

## 26.5 collect 风险大

```python
rows = df.collect()
```

全量拉到 driver，数据一大就爆。
大表不要轻易 `collect()`，最多 `limit().collect()`。

---

# 27. 一个完整小例子

下面这个例子把几个常用动作串起来：读表、过滤、取最新、聚合、写表。

```python
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import Window

spark = (
    SparkSession.builder
    .appName("demo_pipeline")
    .enableHiveSupport()
    .getOrCreate()
)

# 1）读取原表
df = spark.table("dw.user_order_detail")

# 2）筛选有效数据
df1 = (
    df.filter(F.col("dt") >= "20260101")
      .filter(F.col("status") == "success")
      .filter(F.col("user_id").isNotNull())
)

# 3）每个用户取最新一笔订单
w = Window.partitionBy("user_id").orderBy(F.col("order_time").desc())

df_latest = (
    df1.withColumn("rn", F.row_number().over(w))
       .filter(F.col("rn") == 1)
       .drop("rn")
)

# 4）按城市聚合
df_stat = (
    df_latest.groupBy("city")
             .agg(
                 F.countDistinct("user_id").alias("user_cnt"),
                 F.sum("amount").alias("amount_sum"),
                 F.avg("amount").alias("amount_avg")
             )
)

# 5）写出结果
(
    df_stat.write
    .mode("overwrite")
    .saveAsTable("app.user_order_city_stat")
)
```

---

# 28. 最常用的一批方法，记住这些基本就够干活了

如果只保留最核心的一批，通常就是这些：

```python
select
withColumn
withColumnRenamed
filter / where
groupBy + agg
join
dropDuplicates
orderBy
unionByName
fillna
cast
when / otherwise
row_number over window
countDistinct
createOrReplaceTempView
spark.sql
write.saveAsTable
```

---