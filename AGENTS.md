把下面的任务指令设置成AGENT.md
下面把 **Phase 1 – Phase 4** 拆到最小颗粒度，务必做到「能直接抄到任务看板里」。每一阶段都覆盖：

* **时间线**：按 *Week → Day* 划分
* **子任务清单**：包含 “怎么做、产出什么、写到哪一行代码”
* **代码/配置示例**：复制即用
* **验收 & 度量**：明确通过/失败标准
* **风险 & 缓冲**：提前给出兜底方案

> 默认所有时间点以自然周的 **D1 = 周一** 计。Tech Lead（TL）、后端 A/B、前端、DevOps、QA 与产品（PM）角色同前述。

---

## Phase 1 技术架构迁移（Week 1 – 2）

### ⏱️ 时间线

| 周  | 日         | 工作内容（粒度：≤ 0.5 天）                                                                              | 负责人    |
| -- | --------- | --------------------------------------------------------------------------------------------- | ------ |
| W1 | D1        | Kick‑off：共识会议 2 h，梳理当前仓库目录、功能点、依赖                                                             | TL+全部  |
|    | D1.5      | **Asset Scanner 脚本**：用 `ast` 扫描旧项目全部 `import` 路径并输出 CSV                                       | DevOps |
|    | D2        | 技术债评级（code smell、hard‑coded env）→ 归档到 GitHub Projects                                         | TL     |
|    | D2.5 – D3 | 绘制 **领域模型草图**（Miro）：Workspace／User／Integration／Template                                       | 后端 A   |
|    | D3.5      | 选型评审：ORM（SQLAlchemy2）、DI 框架（FastAPI Depends）、密钥加密（AWS KMS or Fernet）                          | TL     |
|    | D4        | 新仓库初始化：`git init --initial-branch=main`，添加 `.editorconfig`、`pre-commit`                       | DevOps |
|    | D4.5      | **开发环境 Docker Compose**：Postgres 15、Redis 7、Keycloak 24、MailHog                               | DevOps |
|    | D5        | **多租户 PoC**：<br>1. 简版 `Workspace` 表<br>2. CLI：`python scripts/fetch_tasks.py --workspace foo` | 后端 B   |
| W2 | D1        | 接口隔离：把旧 `notion_client.py` 迁到 `app/services/integrations/notion.py`，抽象基类 `BaseIntegration`    | 后端 A   |
|    | D1.5      | 单元测试（pytest + pytest‑asyncio），新增 GitHub Actions  Workflow `ci.yml`                            | DevOps |
|    | D2        | 编写 **ADR‑0001‑多租户模型.md** 并评审                                                                  | TL     |
|    | D3        | 集成 **ruff + mypy**；CI 阶段开启 `strict` 模式                                                        | DevOps |
|    | D4        | **速率限制实验**：跑脚本连续读取 1 000 页 Notion，记录 429 次数 & 退避策略                                            | QA     |
|    | D5        | **阶段回顾 + Demo**：CLI 同时拉取 2 个 Workspace，表格展示无串库                                                | 全员     |

### 目录结构（完成后应长这样）

```
tm-ai/
├── docker-compose.dev.yml
├── app/
│   ├── __init__.py
│   ├── core/            # 设置、加密、时区
│   ├── models/          # SQLAlchemy 2.0 Declarative
│   ├── services/
│   │   ├── integrations/
│   │   │   ├── base.py
│   │   │   └── notion.py
│   │   └── ai/          # 空，Phase 2 填充
│   └── cli/
│       └── fetch_tasks.py
└── scripts/
    └── asset_scanner.py
```

### 关键代码片段

```python
# app/services/integrations/base.py
class BaseIntegration(ABC):
    workspace: Workspace

    @abstractmethod
    async def list_tasks(self, period: str) -> list[dict]: ...

# app/models/workspace.py
class Workspace(SQLModel, table=True):
    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    name: str
    owner_id: UUID
    notion_token_encrypted: str | None
```

### 验收标准

