from __future__ import annotations

import html
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Mapping, Optional, Sequence
from urllib.parse import parse_qs, urlencode, urlparse

import pytz

from .coaching_modes import available_mode_keys, resolve_mode
from .config import Config
from .engine_state import EngineStateStore
from .focus_profile import FocusProfileStore
from .models import TaskAlias, TaskRecord
from .review_memory import ReviewMemoryStore
from .sqlite_task_store import SQLiteTaskStore

DEFAULT_CATEGORIES = (
    "Content",
    "Study",
    "Work",
    "Health",
    "Life",
    "Admin",
)


@dataclass
class DashboardSnapshot:
    current_focus: str
    current_stage: str
    coaching_mode_key: str
    coaching_mode_name: str
    coaching_notes: str
    next_action: str
    latest_preview: str
    latest_generated_at: str
    is_dormant: bool
    last_active_date: str
    dormant_since: str
    last_restart_nudge_date: str
    tasks_today: int
    tasks_last_7_days: int
    minutes_last_7_days: int
    manual_alias_count: int


def build_capture_page(
    tasks: Sequence[TaskRecord],
    timezone: str,
    message: str = "",
    host: str = "127.0.0.1",
    port: int = 8765,
    form_values: Optional[Mapping[str, str]] = None,
    form_mode: str = "create",
    active_task_id: str = "",
    manual_aliases: Optional[Sequence[TaskAlias]] = None,
    active_alias_id: str = "",
    dashboard: Optional[DashboardSnapshot] = None,
) -> str:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    values = _merge_form_values(timezone, form_values)
    manual_alias_markup = "\n".join(
        _render_manual_alias_card(alias, active_alias_id=active_alias_id)
        for alias in (manual_aliases or [])
    ) or "<span class='muted-inline'>先存一个手工别名，常用动作以后就能一键装进表单。</span>"
    alias_chips = "\n".join(
        _render_alias_chip(entry["task"], str(entry["alias"]), count=int(entry["count"]))
        for entry in _build_task_aliases(tasks)
    ) or "<span class='muted-inline'>常做的动作会自动长成别名按钮。</span>"
    recent_category_chips = "\n".join(
        _render_quick_chip(category, "category", variant="memory")
        for category in _recent_category_memory(tasks)
    ) or "<span class='muted-inline'>先记几条，最近分类会自动浮出来。</span>"
    category_chips = "\n".join(_render_quick_chip(category, "category") for category in _category_options(tasks, values["category"]))
    recent_template_chips = "\n".join(_render_template_chip(task) for task in tasks[:6]) or "<span class='muted-inline'>最近还没有可复用模板</span>"
    favorite_template_chips = "\n".join(
        _render_template_chip(entry["task"], count=entry["count"], variant="favorite")
        for entry in _build_favorite_templates(tasks)
    ) or "<span class='muted-inline'>先多记几次，系统就会把高频动作提炼成模板。</span>"
    latest_timing_chip = _render_time_preset_chip(_build_latest_timing_preset(tasks, timezone))
    latest_variant_chip = _render_variant_chip(_build_latest_variant_task(tasks))
    dashboard_markup = _render_dashboard(dashboard) if dashboard else ""
    focus_console_markup = _render_focus_console(dashboard) if dashboard else ""
    task_rows = "\n".join(_render_task_row(task, tz, active_task_id=active_task_id) for task in tasks) or (
        "<tr><td colspan='6' class='empty'>最近还没有已完成任务</td></tr>"
    )
    message_html = f"<div class='flash'>{html.escape(message)}</div>" if message else ""
    submit_label = "保存修改" if values["task_id"] else "记录完成任务"
    mode_label = {
        "edit": "编辑模式",
        "alias": "别名模式",
        "manual_alias_edit": "手工别名编辑",
        "manual_alias_use": "手工别名",
        "reuse": "复用模式",
        "variant": "变体模式",
    }.get(form_mode, "快速记录")
    mode_hint = {
        "edit": "你正在修改一条已有任务，保存后会直接覆盖原记录。",
        "alias": "你是从常用别名进来的，保留主结构，直接改成这次的具体内容就行。",
        "manual_alias_edit": "你现在改的是一条手工别名，保存别名后它会成为长期快捷入口。",
        "manual_alias_use": "这条手工别名已经载入，你可以直接记这次完成，也可以顺手调整别名本身。",
        "reuse": "最近任务已经载入表单，你可以改几处再保存成新记录。",
        "variant": "系统已经把上一条搬过来当起点，你只需要改出这次的变体。",
    }.get(form_mode, "只记完成，不做任务管理。把今天真正做完的事写进来就够了。")
    reset_link = "<a class='subtle-link' href='/'>清空表单</a>" if values["task_id"] or values["alias_id"] or form_mode in {"reuse", "variant", "alias", "manual_alias_use"} else ""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bear Review Capture</title>
  <style>
    :root {{
      --bg: #f6f3ee;
      --panel: rgba(255, 252, 247, 0.92);
      --ink: #1c1917;
      --muted: #57534e;
      --line: #d6d3d1;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --accent-soft: #ccfbf1;
      --danger: #b91c1c;
      --danger-soft: #fee2e2;
      --shadow: 0 18px 50px rgba(28, 25, 23, 0.08);
      --radius: 20px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "SF Pro Text", "PingFang SC", "Noto Sans SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.14), transparent 35%),
        linear-gradient(180deg, #fbf9f4 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 46px);
      line-height: 1.05;
      letter-spacing: -0.03em;
    }}
    h2 {{
      margin: 0;
      font-size: 22px;
    }}
    .sub {{
      color: var(--muted);
      max-width: 760px;
      font-size: 16px;
      line-height: 1.6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
      gap: 20px;
      align-items: start;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid rgba(214, 211, 209, 0.8);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 22px;
      backdrop-filter: blur(12px);
    }}
    .flash {{
      margin-bottom: 16px;
      padding: 12px 14px;
      border-radius: 14px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      font-size: 14px;
      font-weight: 600;
    }}
    .dashboard-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .dashboard-card {{
      display: grid;
      gap: 10px;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .hero-value {{
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: -0.03em;
      font-weight: 700;
    }}
    .dashboard-copy {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .metric {{
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.82);
      border: 1px solid rgba(214, 211, 209, 0.7);
      padding: 12px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .metric-value {{
      margin-top: 6px;
      font-size: 20px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .metric-sub {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(214, 211, 209, 0.8);
      font-size: 12px;
      font-weight: 700;
      width: fit-content;
      background: #fff;
    }}
    .status-pill.is-dormant {{
      color: #92400e;
      background: #fef3c7;
      border-color: rgba(217, 119, 6, 0.2);
    }}
    .status-pill.is-active {{
      color: var(--accent-strong);
      background: rgba(204, 251, 241, 0.7);
      border-color: rgba(15, 118, 110, 0.2);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 18px;
    }}
    .chip {{
      border-radius: 999px;
      background: #ffffff;
      border: 1px solid var(--line);
      padding: 6px 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .section-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .section-note {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 18px;
    }}
    form {{
      display: grid;
      gap: 14px;
    }}
    .row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
      font-weight: 600;
    }}
    input, select, textarea, button {{
      font: inherit;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(255, 255, 255, 0.95);
      color: var(--ink);
    }}
    textarea {{
      min-height: 92px;
      resize: vertical;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 14px 18px;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: white;
      font-weight: 700;
      cursor: pointer;
    }}
    .quick-block {{
      display: grid;
      gap: 10px;
      margin-bottom: 16px;
    }}
    .quick-title {{
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .quick-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .quick-btn, .template-link, .subtle-link, .link-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      padding: 8px 12px;
      font-size: 13px;
      line-height: 1.2;
    }}
    .quick-btn.is-accent {{
      border-color: rgba(15, 118, 110, 0.24);
      background: var(--accent-soft);
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .quick-btn.is-memory {{
      border-color: rgba(17, 94, 89, 0.16);
      background: rgba(255, 255, 255, 0.92);
      color: var(--accent-strong);
    }}
    .quick-btn.is-ghost, .subtle-link, .link-btn {{
      background: transparent;
      color: var(--muted);
    }}
    .link-btn {{
      padding: 6px 10px;
    }}
    .link-btn.is-danger {{
      border-color: rgba(185, 28, 28, 0.16);
      color: var(--danger);
      background: var(--danger-soft);
    }}
    .template-link {{
      max-width: 100%;
    }}
    .template-link.is-favorite {{
      border-color: rgba(15, 118, 110, 0.24);
      background: rgba(204, 251, 241, 0.55);
    }}
    .template-link.is-alias {{
      border-color: rgba(17, 94, 89, 0.18);
      background: rgba(240, 253, 250, 0.95);
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .template-link.is-manual {{
      border-color: rgba(15, 118, 110, 0.28);
      background: rgba(240, 253, 250, 0.92);
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .template-link span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 220px;
    }}
    .template-link b {{
      margin-right: 6px;
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .template-link em {{
      margin-left: 6px;
      font-style: normal;
      font-size: 12px;
      color: var(--muted);
    }}
    .manual-aliases {{
      display: grid;
      gap: 10px;
    }}
    .alias-card {{
      display: grid;
      gap: 8px;
      padding: 12px;
      border-radius: 16px;
      border: 1px solid rgba(214, 211, 209, 0.85);
      background: rgba(255, 255, 255, 0.72);
    }}
    .alias-card.is-active {{
      border-color: rgba(15, 118, 110, 0.28);
      background: rgba(204, 251, 241, 0.36);
    }}
    .alias-meta {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .secondary-button {{
      border: 1px solid rgba(15, 118, 110, 0.2);
      background: rgba(255, 255, 255, 0.82);
      color: var(--accent-strong);
    }}
    .focus-form {{
      margin-bottom: 20px;
    }}
    .submit-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .muted-inline {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 12px 0;
      border-bottom: 1px solid rgba(214, 211, 209, 0.7);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .inline-form {{
      margin: 0;
    }}
    .task-cell strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .task-note {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    td[data-label]::before {{
      content: attr(data-label);
      display: none;
    }}
    .row-active td {{
      background: rgba(15, 118, 110, 0.08);
    }}
    .empty {{
      color: var(--muted);
      padding: 18px 0 6px;
    }}
    .hint {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    code {{
      font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
    }}
    @media (max-width: 960px) {{
      .dashboard-grid {{
        grid-template-columns: 1fr;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .wrap {{
        padding: 18px 12px 26px;
      }}
      .hero {{
        margin-bottom: 16px;
      }}
      .card {{
        padding: 16px;
        border-radius: 18px;
      }}
      .hero-value {{
        font-size: 22px;
      }}
      .metric-row {{
        grid-template-columns: 1fr 1fr;
      }}
      .sub {{
        font-size: 14px;
      }}
      .row {{
        grid-template-columns: 1fr;
      }}
      .section-head {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .quick-row {{
        gap: 6px;
      }}
      .quick-btn, .template-link, .subtle-link, .link-btn {{
        min-height: 38px;
        padding: 8px 11px;
      }}
      table, thead, tbody {{
        display: block;
      }}
      thead {{
        display: none;
      }}
      tbody {{
        display: grid;
        gap: 12px;
      }}
      tr {{
        display: grid;
        gap: 6px;
        padding: 12px;
        border: 1px solid rgba(214, 211, 209, 0.7);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
      }}
      td {{
        display: block;
        border-bottom: 0;
        padding: 0;
      }}
      td[data-label]::before {{
        display: block;
        margin-bottom: 2px;
        color: var(--muted);
        font-size: 11px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      .template-link span {{
        max-width: 160px;
      }}
      .actions {{
        gap: 6px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Bear Review Capture</h1>
      <div class="sub">这里不是另一个 Notion。你只需要记下已经完成的事，剩下的复盘、教练模式、自动熄火和提醒系统继续用原来的引擎。</div>
    </section>
    {dashboard_markup}
    {focus_console_markup}
    <div class="grid">
      <section class="card">
        {message_html}
        <div class="meta">
          <span class="chip">本地地址 http://{html.escape(host)}:{port}</span>
          <span class="chip">数据库 .bear_review/tasks.db</span>
          <span class="chip">当前时间 {now.strftime("%Y-%m-%d %H:%M")}</span>
          <span class="chip">{html.escape(mode_label)}</span>
        </div>
        <div class="section-head">
          <h2>快速记录</h2>
          {reset_link}
        </div>
        <div class="section-note">{html.escape(mode_hint)}</div>
        <div class="quick-block">
          <div class="quick-title">手工别名</div>
          <div class="manual-aliases">
            {manual_alias_markup}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">常用别名</div>
          <div class="quick-row">
            {alias_chips}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">最近分类</div>
          <div class="quick-row">
            {recent_category_chips}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">常用分类</div>
          <div class="quick-row">
            {category_chips}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">快捷动作</div>
          <div class="quick-row">
            <button type="button" class="quick-btn is-accent" data-fill="priority" data-value="MIT">一键 MIT</button>
            <button type="button" class="quick-btn" data-fill="priority" data-value="重要">标记重要</button>
            <button type="button" class="quick-btn" data-fill="priority" data-value="">清空优先级</button>
            <button type="button" class="quick-btn is-ghost" data-fill="minutes" data-value="25">25 分钟</button>
            <button type="button" class="quick-btn is-ghost" data-fill="minutes" data-value="50">50 分钟</button>
            <button type="button" class="quick-btn is-ghost" data-action="set-today">今天</button>
            <button type="button" class="quick-btn is-ghost" data-action="set-now-start">现在开始</button>
            <button type="button" class="quick-btn is-ghost" data-action="sync-end">结束=开始+时长</button>
            <button type="button" class="quick-btn is-ghost" data-action="clear-end">清空结束</button>
            {latest_timing_chip}
            {latest_variant_chip}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">高频模板</div>
          <div class="quick-row">
            {favorite_template_chips}
          </div>
        </div>
        <div class="quick-block">
          <div class="quick-title">最近模板</div>
          <div class="quick-row">
            {recent_template_chips}
          </div>
        </div>
        <form method="post" action="/">
          <input type="hidden" name="task_id" value="{_escape_attr(values['task_id'])}">
          <input type="hidden" name="alias_id" value="{_escape_attr(values['alias_id'])}">
          <input type="hidden" name="return_to" value="{_escape_attr(values['return_to'])}">
          <div class="row">
            <label>
              手工别名名
              <input type="text" name="alias_name" value="{_escape_attr(values['alias_name'])}" placeholder="例如：视频粗剪 / 审计复盘">
            </label>
            <label>
              别名说明
              <input type="text" name="alias_note" value="{_escape_attr(values['alias_note'])}" placeholder="给未来的自己留个提示">
            </label>
          </div>
          <label>
            任务名称
            <input type="text" name="title" value="{_escape_attr(values['title'])}" placeholder="例如：剪完第一条视频" required>
          </label>
          <div class="row">
            <label>
              分类
              <input type="text" name="category" value="{_escape_attr(values['category'])}" placeholder="例如：Content / Study / Work">
            </label>
            <label>
              优先级
              <select name="priority">
                {_priority_option("", "无优先级", values["priority"])}
                {_priority_option("MIT", "MIT", values["priority"])}
                {_priority_option("重要", "重要", values["priority"])}
                {_priority_option("次要", "次要", values["priority"])}
              </select>
            </label>
          </div>
          <div class="row">
            <label>
              日期
              <input type="date" name="task_date" value="{_escape_attr(values['task_date'])}">
            </label>
            <label>
              开始时间
              <input type="time" name="start" value="{_escape_attr(values['start'])}">
            </label>
          </div>
          <div class="row">
            <label>
              用时（分钟）
              <input type="number" name="minutes" value="{_escape_attr(values['minutes'])}" min="0">
            </label>
            <label>
              番茄数
              <input type="number" name="tomatoes" value="{_escape_attr(values['tomatoes'])}" min="0">
            </label>
          </div>
          <div class="row">
            <label>
              XP
              <input type="number" name="xp" value="{_escape_attr(values['xp'])}" placeholder="留空时自动按优先级估算" min="0">
            </label>
            <label>
              结束时间
              <input type="time" name="end" value="{_escape_attr(values['end'])}">
            </label>
          </div>
          <label>
            备注
            <textarea name="note" placeholder="例如：这次主要卡在封面和字幕。">{html.escape(values['note'])}</textarea>
          </label>
          <div class="submit-row">
            <button type="submit" name="action" value="save">{submit_label}</button>
            <button type="submit" name="action" value="save_alias" class="secondary-button">保存为手工别名</button>
            <span class="muted-inline">保存后会直接进入 SQLite，本地复盘和自动熄火都会继续使用这份数据。</span>
          </div>
        </form>
        <div class="hint">如果你想用手机录入，把服务启动成 <code>--host 0.0.0.0</code>，然后在同一局域网里访问它。</div>
      </section>
      <section class="card">
        <div class="section-head">
          <h2>最近完成</h2>
          <span class="muted-inline">可直接复用、编辑、删除</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>任务</th>
              <th>分类</th>
              <th>优先级</th>
              <th>效率</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {task_rows}
          </tbody>
        </table>
      </section>
    </div>
  </div>
  <script>
    document.querySelectorAll("[data-fill]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const targetName = button.getAttribute("data-fill");
        const target = document.querySelector(`[name="${{targetName}}"]`);
        if (!target) {{
          return;
        }}
        target.value = button.getAttribute("data-value") || "";
        target.dispatchEvent(new Event("change"));
        if (targetName === "category") {{
          const titleInput = document.querySelector('[name="title"]');
          if (titleInput && !titleInput.value) {{
            titleInput.focus();
          }}
        }}
      }});
    }});

    const pad = (value) => String(value).padStart(2, "0");
    const setCurrentDate = () => {{
      const now = new Date();
      const dateInput = document.querySelector('[name="task_date"]');
      if (dateInput) {{
        dateInput.value = `${{now.getFullYear()}}-${{pad(now.getMonth() + 1)}}-${{pad(now.getDate())}}`;
      }}
    }};
    const setCurrentTime = () => {{
      const now = new Date();
      const startInput = document.querySelector('[name="start"]');
      if (startInput) {{
        startInput.value = `${{pad(now.getHours())}}:${{pad(now.getMinutes())}}`;
      }}
    }};
    const syncEndTime = () => {{
      const startInput = document.querySelector('[name="start"]');
      const minutesInput = document.querySelector('[name="minutes"]');
      const endInput = document.querySelector('[name="end"]');
      if (!startInput || !minutesInput || !endInput || !startInput.value) {{
        return;
      }}
      const [hour, minute] = startInput.value.split(":").map(Number);
      const duration = Number(minutesInput.value || 0);
      const current = new Date();
      current.setHours(hour || 0, minute || 0, 0, 0);
      current.setMinutes(current.getMinutes() + duration);
      endInput.value = `${{pad(current.getHours())}}:${{pad(current.getMinutes())}}`;
    }};
    const copyLastTiming = (button) => {{
      const startInput = document.querySelector('[name="start"]');
      const endInput = document.querySelector('[name="end"]');
      const minutesInput = document.querySelector('[name="minutes"]');
      const tomatoesInput = document.querySelector('[name="tomatoes"]');
      const dateInput = document.querySelector('[name="task_date"]');
      if (dateInput) {{
        setCurrentDate();
      }}
      if (startInput) {{
        startInput.value = button.getAttribute("data-preset-start") || "";
      }}
      if (endInput) {{
        endInput.value = button.getAttribute("data-preset-end") || "";
      }}
      if (minutesInput) {{
        minutesInput.value = button.getAttribute("data-preset-minutes") || minutesInput.value;
      }}
      if (tomatoesInput) {{
        tomatoesInput.value = button.getAttribute("data-preset-tomatoes") || tomatoesInput.value;
      }}
    }};
    document.querySelectorAll("[data-action]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const action = button.getAttribute("data-action");
        if (action === "set-today") {{
          setCurrentDate();
        }} else if (action === "set-now-start") {{
          setCurrentDate();
          setCurrentTime();
        }} else if (action === "sync-end") {{
          syncEndTime();
        }} else if (action === "clear-end") {{
          const endInput = document.querySelector('[name="end"]');
          if (endInput) {{
            endInput.value = "";
          }}
        }} else if (action === "copy-last-time") {{
          copyLastTiming(button);
        }}
      }});
    }});
  </script>
</body>
</html>"""


def run_capture_server(store: SQLiteTaskStore, config: Config, host: str, port: int) -> None:
    focus_store = FocusProfileStore(config.sqlite_db_path)
    memory_store = ReviewMemoryStore(config.sqlite_db_path)
    engine_store = EngineStateStore(config.sqlite_db_path)
    focus_store.ensure_default_exists()
    handler = build_capture_handler(
        store,
        config,
        host=host,
        port=port,
        focus_profile_store=focus_store,
        memory_store=memory_store,
        engine_state_store=engine_store,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Capture 页面已启动: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def normalize_submission(form: Mapping[str, str], timezone: str) -> Dict[str, object]:
    tz = pytz.timezone(timezone)
    task_date = form.get("task_date") or datetime.now(tz).date().isoformat()
    start_time = form.get("start") or "09:00"
    start_dt = tz.localize(datetime.combine(datetime.fromisoformat(task_date).date(), datetime.strptime(start_time, "%H:%M").time()))

    end_value = form.get("end", "").strip()
    end_dt = None
    if end_value:
        end_dt = tz.localize(
            datetime.combine(datetime.fromisoformat(task_date).date(), datetime.strptime(end_value, "%H:%M").time())
        )

    xp_raw = form.get("xp", "").strip()
    return {
        "title": form.get("title", "").strip(),
        "category": form.get("category", "").strip() or "未分类",
        "priority": form.get("priority", "").strip(),
        "scheduled_start": start_dt,
        "scheduled_end": end_dt,
        "actual_minutes": int(form.get("minutes", "0") or 0),
        "tomatoes": int(form.get("tomatoes", "0") or 0),
        "xp": int(xp_raw) if xp_raw else None,
        "note": form.get("note", "").strip(),
    }


def build_capture_handler(
    store: SQLiteTaskStore,
    config: Config,
    host: str,
    port: int,
    focus_profile_store: Optional[FocusProfileStore] = None,
    memory_store: Optional[ReviewMemoryStore] = None,
    engine_state_store: Optional[EngineStateStore] = None,
):
    class CaptureHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            message = query.get("message", [""])[0]
            recent_tasks = store.recent_done_tasks(limit=12)
            dashboard_tasks = store.fetch_recent_tasks(7)
            manual_aliases = store.list_task_aliases(limit=8)
            dashboard = build_dashboard_snapshot(
                tasks=dashboard_tasks,
                manual_aliases=manual_aliases,
                timezone=config.timezone,
                focus_profile_store=focus_profile_store,
                memory_store=memory_store,
                engine_state_store=engine_state_store,
            )
            form_mode = "create"
            active_task_id = query.get("focus", [""])[0].strip()
            active_alias_id = query.get("alias_focus", [""])[0].strip()
            form_values = _merge_form_values(config.timezone)

            edit_id = query.get("edit", [""])[0].strip()
            edit_alias_id = query.get("edit_alias", [""])[0].strip()
            alias_id = query.get("alias", [""])[0].strip()
            manual_alias_id = query.get("manual_alias", [""])[0].strip()
            reuse_id = query.get("reuse", [""])[0].strip()
            variant_id = query.get("variant", [""])[0].strip()
            if edit_id:
                task = store.get_task(edit_id)
                if task:
                    form_values = _build_form_values_from_task(task, config.timezone, mode="edit")
                    form_mode = "edit"
                    active_task_id = task.id
                    if not message:
                        message = f"正在编辑：{task.title}"
            elif edit_alias_id:
                alias = store.get_task_alias(edit_alias_id)
                if alias:
                    form_values = _build_form_values_from_alias(alias, config.timezone, mode="manual_alias_edit")
                    form_mode = "manual_alias_edit"
                    active_alias_id = alias.id
                    if not message:
                        message = f"正在编辑手工别名：{alias.alias_name}"
            elif manual_alias_id:
                alias = store.get_task_alias(manual_alias_id)
                if alias:
                    form_values = _build_form_values_from_alias(alias, config.timezone, mode="manual_alias_use")
                    form_mode = "manual_alias_use"
                    active_alias_id = alias.id
                    if not message:
                        message = f"已载入手工别名：{alias.alias_name}"
            elif variant_id:
                task = store.get_task(variant_id)
                if task:
                    form_values = _build_form_values_from_task(task, config.timezone, mode="variant")
                    form_mode = "variant"
                    active_task_id = task.id
                    if not message:
                        message = f"已载入变体起点：{task.title}"
            elif alias_id:
                task = store.get_task(alias_id)
                if task:
                    form_values = _build_form_values_from_task(task, config.timezone, mode="alias")
                    form_mode = "alias"
                    active_task_id = task.id
                    if not message:
                        message = f"已载入别名：{task.title}"
            elif reuse_id:
                task = store.get_task(reuse_id)
                if task:
                    form_values = _build_form_values_from_task(task, config.timezone, mode="reuse")
                    form_mode = "reuse"
                    active_task_id = task.id
                    if not message:
                        message = f"已载入模板：{task.title}"

            body = build_capture_page(
                recent_tasks,
                timezone=config.timezone,
                message=message,
                host=host,
                port=port,
                form_values=form_values,
                form_mode=form_mode,
                active_task_id=active_task_id,
                manual_aliases=manual_aliases,
                active_alias_id=active_alias_id,
                dashboard=dashboard,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            payload = self.rfile.read(length).decode("utf-8")
            raw_form = parse_qs(payload, keep_blank_values=True)
            form = {key: values[0] for key, values in raw_form.items()}
            action = form.get("action", "save").strip()
            task_id = form.get("task_id", "").strip()
            alias_id = form.get("alias_id", "").strip()

            if action == "delete":
                self._delete_task(task_id)
                return
            if action == "delete_alias":
                self._delete_alias(alias_id)
                return
            if action == "save_focus":
                self._save_focus(form)
                return

            title = form.get("title", "").strip()
            if not title:
                self._redirect("任务名称不能为空。")
                return

            try:
                normalized = normalize_submission(form, config.timezone)
            except ValueError:
                self._redirect("日期或时间格式不正确，请检查后再保存。")
                return

            if action == "save_alias":
                alias_name = form.get("alias_name", "").strip() or _default_manual_alias_name(normalized["title"])
                alias_note = form.get("alias_note", "").strip()
                saved_alias = store.save_task_alias(
                    alias_name=alias_name,
                    title=str(normalized["title"]),
                    category=str(normalized["category"]),
                    priority=str(normalized["priority"]),
                    actual_minutes=int(normalized["actual_minutes"]),
                    tomatoes=int(normalized["tomatoes"]),
                    xp=normalized["xp"],
                    note=alias_note or str(normalized["note"]),
                    alias_id=alias_id,
                )
                self._redirect(
                    f"已保存手工别名：{saved_alias.alias_name}",
                    alias_focus_id=saved_alias.id,
                    alias_anchor=True,
                )
                return

            if task_id:
                updated = store.update_done_task(task_id, **normalized)
                if updated is None:
                    self._redirect("没有找到这条任务，可能已经被删除。")
                    return
                self._redirect(f"已更新：{updated.title}", focus_task_id=updated.id)
                return

            task = store.record_done_task(**normalized)
            self._redirect(f"已记录：{task.title}", focus_task_id=task.id)

        def log_message(self, format, *args):  # noqa: A003
            return

        def _delete_task(self, task_id: str) -> None:
            task = store.get_task(task_id)
            if task is None:
                self._redirect("没有找到这条任务，无法删除。")
                return
            if store.delete_task(task_id):
                self._redirect(f"已删除：{task.title}")
                return
            self._redirect("删除失败，请稍后再试。")

        def _delete_alias(self, alias_id: str) -> None:
            alias = store.get_task_alias(alias_id)
            if alias is None:
                self._redirect("没有找到这条手工别名，无法删除。")
                return
            if store.delete_task_alias(alias_id):
                self._redirect(f"已删除手工别名：{alias.alias_name}")
                return
            self._redirect("删除手工别名失败，请稍后再试。")

        def _save_focus(self, form: Mapping[str, str]) -> None:
            if not focus_profile_store:
                self._redirect("当前环境没有可写的焦点档案。")
                return

            profile = focus_profile_store.load()
            profile.current_focus = form.get("current_focus", "").strip()
            profile.current_stage = form.get("current_stage", "").strip()
            mode_key = form.get("coaching_mode", "").strip()
            profile.coaching_mode = resolve_mode(mode_key).key
            profile.coaching_notes = form.get("coaching_notes", "").strip()
            profile.last_updated = datetime.now().date().isoformat()
            focus_profile_store.save(profile)
            self._redirect("已更新首页控制台。", focus_anchor=True)

        def _redirect(
            self,
            message: str,
            focus_task_id: str = "",
            alias_focus_id: str = "",
            alias_anchor: bool = False,
            focus_anchor: bool = False,
        ) -> None:
            params = {"message": message}
            if focus_task_id:
                params["focus"] = focus_task_id
            if alias_focus_id:
                params["alias_focus"] = alias_focus_id
            query = urlencode(params)
            suffix = ""
            if focus_anchor:
                suffix = "#focus-control"
            elif alias_focus_id and alias_anchor:
                suffix = f"#alias-{alias_focus_id}"
            elif focus_task_id:
                suffix = f"#task-{focus_task_id}"
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/?{query}{suffix}")
            self.end_headers()

    return CaptureHandler


def _build_form_values_from_task(task: TaskRecord, timezone: str, mode: str) -> Dict[str, str]:
    tz = pytz.timezone(timezone)
    defaults = _merge_form_values(timezone)
    start_local = task.scheduled_start.astimezone(tz) if task.scheduled_start else datetime.now(tz)
    end_local = task.scheduled_end.astimezone(tz) if task.scheduled_end else None
    if mode in {"reuse", "alias", "variant"}:
        defaults["task_date"] = datetime.now(tz).date().isoformat()
        defaults["start"] = datetime.now(tz).strftime("%H:%M")
        defaults["end"] = ""
        defaults["task_id"] = ""
        defaults["return_to"] = task.id
    else:
        defaults["task_date"] = start_local.date().isoformat()
        defaults["start"] = start_local.strftime("%H:%M")
        defaults["end"] = end_local.strftime("%H:%M") if end_local else ""
        defaults["task_id"] = task.id
        defaults["return_to"] = task.id

    defaults["title"] = task.title
    defaults["category"] = task.category or "未分类"
    defaults["priority"] = task.priority or ""
    defaults["minutes"] = str(task.actual_minutes if task.actual_minutes > 0 else 30)
    defaults["tomatoes"] = str(task.tomatoes)
    defaults["xp"] = str(task.xp) if task.xp > 0 else ""
    defaults["note"] = "" if mode == "variant" else str(task.raw.get("note", "") or "")
    defaults["alias_id"] = ""
    defaults["alias_name"] = ""
    defaults["alias_note"] = ""
    return defaults


def _build_form_values_from_alias(alias: TaskAlias, timezone: str, mode: str) -> Dict[str, str]:
    defaults = _merge_form_values(timezone)
    defaults["task_id"] = ""
    defaults["alias_id"] = alias.id
    defaults["alias_name"] = alias.alias_name
    defaults["alias_note"] = alias.note
    defaults["title"] = alias.title
    defaults["category"] = alias.category or "未分类"
    defaults["priority"] = alias.priority or ""
    defaults["minutes"] = str(alias.actual_minutes if alias.actual_minutes > 0 else 30)
    defaults["tomatoes"] = str(alias.tomatoes)
    defaults["xp"] = str(alias.xp) if alias.xp > 0 else ""
    defaults["note"] = alias.note if mode == "manual_alias_edit" else ""
    return defaults


def build_dashboard_snapshot(
    tasks: Sequence[TaskRecord],
    manual_aliases: Sequence[TaskAlias],
    timezone: str,
    focus_profile_store: Optional[FocusProfileStore] = None,
    memory_store: Optional[ReviewMemoryStore] = None,
    engine_state_store: Optional[EngineStateStore] = None,
) -> DashboardSnapshot:
    tz = pytz.timezone(timezone)
    today = datetime.now(tz).date()
    today_tasks = [
        task for task in tasks
        if task.scheduled_start and task.scheduled_start.astimezone(tz).date() == today
    ]
    minutes_last_7_days = sum(max(task.actual_minutes, 0) for task in tasks[:7])
    focus_profile = focus_profile_store.load() if focus_profile_store else None
    memory_entry = memory_store.latest_follow_up_entry("daily") if memory_store else None
    engine_state = engine_state_store.load() if engine_state_store else None
    mode = resolve_mode(focus_profile.coaching_mode if focus_profile else "adaptive")
    next_action = ""
    latest_preview = ""
    latest_generated_at = ""
    if memory_entry:
        next_action = memory_entry.follow_up
        latest_preview = memory_entry.preview
        latest_generated_at = memory_entry.generated_at
    elif focus_profile and focus_profile.current_focus:
        next_action = f"围绕“{focus_profile.current_focus}”推进一个最小可交付动作。"

    return DashboardSnapshot(
        current_focus=focus_profile.current_focus if focus_profile else "",
        current_stage=focus_profile.current_stage if focus_profile else "",
        coaching_mode_key=mode.key,
        coaching_mode_name=mode.name,
        coaching_notes=focus_profile.coaching_notes if focus_profile else "",
        next_action=next_action,
        latest_preview=latest_preview,
        latest_generated_at=latest_generated_at,
        is_dormant=bool(engine_state.dormant_since) if engine_state else False,
        last_active_date=engine_state.last_active_date if engine_state else "",
        dormant_since=engine_state.dormant_since if engine_state else "",
        last_restart_nudge_date=engine_state.last_restart_nudge_date if engine_state else "",
        tasks_today=len(today_tasks),
        tasks_last_7_days=len(tasks),
        minutes_last_7_days=minutes_last_7_days,
        manual_alias_count=len(manual_aliases),
    )


def _merge_form_values(timezone: str, overrides: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    values = {
        "task_id": "",
        "alias_id": "",
        "alias_name": "",
        "alias_note": "",
        "return_to": "",
        "title": "",
        "category": "未分类",
        "priority": "",
        "task_date": now.date().isoformat(),
        "start": now.strftime("%H:%M"),
        "end": "",
        "minutes": "30",
        "tomatoes": "0",
        "xp": "",
        "note": "",
    }
    if not overrides:
        return values

    for key, value in overrides.items():
        values[key] = "" if value is None else str(value)
    return values


def _render_dashboard(snapshot: DashboardSnapshot) -> str:
    status_class = "is-dormant" if snapshot.is_dormant else "is-active"
    status_text = "熄火中" if snapshot.is_dormant else "运行中"
    next_action = html.escape(snapshot.next_action or "还没有明确下一步。先在下面更新当前主线或记录一个最小完成动作。")
    latest_preview = html.escape(snapshot.latest_preview or "还没有历史复盘摘要。")
    current_focus = html.escape(snapshot.current_focus or "当前主线还没有明确写下来。")
    current_stage = html.escape(snapshot.current_stage or "阶段未设置")
    latest_meta = html.escape(snapshot.latest_generated_at or "暂无复盘记录")
    active_meta = html.escape(snapshot.last_active_date or "暂无任务证据")
    dormant_meta = html.escape(snapshot.dormant_since or "未进入熄火")
    return (
        "<section class='dashboard-grid'>"
        "<section class='card dashboard-card'>"
        "<div class='eyebrow'>当前主线</div>"
        f"<div class='hero-value'>{current_focus}</div>"
        f"<div class='dashboard-copy'>阶段：{current_stage}<br>模式：{html.escape(snapshot.coaching_mode_name)}</div>"
        "</section>"
        "<section class='card dashboard-card'>"
        "<div class='eyebrow'>当前建议动作</div>"
        f"<div class='hero-value'>{next_action}</div>"
        f"<div class='dashboard-copy'>最近摘要：{latest_preview}<br>来源时间：{latest_meta}</div>"
        "</section>"
        "<section class='card dashboard-card'>"
        "<div class='eyebrow'>系统状态</div>"
        f"<div class='status-pill {status_class}'>{status_text}</div>"
        f"<div class='dashboard-copy'>最近活跃：{active_meta}<br>熄火起点：{dormant_meta}</div>"
        "<div class='metric-row'>"
        f"<div class='metric'><div class='metric-label'>今天完成</div><div class='metric-value'>{snapshot.tasks_today}</div><div class='metric-sub'>项</div></div>"
        f"<div class='metric'><div class='metric-label'>最近 7 天</div><div class='metric-value'>{snapshot.tasks_last_7_days}</div><div class='metric-sub'>项</div></div>"
        f"<div class='metric'><div class='metric-label'>最近 7 天时长</div><div class='metric-value'>{snapshot.minutes_last_7_days}</div><div class='metric-sub'>分钟</div></div>"
        f"<div class='metric'><div class='metric-label'>手工别名</div><div class='metric-value'>{snapshot.manual_alias_count}</div><div class='metric-sub'>个</div></div>"
        "</div>"
        "</section>"
        "</section>"
    )


def _render_focus_console(snapshot: DashboardSnapshot) -> str:
    options = "\n".join(
        _mode_option_html(mode_key, snapshot.coaching_mode_key)
        for mode_key in available_mode_keys()
    )
    return (
        "<section class='card focus-form' id='focus-control'>"
        "<div class='section-head'><h2>首页控制台</h2><span class='muted-inline'>在这里维护当前主线、阶段和教练模式。</span></div>"
        "<form method='post' action='/'>"
        "<div class='row'>"
        "<label>当前主线"
        f"<input type='text' name='current_focus' value='{_escape_attr(snapshot.current_focus)}' placeholder='例如：把内容系统跑起来'>"
        "</label>"
        "<label>当前阶段"
        f"<input type='text' name='current_stage' value='{_escape_attr(snapshot.current_stage)}' placeholder='例如：建设期 / 冲刺期'>"
        "</label>"
        "</div>"
        "<div class='row'>"
        "<label>教练模式"
        f"<select name='coaching_mode'>{options}</select>"
        "</label>"
        "<label>模式备注"
        f"<input type='text' name='coaching_notes' value='{_escape_attr(snapshot.coaching_notes)}' placeholder='例如：现在优先沉淀系统资产'>"
        "</label>"
        "</div>"
        "<div class='submit-row'>"
        "<button type='submit' name='action' value='save_focus'>更新首页控制台</button>"
        "<span class='muted-inline'>这会直接更新你的当前主线，不需要再去手改 JSON。</span>"
        "</div>"
        "</form>"
        "</section>"
    )


def _category_options(tasks: Sequence[TaskRecord], current_category: str) -> List[str]:
    options: List[str] = []
    for category in DEFAULT_CATEGORIES:
        if category not in options:
            options.append(category)

    if current_category and current_category not in options and current_category != "未分类":
        options.insert(0, current_category)

    for task in tasks:
        category = (task.category or "").strip()
        if category and category != "未分类" and category not in options:
            options.append(category)
    return options


def _priority_option(value: str, label: str, selected_value: str) -> str:
    selected = " selected" if value == selected_value else ""
    return f"<option value='{html.escape(value, quote=True)}'{selected}>{html.escape(label)}</option>"


def _mode_option_html(mode_key: str, selected_key: str) -> str:
    mode = resolve_mode(mode_key)
    selected = " selected" if mode.key == selected_key else ""
    return f"<option value='{html.escape(mode.key, quote=True)}'{selected}>{html.escape(mode.name)}</option>"


def _render_quick_chip(label: str, field_name: str, variant: str = "") -> str:
    escaped = _escape_attr(label)
    extra_class = f" is-{variant}" if variant else ""
    return f"<button type='button' class='quick-btn{extra_class}' data-fill='{field_name}' data-value='{escaped}'>{html.escape(label)}</button>"


def _render_time_preset_chip(preset: Optional[Mapping[str, str]]) -> str:
    if not preset:
        return ""
    return (
        "<button type='button' class='quick-btn is-memory' data-action='copy-last-time' "
        f"data-preset-start='{_escape_attr(preset['start'])}' "
        f"data-preset-end='{_escape_attr(preset['end'])}' "
        f"data-preset-minutes='{_escape_attr(preset['minutes'])}' "
        f"data-preset-tomatoes='{_escape_attr(preset['tomatoes'])}'>"
        f"{html.escape(preset['label'])}"
        "</button>"
    )


def _render_variant_chip(task: Optional[TaskRecord]) -> str:
    if task is None:
        return ""
    task_id = html.escape(task.id, quote=True)
    title = html.escape(task.title)
    return (
        f"<a class='quick-btn is-memory' href='/?variant={task_id}&focus={task_id}#task-{task_id}' "
        f"title='基于上一条做变体：{title}'>上一条做变体</a>"
    )


def _render_manual_alias_card(alias: TaskAlias, active_alias_id: str = "") -> str:
    alias_id = html.escape(alias.id, quote=True)
    alias_name = html.escape(alias.alias_name)
    title = html.escape(alias.title)
    row_class = " alias-card is-active" if active_alias_id and alias.id == active_alias_id else " alias-card"
    meta_bits = [alias.category or "未分类"]
    if alias.priority:
        meta_bits.append(alias.priority)
    if alias.actual_minutes > 0:
        meta_bits.append(f"{alias.actual_minutes} 分钟")
    if alias.tomatoes > 0:
        meta_bits.append(f"{alias.tomatoes} 番茄")
    meta_line = " · ".join(meta_bits)
    note_line = f"<div class='task-note'>{html.escape(alias.note)}</div>" if alias.note else ""
    return (
        f"<div class='{row_class.strip()}' id='alias-{alias_id}'>"
        f"<a class='template-link is-manual' href='/?manual_alias={alias_id}&alias_focus={alias_id}#alias-{alias_id}' title='使用手工别名 {alias_name}'>"
        f"<b>Manual</b><span>{alias_name}</span></a>"
        f"<div class='alias-meta'>{title}</div>"
        f"<div class='alias-meta'>{html.escape(meta_line)}</div>"
        f"{note_line}"
        "<div class='actions'>"
        f"<a class='link-btn' href='/?edit_alias={alias_id}&alias_focus={alias_id}#alias-{alias_id}'>编辑别名</a>"
        "<form class='inline-form' method='post' action='/' onsubmit=\"return confirm('删除这条手工别名吗？');\">"
        "<input type='hidden' name='action' value='delete_alias'>"
        f"<input type='hidden' name='alias_id' value='{alias_id}'>"
        "<button type='submit' class='link-btn is-danger'>删除别名</button>"
        "</form>"
        "</div>"
        "</div>"
    )


def _render_template_chip(task: TaskRecord, count: int = 1, variant: str = "recent") -> str:
    title = html.escape(task.title)
    count_badge = f" <em>x{count}</em>" if count > 1 else ""
    css_class = "template-link is-favorite" if variant == "favorite" else "template-link"
    return (
        f"<a class='{css_class}' href='/?reuse={html.escape(task.id, quote=True)}&focus={html.escape(task.id, quote=True)}#task-{html.escape(task.id, quote=True)}' "
        f"title='复用 {title}'><span>{title}</span>{count_badge}</a>"
    )


def _render_alias_chip(task: TaskRecord, alias: str, count: int = 1) -> str:
    task_id = html.escape(task.id, quote=True)
    alias_text = html.escape(alias)
    title = html.escape(task.title)
    count_badge = f" <em>x{count}</em>" if count > 1 else ""
    return (
        f"<a class='template-link is-alias' href='/?alias={task_id}&focus={task_id}#task-{task_id}' "
        f"title='别名 {alias_text} -> {title}'><b>Alias</b><span>{alias_text}</span>{count_badge}</a>"
    )


def _render_task_row(task: TaskRecord, tz, active_task_id: str = "") -> str:
    start_str = task.scheduled_start.astimezone(tz).strftime("%m-%d %H:%M") if task.scheduled_start else "无"
    efficiency = f"{task.xp}/{task.tomatoes}" if task.tomatoes else f"{task.xp}/0"
    note = str(task.raw.get("note", "") or "")
    note_html = f"<div class='task-note'>{html.escape(note)}</div>" if note else ""
    row_class = " class='row-active'" if active_task_id and task.id == active_task_id else ""
    return (
        f"<tr id='task-{html.escape(task.id, quote=True)}'{row_class}>"
        f"<td data-label='时间'>{html.escape(start_str)}</td>"
        f"<td data-label='任务' class='task-cell'><strong>{html.escape(task.title)}</strong>{note_html}</td>"
        f"<td data-label='分类'>{html.escape(task.category)}</td>"
        f"<td data-label='优先级'>{html.escape(task.priority or '无')}</td>"
        f"<td data-label='效率'>{html.escape(efficiency)}</td>"
        "<td data-label='操作'>"
        "<div class='actions'>"
        f"<a class='link-btn' href='/?variant={html.escape(task.id, quote=True)}&focus={html.escape(task.id, quote=True)}#task-{html.escape(task.id, quote=True)}'>变体</a>"
        f"<a class='link-btn' href='/?reuse={html.escape(task.id, quote=True)}&focus={html.escape(task.id, quote=True)}#task-{html.escape(task.id, quote=True)}'>复用</a>"
        f"<a class='link-btn' href='/?edit={html.escape(task.id, quote=True)}&focus={html.escape(task.id, quote=True)}#task-{html.escape(task.id, quote=True)}'>编辑</a>"
        "<form class='inline-form' method='post' action='/' onsubmit=\"return confirm('删除后无法恢复，确定继续吗？');\">"
        "<input type='hidden' name='action' value='delete'>"
        f"<input type='hidden' name='task_id' value='{html.escape(task.id, quote=True)}'>"
        "<button type='submit' class='link-btn is-danger'>删除</button>"
        "</form>"
        "</div>"
        "</td>"
        "</tr>"
    )


def _escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def _build_favorite_templates(tasks: Sequence[TaskRecord]) -> List[Dict[str, object]]:
    grouped: "OrderedDict[tuple[str, str, str], Dict[str, object]]" = OrderedDict()
    for index, task in enumerate(tasks):
        key = (task.title.strip(), task.category.strip(), task.priority.strip())
        if key not in grouped:
            grouped[key] = {"task": task, "count": 0, "first_index": index}
        grouped[key]["count"] += 1

    ranked = sorted(grouped.values(), key=lambda item: (-int(item["count"]), int(item["first_index"])))
    return ranked[:5]


def _build_task_aliases(tasks: Sequence[TaskRecord]) -> List[Dict[str, object]]:
    aliases: List[Dict[str, object]] = []
    seen_labels = set()
    for entry in _build_favorite_templates(tasks):
        task = entry["task"]
        label = _build_alias_label(task)
        if label in seen_labels:
            label = _build_alias_label(task, include_category=True)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        aliases.append({
            "task": task,
            "alias": label,
            "count": int(entry["count"]),
        })
    return aliases[:5]


def _recent_category_memory(tasks: Sequence[TaskRecord], limit: int = 3) -> List[str]:
    seen = set()
    categories: List[str] = []
    for task in tasks:
        category = (task.category or "").strip()
        if not category or category == "未分类" or category in seen:
            continue
        seen.add(category)
        categories.append(category)
        if len(categories) >= limit:
            break
    return categories


def _build_latest_timing_preset(tasks: Sequence[TaskRecord], timezone: str) -> Optional[Dict[str, str]]:
    if not tasks:
        return None

    tz = pytz.timezone(timezone)
    task = tasks[0]
    start_local = task.scheduled_start.astimezone(tz) if task.scheduled_start else None
    end_local = task.scheduled_end.astimezone(tz) if task.scheduled_end else None
    if start_local is None:
        return None

    minutes = str(task.actual_minutes if task.actual_minutes > 0 else 30)
    tomatoes = str(task.tomatoes if task.tomatoes >= 0 else 0)
    label = f"复制上一条时间 {start_local.strftime('%H:%M')} / {minutes} 分钟"
    return {
        "start": start_local.strftime("%H:%M"),
        "end": end_local.strftime("%H:%M") if end_local else "",
        "minutes": minutes,
        "tomatoes": tomatoes,
        "label": label,
    }


def _build_latest_variant_task(tasks: Sequence[TaskRecord]) -> Optional[TaskRecord]:
    if not tasks:
        return None
    return tasks[0]


def _build_alias_label(task: TaskRecord, include_category: bool = False) -> str:
    raw_title = " ".join((task.title or "").split())
    for separator in ("：", ":", "-", "|", "（", "("):
        if separator in raw_title:
            raw_title = raw_title.split(separator, 1)[0].strip()
            break
    if len(raw_title) > 8:
        raw_title = raw_title[:8] + "…"
    if include_category and task.category and task.category != "未分类":
        return f"{task.category}-{raw_title}"
    return raw_title or "常用任务"


def _default_manual_alias_name(title: object) -> str:
    text = " ".join(str(title or "").split())
    if len(text) > 10:
        return text[:10] + "…"
    return text or "手工别名"
