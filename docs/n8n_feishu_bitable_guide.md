# n8n + 飞书多维表格（Bitable）自动化流程配置文档

> 基于实际踩坑与调试过程整理，覆盖"自动创建字段 → 写入记录 → 错误隔离"完整链路。

---

## 一、问题背景

飞书多维表格（Bitable）的字段（列）**必须预先存在**，才能通过 API 写入数据。如果请求体里包含表格中不存在的字段名，飞书会返回 `1254045 FieldNameNotFound` 错误，且**整条记录都会被拒绝**（不存在"跳过错误字段继续写入其他字段"的机制）。

此外，社区节点 `n8n-nodes-feishu-lite` **不支持通过 API 创建字段**，因此需要借助 n8n 原生 **HTTP Request** 节点调用飞书开放平台接口，先自动创建缺失的字段，再写入记录。

---

## 二、完整工作流架构

```
[When clicking 'Execute workflow']  ← 手动触发（或换成你的触发器）
    ↓
[Code: 字段列表]                     ← 定义需要创建的字段名和类型
    ↓ (3 items)
[Loop Over Items]                    ← 逐个拆分，每次处理 1 个字段
    ↓ (loop)
[HTTP Request: 创建字段]             ← 调用 /fields 接口创建列
  Settings → On Error → Continue     ← 关键：字段已存在时不中断
    ↓
[If: 成功或已存在？]                 ← 判断 code==0 或 msg 包含"已存在"
    ├─ ✅ true  ─────────────────→ 回连 Loop Over Items（继续循环）
    └─ ❌ false ─────────────────→ 回连 Loop Over Items（或 Stop and Error）
    ↓ (done)
[Item Lists: Limit = 1]            ← 防止 done 出口携带多个 items 导致重复写入
    ↓ (1 item)
[feishu-lite / HTTP Request: 写入记录]  ← 写入行数据
```

---

## 三、节点详细配置

### 3.1 Code 节点（字段列表）

**用途：** 定义需要自动创建的字段，以及后续要写入的数据。

```javascript
// 字段创建列表
return [
  { json: { field_name: "用户编号", type: 1 } },
  { json: { field_name: "标题", type: 1 } },
  { json: { field_name: "内容", type: 1 } }
];
```

> `type: 1` 表示"多行文本"类型。常用类型对照见附录。

---

### 3.2 Loop Over Items 节点

| 配置项 | 值 |
|---|---|
| **Mode** | `Split In Batches` |
| **Batch Size** | `1` |

**连线方式：**
- **输入** ← Code 节点输出
- **loop 出口** → HTTP Request 节点
- **done 出口** → Item Lists 节点
- **HTTP → If → true/false** 均回连到 Loop Over Items **输入口**（形成循环）

---

### 3.3 HTTP Request 节点（创建字段）

| 配置项 | 值 |
|---|---|
| **Method** | `POST` |
| **URL** | `https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields` |
| **Authentication** | `None` |
| **Send Headers** | ✅ 开启 |
| **Headers** | `Authorization: Bearer {tenant_access_token}` |
| **Send Body** | ✅ 开启 |
| **Body Content Type** | `JSON` |
| **Specify Body** | **`Using JSON`** ⚠️ 绝对不能选 "Using Fields Below" |
| **Body (JSON)** | `{"field_name":"{{ $json.field_name }}","type":{{ $json.type }}}` |

> **注意：** `{{ $json.type }}` 外面**没有引号**，因为它是数字类型。

**Settings 标签页（关键）：**
| 配置项 | 值 |
|---|---|
| **On Error** | `Continue` 或 `Continue (using error output)` |

> 开启后，即使字段已存在报错，也不会中断整个工作流。

**如何获取 `app_token` 和 `table_id`：**
打开飞书多维表格，看浏览器地址栏：
```
https://xxx.feishu.cn/base/{app_token}?table={table_id}
```

---

### 3.4 IF 节点（判断循环是否继续）

**用途：** 区分"创建成功"、"字段已存在"和"其他错误"。

| 配置 | 值 |
|---|---|
| **条件组合** | `OR`（点击 "AND" 下拉框改成 "OR"） |
| **条件 1** | `{{ $json.code }}` `is equal to` `0` |
| **条件 2** | `{{ $json.msg }}` `contains` `已存在` |
| **条件 3** | `{{ $json.msg }}` `contains` `exists` |

**连线：**
- **true 出口** → 拖回 **Loop Over Items 输入口**
- **false 出口** → 拖回 **Loop Over Items 输入口**（先跑通）或接 **Stop and Error**（生产环境）

---

### 3.5 Item Lists 节点（去重防重入）

**用途：** Loop Over Items 的 `done` 出口会**原样输出所有原始 items**（例如 3 个），如果直接连到写入节点，会导致**同一条记录被重复写入 3 次**。

| 配置项 | 值 |
|---|---|
| **Operation** | `Limit` |
| **Limit** | `1` |

> 如果后续需要批量写入**多条不同数据**，则不需要此节点，改为在 Code 节点输出多条记录数据，让写入节点自动逐条执行。