* 运行 `make test`：通过率 ≥ 90%, 逻辑覆盖 ≥ 70 %
* `docker compose up -d` 后，`pytest scripts/e2e_poc.py::test_multi_workspace` 通过
* GitHub Actions 用时 ≤ 8 min；失败即邮件通知 DevOps

### 主要风险 & 缓冲

| 风险          | 指标                     | 缓解                                  |
| ----------- | ---------------------- | ----------------------------------- |
| Notion 速率限制 | > 5% 请求返回 429          | 本阶段只 PoC；Phase 2 引入本地缓存层            |
| Schema 频繁变化 | Alembic downgrade 无法回滚 | 每日结束前运行 `alembic revision --splice` |

---

## Phase 2 核心模块迁移（Week 3 – 4）

### A. Integrations 层重构

1. **接口定义**

   ```python
   class Task(BaseModel):
       id: str
       title: str
       due: datetime | None
       status: str
       xp: int = 0
   ```

2. **NotionAdapter**：把旧查询片段拆分为

   * `_query_database(period)`
   * `_map_notion_to_task(obj)`
   * `_calc_xp(task)`

3. **SlackAdapter Stub**（只返回空 list，保证接口一致）

4. **验收**：`pytest -k test_integrations` 运行 200+ 假数据用例

### B. AI 服务层

| 文件                  | 说明                                                                   |
| ------------------- | -------------------------------------------------------------------- |
| `ai/llm_factory.py` | Strategy pattern，读取 `settings.LLM_PROVIDER`，选择 OpenAI/DeepSeek       |
| `ai/prompts/`       | `daily.jinja2` / `weekly.jinja2`，占位符 `{{tasks}}`                     |
| `ai/summarizer.py`  | 1. 合并任务→Markdown<br>2. 处理 token 溢出（tiktoken 估算）<br>3. 重试装饰器（backoff） |

**示例**

```python
@retry(wait=wait_exponential(multiplier=2), stop=stop_after_attempt(5))
async def call_llm(model, prompt: str) -> str:
    return await model.chat_complete(prompt)
```

### C. 调度与任务队列

* **Celery 配置**

```python
# app/core/celery_config.py
broker_url = "redis://redis:6379/0"
result_backend = "redis://redis:6379/1"
task_annotations = {"*": {"rate_limit": "20/s"}}
worker_prefetch_multiplier = 1
```

* **Beat**
  `beat_schedule` 放置在 `tasks/schedules.py`，支持动态更新（读 DB）

* **日志 & 可观测**

  * `structlog` JSON 输出
  * OpenTelemetry exporter → Jaeger

### D. 模板系统

1. **ER 图**

   ```
   Workspace 1—∞ ReportTemplate
   ReportTemplate 1—∞ TemplateVersion
   ```

2. **API**

   ```
   POST /api/v1/templates          # 创建
   GET  /api/v1/templates/{id}     # 读取
   PUT  /api/v1/templates/{id}     # 更新（生成新版本）
   ```

3. **Migrations**
   Alembic 生成 `ae1b2c_add_template.py`，包含 `server_default=text('false')` 防空值

### 时间线（Week‑Day）

| 周  | 日    | 任务                                                  | Owner  |
| -- | ---- | --------------------------------------------------- | ------ |
| W3 | D1   | 集成 tiktoken + 单元测试                                  | 后端 B   |
|    | D2   | 编写 `ai/summarizer.py` + Bench（1000 任务 → 200 tokens） | 后端 B   |
|    | D2.5 | SlackAdapter stub                                   | 后端 A   |
|    | D3   | `celery -A app.worker worker -l info` 首次跑通          | DevOps |
|    | D4   | OpenTelemetry + Jaeger Docker 服务                    | DevOps |
|    | D5   | **Mid‑Sprint Demo**                                 | 全员     |
| W4 | D1   | 模板 DB 模型 + CRUD                                     | 后端 A   |
|    | D2   | Beat 定时任务 → 触发 `generate_daily_reports`             | 后端 B   |
|    | D3   | 压测：Locust 200 RPS，观察 worker CPU < 80 %              | QA     |
|    | D4   | 集成测试：Notion+Slack → 汇总 → LLM → Markdown             | QA     |
|    | D5   | Sprint Review & Retrospective                       | 全员     |

