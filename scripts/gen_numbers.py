#!/usr/bin/env python3
"""Живые счётчики сайта (ПРЕДЛОЖЕНИЕ-18, волна ×3 W3-D). Только stdlib, Python 3.11.

«Рука пишет слова, машина пишет числа»: numbers.json рождается на сборке сайта.
  - публичные числа — из живого GitHub API (api.github.com/users/rtynbirf);
  - приватные агрегаты — из catalog.json роя, вложенного в сборку (--catalog);
  - числа собираются в каркас scripts/numbers.template.json;
  - страница читает numbers.json (подключение страницы — отдельный живой ход,
    index.html правилами волны не трогается).

Гейт: --check-index ПУТЬ — в index.html не должно остаться устаревшего литерала
«25 реп» (grep пуст); выход 1, пока литерал жив. Выход: 0 зелёный / 1 устаревшее число.
Без сети числа честно остаются пустыми (null) с пометкой — заполнятся при прогоне CI.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).resolve().parent / "numbers.template.json"
API_USER = "https://api.github.com/users/rtynbirf"
STALE = "25 реп"


def api(url):
    headers = {"User-Agent": "rtynbirf.github.io-wave3"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_template():
    if TEMPLATE.exists():
        return json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return {"generated_at": None, "source": {"api": API_USER, "catalog": None},
            "public": {"login": "rtynbirf", "repos": None}, "clusters": {}, "notes": ""}


def fetch_public(numbers):
    try:
        user = api(API_USER)
        numbers["public"] = {"login": user.get("login"), "repos": user.get("public_repos")}
    except Exception as e:
        print("  API недоступен (%s) — публичные числа останутся пустыми до прогона CI" % type(e).__name__)


def merge_catalog(numbers, catalog_path: Path):
    numbers["source"]["catalog"] = str(catalog_path)
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception as e:
        print("  catalog.json не читается (%s) — кластерные счётчики останутся пустыми" % e)
        return
    clusters = {}
    if isinstance(catalog, dict) and isinstance(catalog.get("clusters"), dict):
        for name, v in catalog["clusters"].items():
            clusters[name] = len(v) if isinstance(v, list) else v
    elif isinstance(catalog, list):
        for item in catalog:
            if isinstance(item, dict) and "cluster" in item:
                clusters[item["cluster"]] = clusters.get(item["cluster"], 0) + 1
    else:
        print("  форма catalog.json не опознана — кластерные счётчики останутся пустыми (сверить живым ходом)")
        return
    numbers["clusters"] = clusters


def check_index(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if STALE in text:
        print("ГАТ КРАСНЫЙ: в %s жив устаревший литерал «%s» — рука должна оставить слова, число отдать numbers.json" % (path, STALE))
        return 1
    print("гейт: устаревших литералов не найдено (grep пуст)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Живые счётчики сайта: numbers.json из API")
    ap.add_argument("--out", default=str(ROOT / "numbers.json"))
    ap.add_argument("--catalog", default=None, help="catalog.json роя, вложенный в сборку")
    ap.add_argument("--check-index", default=None, help="гейт устаревших чисел в index.html")
    args = ap.parse_args()

    if args.check_index:
        return check_index(Path(args.check_index))

    numbers = load_template()
    numbers["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    numbers["notes"] = ("(заполняется скриптом scripts/gen_numbers.py при каждом прогоне; "
                        "clusters — при вложении catalog.json роя в сборку)")
    fetch_public(numbers)
    if args.catalog:
        merge_catalog(numbers, Path(args.catalog))
    out = Path(args.out)
    out.write_text(json.dumps(numbers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("numbers.json записан: %s (public.repos=%s, кластеров: %d)"
          % (out, numbers["public"].get("repos"), len(numbers.get("clusters", {}))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