---

### 3.6 写入记录节点（二选一）

#### 方案 A：feishu-lite 节点（简单）

| 配置 | 值 |
|---|---|
| **Resource** | `bitable` |
| **Operation** | `bitable:table:record:add` |
| **App** / **Table** | 选择你的多维表格 |
| **Fields** | 字段映射 |

**字段映射示例：**

| 字段名（必须与表格完全一致） | 值 |
|---|---|
| `文本` | `n8n主标题` |
| `用户编号` | `n8n001` |
| `标题` | `n8n测试` |
| `内容` | `n8n测试内容` |

> ⚠️ **第一列 `文本` 是主字段（带 🔒 图标），建议始终赋值，否则记录在其他视图/关联中可能显示为空白。**

#### 方案 B：HTTP Request 节点（支持错误隔离）

如果上游有多条记录，且希望**某一条写入失败时不影响其他正确的记录**，必须使用 HTTP Request 并开启 **Continue On Fail**。

| 配置项 | 值 |
|---|---|
| **Method** | `POST` |
| **URL** | `https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records` |
| **Headers** | `Authorization: Bearer {token}` |
| **Body (JSON)** | `{"fields":{"文本":"{{ $json.文本 }}","用户编号":"{{ $json.用户编号 }}","标题":"{{ $json.标题 }}","内容":"{{ $json.内容 }}"}}` |
| **Settings → On Error** | `Continue` |

后面同样接 **IF 节点**判断 `code == 0`，把成功和失败的记录分流处理（例如失败的发通知或写入错误日志表）。

---

## 四、关键注意事项

### 4.1 Body 格式是最大坑点

n8n HTTP Request 节点的 **"Specify Body"** 必须选择 **`Using JSON`**，并在文本框中填入完整 JSON：

```json
{"field_name":"用户编号","type":1}
```

❌ **错误做法：** 选择 "Using Fields Below"，然后填 Name/Value 列表。这会生成 `field_name=用户编号&type=1` 的表单数据，飞书 API 无法解析，会报 `99992402 field validation failed`。

### 4.2 字段名必须 100% 一致

飞书字段名**区分大小写、空格、全角/半角符号**。建议：
- 不要手打，从飞书表格表头**复制**字段名
- 或使用 **List Fields API** 查询真实的 `field_name`
- 第一列主字段默认叫 `文本`，不是 `id` 或 `标题`

### 4.3 创建字段 vs 写入记录是两套接口

| 操作 | 接口后缀 | Body 示例 |
|---|---|---|
| **创建字段**（加列） | `/fields` | `{"field_name":"标题","type":1}` |
| **写入记录**（加行） | `/records` | `{"fields":{"标题":"xxx"}}` |
| **批量写入** | `/records/batch_create` | `{"records":[{"fields":{...}},{"fields":{...}}]}` |

### 4.4 单条记录字段错误无法部分写入

如果一条记录里某个字段名不存在，飞书会**拒绝整条记录**，不会只跳过错误字段。这是飞书 API 的限制，不是 n8n 的问题。

---

## 五、常见问题速查

| 错误码/现象 | 原因 | 解决 |
|---|---|---|
| `1254045 FieldNameNotFound` | 请求中的字段名与表格实际字段名不匹配 | 核对表格字段名，确保完全一致 |
| `91402 NOTEXIST` | `app_token` 或 `table_id` 错误 | 从飞书 URL 中复制准确的参数 |
| `99992402 field validation failed` | Body 格式不是 JSON，或用了 "Using Fields Below" | 改成 "Using JSON" 模式 |
| `99991661 Missing access token` | 获取 token 的 URL 写错了，或 Headers 未开启 | 检查 URL 是 `/auth/...` 而非 `/bitable/...` |
| 记录重复写入 3 次 | Loop Over Items done 出口输出多个 items | 中间加 **Item Lists → Limit = 1** |
| 第一列始终为空 | 没映射主字段 `文本` | 在字段映射中加上 `文本` 字段 |
| 写入位置不在第 1 行 | 飞书 API 只支持**追加**到表格末尾 | 手动删除前面的空行，或接受追加行为 |

---

## 六、附录：飞书字段类型对照

| 字段类型 | type 值 |
|---|---|
| 多行文本 | `1` |
| 数字 | `2` |
| 单选 | `3` |
| 多选 | `4` |
| 日期 | `5` |
| 复选框 | `7` |
| 人员 | `11` |
| 附件 | `17` |
| 单向关联 | `18` |
| 双向关联 | `21` |
| 公式 | `20` |
| 自动编号 | `1005` |

---

## 七、获取 Tenant Access Token

如果 token 过期或需要自动化获取，单独配置一个 HTTP Request 节点：

| 配置 | 值 |
|---|---|
| **Method** | `POST` |
| **URL** | `https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal` |
| **Body (JSON)** | `{"app_id":"cli_xxx","app_secret":"xxx"}` |

返回结果中的 `tenant_access_token` 有效期约 2 小时，可在后续节点通过表达式 `{{ $json.tenant_access_token }}` 引用。