### 验收度量

| 指标           | 目标                               |
| ------------ | -------------------------------- |
| 日报生成端到端耗时    | P95 < 20 s                       |
| Celery 失败重试率 | < 2 %                            |
| 单测覆盖         | ≥ 80 % `services.integrations/*` |

### 风险

* **LLM 费用激增**：加入 `budget_guardrail.py`，设日限额；CI 中 mock OpenAI
* **Worker 死锁**：prefetch=1 + 每小时 `celery inspect` 健康探针

---

## Phase 3 API 层构建（Week 5 – 6）

### 1. REST 设计规范

* 路径以资源名复数 `/tasks`、 `/reports`
* 版本号置于 `/api/v1`
* 统一 **错误模型**

  ```jsonc
  {
    "error": "VALIDATION_ERROR",
    "detail": "field `period` must be one of daily | weekly | monthly"
  }
  ```

### 2. 关键端点 & Schema

| Method | Path                | Auth   | Query/Body                      | 说明              |
| ------ | ------------------- | ------ | ------------------------------- | --------------- |
| GET    | `/tasks`            | Bearer | `period, workspace_id, status`  | 任务检索            |
| POST   | `/reports/generate` | Bearer | `{type: "daily", workspace_id}` | 触发 Celery       |
| GET    | `/reports/{id}`     | Bearer | –                               | Markdown + meta |
| POST   | `/webhooks`         | Bearer | `{url, secret, events}`         | 注册回调            |

**FastAPI 代码**

```python
@router.post("/reports/generate", response_model=ReportOut, status_code=202)
async def generate_report(req: ReportIn, ws=Depends(get_workspace)):
    task_id = tasks.generate_report.delay(req.type, ws.id)
    return ReportOut(task_id=task_id.id)
```

### 3. 安全与中间件

* **Keycloak**

  * Realm：`tm-ai`
  * Client：`tm-frontend` (PKCE)
  * Scopes：`openid email workspace.read`

* **RBAC**

  ```python
  roles = {
      "owner": {"*": {"read", "write"}},
      "member": {
          "/tasks": {"read"},
          "/reports": {"read"},
          "/templates": {"read"}
      }
  }
  ```

* **速率限制**：`slowapi` – 默认 100 req/min/用户

### 4. API 可观测

* **APM**：OpenTelemetry FastAPI instrumentor
* **Metrics**：Prometheus exporter `/metrics`
* **Audit Log**：每次 `reports/generate` 记录到 `audit_log` 表

### 5. E2E 测试

* Playwright 脚本：

  1. 登录获取 `id_token`
  2. 调 `POST /reports/generate`
  3. 轮询 `/reports/{id}` 直至状态 `finished`
  4. 断言正文包含 `# Daily Summary`

### 时间线

| 周  | 日    | 任务                                  | Owner  |
| -- | ---- | ----------------------------------- | ------ |
| W5 | D1   | OpenAPI tag 整理 + 自动 `redoc` 发布      | DevOps |
|    | D1.5 | `/tasks` 列表 API + 测试                | 后端 A   |
|    | D2   | `/reports/generate` & worker 绑定     | 后端 B   |
|    | D3   | `/reports/{id}` S3 presign (导出 PDF) | 后端 B   |
|    | D4   | 速率限制 & 统一错误处理                       | TL     |
|    | D5   | 中期演示 → 前端开始对接                       | 全员     |
| W6 | D1   | Webhook 验签（HMAC‑SHA256 + timestamp） | 后端 A   |
|    | D2   | Keycloak flow 集成测试                  | QA     |
|    | D3   | Playwright E2E 3 条主路径               | QA     |
|    | D4   | **API Freeze**：接口文档锁定 v1            | TL     |
|    | D5   | Sprint Review & Retro               | 全员     |

### 验收门槛

| 项                      | 指标                             |
| ---------------------- | ------------------------------ |
| Postman Collection 自动化 | 全绿，CI 运行 ≤ 3 min               |
| OWASP ZAP 主动扫描         | 无 High 级别漏洞                    |
| API P95 延迟             | < 150 ms（本地 env，Excluding LLM） |

