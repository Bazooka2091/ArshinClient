#!/usr/bin/env python3
"""Простой веб-интерфейс для запросов к ФГИС Аршин."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import requests
from flask import Flask, render_template_string, request

app = Flask(__name__)

EAPI_URL = "https://fgis.gost.ru/fundmetrology/eapi/vri"
XCDB_URL = "https://fgis.gost.ru/fundmetrology/cm/xcdb/vri/select"
TIMEOUT = 60

# По руководству /vri (Таб. 34–35) + атрибутивный поиск по полям, включённым в search.
EAPI_FILTERS = [
    {"key": "year", "label": "year — год поверки"},
    {"key": "search", "label": "search — полнотекстовый поиск (*подстрока*)"},
    {"key": "mi_number", "label": "mi_number — заводской / серийный номер"},
    {"key": "mit_number", "label": "mit_number — рег. номер типа СИ"},
    {"key": "mit_title", "label": "mit_title — наименование типа СИ"},
    {"key": "mit_notation", "label": "mit_notation — обозначение типа СИ"},
    {"key": "mi_modification", "label": "mi_modification — модификация СИ"},
    {"key": "org_title", "label": "org_title — организация-поверитель"},
    {"key": "result_docnum", "label": "result_docnum — № свидетельства / извещения"},
    {"key": "verification_date", "label": "verification_date — дата поверки"},
    {"key": "valid_date", "label": "valid_date — действительна до"},
    {"key": "applicability", "label": "applicability — пригодность (true/false)"},
]

# Поля Solr-эндпоинта xcdb (неофициальный).
XCDB_FILTERS = [
    {"key": "mi.number", "label": "mi.number — заводской номер"},
    {"key": "mi.mitnumber", "label": "mi.mitnumber — рег. номер типа СИ"},
    {"key": "mi.mititle", "label": "mi.mititle — наименование типа СИ"},
    {"key": "mi.mitype", "label": "mi.mitype — обозначение типа СИ"},
    {"key": "mi.modification", "label": "mi.modification — модификация"},
    {"key": "org_title", "label": "org_title — организация-поверитель"},
    {"key": "result_docnum", "label": "result_docnum — № свидетельства"},
    {"key": "verification_date", "label": "verification_date — дата поверки"},
    {"key": "valid_date", "label": "valid_date — действительна до"},
    {"key": "applicability", "label": "applicability — пригодность (true/false)"},
    {"key": "vri_id", "label": "vri_id — идентификатор записи"},
    {"key": "custom", "label": "custom — произвольный fq (целиком)"},
]

PAGE = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Аршин — поиск поверок</title>
  <style>
    :root {
      --bg: #f3f1ec;
      --card: #fff;
      --ink: #1c1b19;
      --muted: #5c5852;
      --line: #d9d4cb;
      --accent: #0b5fff;
      --ok: #0f7b3a;
      --err: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(900px 400px at 10% -10%, #dfe9ff 0%, transparent 55%),
        radial-gradient(700px 300px at 100% 0%, #efe7d8 0%, transparent 50%),
        var(--bg);
    }
    main { max-width: 1100px; margin: 0 auto; padding: 28px 16px 48px; }
    h1 { margin: 0 0 6px; font-size: 1.6rem; }
    .sub { color: var(--muted); margin-bottom: 22px; }
    form, .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
    input, select, textarea {
      width: 100%;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      background: #fff;
    }
    .row { margin-top: 12px; }
    .hint { font-size: 12px; color: var(--muted); margin-top: 6px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; align-items: center; }
    button, .btn {
      border: 0;
      border-radius: 8px;
      padding: 10px 16px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      cursor: pointer;
    }
    button.secondary, .btn.secondary { background: #eceae4; color: var(--ink); }
    button.danger, .btn.danger { background: #f3e0de; color: var(--err); padding: 8px 12px; }
    button.icon, .btn.icon { padding: 8px 12px; min-width: 40px; }
    .url {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      word-break: break-all;
      background: #f7f5f0;
      border-radius: 8px;
      padding: 10px;
      border: 1px solid var(--line);
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); text-align: left; padding: 8px 6px; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    .ok { color: var(--ok); }
    .err { color: var(--err); white-space: pre-wrap; }
    pre {
      margin: 0;
      overflow: auto;
      max-height: 420px;
      background: #111;
      color: #e8e8e8;
      padding: 12px;
      border-radius: 8px;
      font-size: 12px;
    }
    details { margin-top: 12px; }
    .filter-row {
      display: grid;
      grid-template-columns: minmax(220px, 1.2fr) minmax(180px, 1fr) auto;
      gap: 8px;
      margin-top: 8px;
      align-items: end;
    }
    @media (max-width: 720px) {
      .filter-row { grid-template-columns: 1fr; }
    }
    .section-title {
      margin: 18px 0 4px;
      font-size: 14px;
      font-weight: 650;
    }
  </style>
</head>
<body>
<main>
  <h1>Аршин API</h1>
  <p class="sub">Конструктор фильтров по параметрам реестра поверок СИ (/eapi/vri).</p>

  <form method="post" id="search-form">
    <div class="grid">
      <div>
        <label>Режим API</label>
        <select name="mode" id="mode">
          <option value="eapi" {% if mode == 'eapi' %}selected{% endif %}>Официальный eapi/vri</option>
          <option value="xcdb" {% if mode == 'xcdb' %}selected{% endif %}>xcdb (Solr fq, все годы)</option>
        </select>
      </div>
      <div>
        <label>Строк (rows, max 100)</label>
        <input name="rows" type="number" min="1" max="100" value="{{ rows }}">
      </div>
      <div>
        <label>Старт (start)</label>
        <input name="start" type="number" min="0" value="{{ start }}">
      </div>
      <div>
        <label>Сортировка (sort)</label>
        <input name="sort" value="{{ sort }}" placeholder="verification_date desc">
      </div>
    </div>

    <div class="section-title">Фильтры</div>
    <p class="hint" id="eapi-hint">
      По руководству API в поиск входят: org_title, mit_number, mit_title, mit_notation,
      mi_modification, mi_number, result_docnum. Их же можно задавать отдельными параметрами.
      Для подстроки используйте <code>*текст*</code>.
    </p>
    <p class="hint" id="xcdb-hint" style="display:none;">
      Каждый фильтр уходит как отдельный <code>fq</code>. Для подстроки: <code>*текст*</code>.
      Режим custom — произвольная строка fq целиком.
    </p>

    <div id="filters"></div>
    <div class="actions">
      <button type="button" class="secondary icon" id="add-filter">+ параметр</button>
      <button type="submit">Выполнить запрос</button>
      <button type="submit" name="show_url_only" value="1" class="secondary">Только URL</button>
    </div>
  </form>

  {% if error %}
  <div class="panel"><strong class="err">Ошибка:</strong><div class="err">{{ error }}</div></div>
  {% endif %}

  {% if request_url %}
  <div class="panel">
    <label>URL запроса</label>
    <div class="url">{{ request_url }}</div>
    {% if elapsed is not none %}<p class="hint">Время ответа: {{ '%.2f'|format(elapsed) }} с</p>{% endif %}
  </div>
  {% endif %}

  {% if items %}
  <div class="panel">
    <strong>Найдено: {{ count }}</strong>
    <div style="overflow:auto; margin-top:10px;">
      <table>
        <thead>
          <tr>
            <th>Номер</th>
            <th>Тип / модель</th>
            <th>Наименование</th>
            <th>Поверка</th>
            <th>Действует до</th>
            <th>Организация</th>
            <th>Пригодность</th>
          </tr>
        </thead>
        <tbody>
          {% for it in items %}
          <tr>
            <td>{{ it.number }}</td>
            <td>{{ it.type }}{% if it.modification %}<br><span class="hint">{{ it.modification }}</span>{% endif %}</td>
            <td>{{ it.title }}</td>
            <td>{{ it.verification_date }}</td>
            <td>{{ it.valid_date }}</td>
            <td>{{ it.org }}</td>
            <td class="{{ 'ok' if it.applicability else 'err' }}">{{ it.applicability }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% elif raw_json and not error %}
  <div class="panel"><em>Записей нет.</em></div>
  {% endif %}

  {% if raw_json %}
  <div class="panel">
    <details open>
      <summary>Сырой JSON</summary>
      <pre>{{ raw_json }}</pre>
    </details>
  </div>
  {% endif %}
</main>

<script>
  const EAPI_FILTERS = {{ eapi_filters | tojson }};
  const XCDB_FILTERS = {{ xcdb_filters | tojson }};
  const INITIAL_FILTERS = {{ filters | tojson }};

  const filtersEl = document.getElementById('filters');
  const modeEl = document.getElementById('mode');

  function currentCatalog() {
    return modeEl.value === 'xcdb' ? XCDB_FILTERS : EAPI_FILTERS;
  }

  function optionHtml(selected) {
    return currentCatalog().map(f =>
      `<option value="${f.key}" ${f.key === selected ? 'selected' : ''}>${f.label}</option>`
    ).join('');
  }

  function addFilter(field, value) {
    const catalog = currentCatalog();
    const defaultField = catalog[0] ? catalog[0].key : '';
    const row = document.createElement('div');
    row.className = 'filter-row';
    row.innerHTML = `
      <div>
        <label>Параметр</label>
        <select name="filter_field">${optionHtml(field || defaultField)}</select>
      </div>
      <div>
        <label>Значение</label>
        <input name="filter_value" placeholder="значение или *подстрока*">
      </div>
      <div>
        <button type="button" class="danger icon remove-filter">−</button>
      </div>
    `;
    row.querySelector('[name=filter_value]').value = value || '';
    row.querySelector('.remove-filter').addEventListener('click', () => {
      row.remove();
      if (!filtersEl.children.length) addFilter();
    });
    filtersEl.appendChild(row);
  }

  function rebuildFilterOptionsKeepValues() {
    const rows = [...filtersEl.querySelectorAll('.filter-row')];
    const values = rows.map(r => ({
      field: r.querySelector('[name=filter_field]').value,
      value: r.querySelector('[name=filter_value]').value,
    }));
    filtersEl.innerHTML = '';
    if (!values.length) {
      addFilter(modeEl.value === 'xcdb' ? 'mi.number' : 'mi_number', '');
      return;
    }
    const keys = new Set(currentCatalog().map(f => f.key));
    values.forEach(v => {
      const field = keys.has(v.field) ? v.field : (currentCatalog()[0] || {}).key;
      addFilter(field, v.value);
    });
  }

  function syncMode() {
    const xcdb = modeEl.value === 'xcdb';
    document.getElementById('eapi-hint').style.display = xcdb ? 'none' : 'block';
    document.getElementById('xcdb-hint').style.display = xcdb ? 'block' : 'none';
    rebuildFilterOptionsKeepValues();
  }

  document.getElementById('add-filter').addEventListener('click', () => addFilter());
  modeEl.addEventListener('change', syncMode);

  if (INITIAL_FILTERS && INITIAL_FILTERS.length) {
    INITIAL_FILTERS.forEach(f => addFilter(f.field, f.value));
  } else {
    addFilter('mi_number', '');
  }
  syncMode();
</script>
</body>
</html>
"""