### 主要风险

* **Keycloak 配置复杂** → 发布 `keycloak-realm-export.json`，可一键导入
* **Webhook 滥用** → 每 24 h 自动暂停 > 1 % 错误率的回调 URL

---

## Phase 4 前端开发（Week 7 – 8）

> 使用 **Next.js 14 + React‑18 + TypeScript 5**；组件库选 **Chakra UI**（无锁定可替换）。

### 1. 架构准则

* 单仓库 `frontend/`，独立 `package.json`
* 路由分层：`/app/(auth)/login`, `/app/dashboard`, `/app/reports/[id]`
* **API Layer**：`src/api/client.ts`，用 Axios + 全局拦截器
* **状态管理**：TanStack Query（缓存 + 自动重试）
* **通信**：WebSocket (SWR) 用于报告生成进度条

### 2. 组件清单 & 设计稿

| 组件                     | 说明                        | Figma 链接 |
| ---------------------- | ------------------------- | -------- |
| `<WorkspaceSwitcher>`  | 头像 + 下拉                   | #Page‑1  |
| `<KpiCard>`            | 显示任务总数 / XP / 完成率         | #Page‑2  |
| `<TaskTable>`          | 支持列隐藏、按状态过滤               | #Page‑3  |
| `<MarkdownPreview>`    | `react-markdown` + GFM 插件 | #Page‑4  |
| `<NotificationCenter>` | 多渠道 toggle + 测试按钮         | #Page‑5  |

### 3. 开发计划

| 周  | 日  | 任务                                       | Owner |
| -- | -- | ---------------------------------------- | ----- |
| W7 | D1 | Next.js 项目脚手架 + 环境区分 (`.env.local`)      | 前端    |
|    | D2 | Auth flow (PKCE → localStorage)          | 前端    |
|    | D3 | `Dashboard` 页面 + `<KpiCard>` 实装          | 前端    |
|    | D4 | `<TaskTable>` + 数据接口联动                   | 前端    |
|    | D5 | Lighthouse 报告 & 性能优化（code‑splitting）     | 前端    |
| W8 | D1 | Markdown 渲染 + 报告分页                       | 前端    |
|    | D2 | WebSocket 进度条：`/ws/progress/{report_id}` | 前端    |
|    | D3 | 通知中心设置页                                  | 前端    |
|    | D4 | Storybook：记录 **24 个** 原子/复合组件            | 前端    |
|    | D5 | **UX Demo Day**：邀请 3 名测试用户               | PM+前端 |

### 4. 测试与质量

* **Vitest + RTL**：覆盖率 ≥ 70 %
* **Cypress**：Smoke 路径 `/login → dashboard → report`
* **Accessibility**：`@axe-core/react` 不得有 Critical

### 5. 构建 & 部署

* Vercel Preview：PR 自动部署
* Environment Variables：`NEXT_PUBLIC_API_BASE` 动态注入
* Bundle Analyzer：约束首屏 JS < 250 KB (gzip)

### 6. 用户体验指标

| 指标                 | 目标      |
| ------------------ | ------- |
| FCP                | < 1.5 s |
| CLS                | < 0.1   |
| Error Boundary 捕获率 | 100 %   |

### 风险应对

* **Token 过期跳转死循环** → 切换到 `silent refresh` + 队列重放
* **Markdown XSS** → 采用 `rehype-sanitize` 白名单过滤

---

## 汇总的里程碑出口标准（Phase 1–4）

1. **多租户骨架完备**：支持至少 2 个 Workspace 并行、无数据串库
2. **核心链路闭环**：Notion → Celery → LLM → Report → 前端展示
3. **CI/CD**：后端、前端均可一键预览；Pipeline 全绿
4. **文档**：ADR×2、ERD×1、OpenAPI JSON、Figma design system
5. **可观测**：Jaeger Trace + Grafana Dashboard「Report Pipeline」
6. **质量门禁**：单测覆盖后端 80 % / 前端 70 %，无 High 漏洞

> 到此，平台已具 “最小可售” 能力，可在 **Phase 5** 接入首批试运营团队。