def _norm_date(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return text[:10]
    return text


def collect_filters() -> list[dict[str, str]]:
    fields = request.form.getlist("filter_field")
    values = request.form.getlist("filter_value")
    out: list[dict[str, str]] = []
    for field, value in zip(fields, values):
        field = (field or "").strip()
        value = (value or "").strip()
        if field and value:
            out.append({"field": field, "value": value})
    return out


def build_eapi(
    filters: list[dict[str, str]], rows: int, start: int, sort: str
) -> tuple[str, dict[str, Any]]:
    allowed = {f["key"] for f in EAPI_FILTERS}
    params: dict[str, Any] = {"rows": rows, "start": start}
    if sort:
        params["sort"] = sort

    for item in filters:
        key = item["field"]
        if key not in allowed:
            raise ValueError(f"Недопустимый параметр eapi: {key}")
        if key == "year":
            params["year"] = int(item["value"])
        else:
            params[key] = item["value"]

    # year/search/атрибуты — всё необязательно; без фильтров API отдаст выдачу по умолчанию
    return EAPI_URL, params


def build_xcdb(
    filters: list[dict[str, str]], rows: int, start: int, sort: str
) -> tuple[str, list[tuple[str, str]]]:
    allowed = {f["key"] for f in XCDB_FILTERS}
    fq: list[str] = []
    for item in filters:
        key = item["field"]
        value = item["value"]
        if key not in allowed:
            raise ValueError(f"Недопустимый параметр xcdb: {key}")
        if key == "custom":
            fq.append(value)
        else:
            fq.append(f"{key}:{value}")

    if not fq:
        raise ValueError("Добавьте хотя бы один фильтр для xcdb.")

    params: list[tuple[str, str]] = [
        ("q", "*"),
        ("rows", str(rows)),
        ("start", str(start)),
        (
            "fl",
            "mi.number,vri_id,verification_date,valid_date,mi.mititle,mi.mitype,"
            "mi.modification,mi.mitnumber,org_title,applicability,result_docnum",
        ),
    ]
    if sort:
        # в Solr обычно "field asc"
        params.append(("sort", sort))
    for item in fq:
        params.append(("fq", item))
    return XCDB_URL, params


def normalize_eapi(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    result = payload.get("result") or {}
    items = []
    for it in result.get("items") or []:
        items.append(
            {
                "number": it.get("mi_number", ""),
                "type": it.get("mit_notation", ""),
                "modification": it.get("mi_modification", ""),
                "title": it.get("mit_title", ""),
                "verification_date": _norm_date(it.get("verification_date")),
                "valid_date": _norm_date(it.get("valid_date")),
                "org": it.get("org_title", ""),
                "applicability": it.get("applicability"),
            }
        )
    return int(result.get("count") or len(items)), items


def normalize_xcdb(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    response = payload.get("response") or {}
    items = []
    for it in response.get("docs") or []:
        items.append(
            {
                "number": it.get("mi.number", ""),
                "type": it.get("mi.mitype", ""),
                "modification": it.get("mi.modification", ""),
                "title": it.get("mi.mititle", ""),
                "verification_date": _norm_date(it.get("verification_date")),
                "valid_date": _norm_date(it.get("valid_date")),
                "org": it.get("org_title", ""),
                "applicability": it.get("applicability"),
            }
        )
    return int(response.get("numFound") or len(items)), items


def render_page(**kwargs: Any):
    return render_template_string(
        PAGE,
        eapi_filters=EAPI_FILTERS,
        xcdb_filters=XCDB_FILTERS,
        **kwargs,
    )


@app.get("/")
def index_get():
    return render_page(
        mode="eapi",
        rows=20,
        start=0,
        sort="",
        filters=[{"field": "mi_number", "value": ""}],
        request_url=None,
        items=None,
        count=0,
        raw_json=None,
        error=None,
        elapsed=None,
    )


@app.post("/")
def index_post():
    mode = request.form.get("mode") or "eapi"
    rows = int(request.form.get("rows") or 20)
    start = int(request.form.get("start") or 0)
    sort = (request.form.get("sort") or "").strip()
    filters = collect_filters()

    # Для повторного отображения формы сохраняем и пустые строки фильтров.
    display_filters = []
    for field, value in zip(
        request.form.getlist("filter_field"), request.form.getlist("filter_value")
    ):
        if (field or "").strip():
            display_filters.append({"field": field.strip(), "value": (value or "").strip()})
    if not display_filters:
        display_filters = [{"field": "mi_number" if mode == "eapi" else "mi.number", "value": ""}]

    ctx: dict[str, Any] = {
        "mode": mode,
        "rows": rows,
        "start": start,
        "sort": sort,
        "filters": display_filters,
        "request_url": None,
        "items": None,
        "count": 0,
        "raw_json": None,
        "error": None,
        "elapsed": None,
    }

    try:
        if mode == "xcdb":
            url, params = build_xcdb(filters, rows, start, sort)
            request_url = f"{url}?{urlencode(params)}"
        else:
            url, params = build_eapi(filters, rows, start, sort)
            request_url = f"{url}?{urlencode(params)}"

        ctx["request_url"] = request_url

        if request.form.get("show_url_only"):
            return render_page(**ctx)

        started = datetime.now()
        response = requests.get(url, params=params, timeout=TIMEOUT)
        ctx["elapsed"] = (datetime.now() - started).total_seconds()
        response.raise_for_status()
        payload = response.json()
        ctx["raw_json"] = json.dumps(payload, ensure_ascii=False, indent=2)

        if mode == "xcdb":
            count, items = normalize_xcdb(payload)
        else:
            if payload.get("status"):
                raise ValueError(payload.get("message") or str(payload))
            count, items = normalize_eapi(payload)
        ctx["count"] = count
        ctx["items"] = items
    except Exception as exc:  # noqa: BLE001 — UI показывает любую ошибку запроса
        ctx["error"] = str(exc)

    return render_page(**ctx)


if __name__ == "__main__":
    print("Открой http://127.0.0.1:5055")
    app.run(host="127.0.0.1", port=5055, debug=False)
