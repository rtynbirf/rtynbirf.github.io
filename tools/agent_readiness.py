#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_readiness.py — свой статический аудит «агент-читаемости» сайтов роя.

Зачем: сайты роя — витрина для людей И для browsing-агентов. Соседний гейт
kiosk-a11y-gate проверяет человеческую доступность киоска; этот аудит — про
машинную сторону мембраны: llms.txt (машинный индекс, не SEO), html[lang],
meta viewport, aria-атрибуты/landmark-роли, alt у картинок, гигиена CLS
(явные width/height у img), ровно один h1 и порядок заголовков без скачков.

Только stdlib. Сеть не нужна: страницы читаются из каталога (--root);
опционально есть живой режим --base-url (страницы снимаются по HTTP через
urllib) — для разовой проверки опубликованного сайта.

Метрика: agent-readiness: NN (0..100). Формула прозрачная, веса ниже.
Гейт: exit 1, если число ниже порога 60.

ВЕСА (сумма ровно 100):
  Глобально (30 очков):
    llms.txt в корне существует и непуст ................. 20
    llms.txt упоминает PULSE или README .................. 10
  Страницы (в сумме 70 очков, поровну на каждую страницу;
  внутри страницы каждая проверка имеет долю от 100%):
    html[lang] ........................................... 10%
    meta viewport с непустым content ..................... 10%
    aria-атрибуты или landmark-роли ...................... 15%
    доля img с alt ....................................... 20%
    доля img с явными width и height (CLS-гигиена) ....... 15%
    ровно один h1 ........................................ 15%
    порядок заголовков без скачков уровней ............... 15%
  Правила: отсутствующий атрибут alt — находка, пустой alt
  допускается (декоративная картинка); если у страницы нет
  ни одной картинки — обе img-проверки зачитываются;
  скачок уровней — переход hN -> hM, где M > N+1.
"""

import argparse
import os
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser

GATE = 60  # порог гейта: ниже — провал (exit 1)

# Landmark-роли WAI-ARIA и семантические элементы-ориентиры, которые
# агент способен прочитать как структуру страницы.
LANDMARK_ROLES = {
    'banner', 'main', 'navigation', 'contentinfo',
    'complementary', 'search', 'form', 'region',
}
SEMANTIC_LANDMARKS = {'main', 'nav', 'header', 'footer', 'aside'}
HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

GLOBAL_WEIGHTS = {'llms_exists': 20, 'llms_mentions': 10}
PAGE_BLOCK = 70  # суммарный вес страничных проверок на все страницы
PAGE_WEIGHTS = {
    'lang': 10, 'viewport': 10, 'aria': 15, 'alt': 20,
    'dims': 15, 'h1': 15, 'order': 15,  # сумма = 100
}


class PageAuditor(HTMLParser):
    """Собирает признаки агент-читаемости одной HTML-страницы."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None            # атрибут lang у <html>
        self.viewport = False       # meta viewport с непустым content
        self.imgs = []              # [{'alt': bool, 'dims': bool}, ...]
        self.aria_hits = 0          # сколько aria-* атрибутов встречено
        self.landmark = False       # landmark-роль или семантический элемент
        self.h1_count = 0
        self.head_levels = []       # уровни заголовков в порядке документа

    def handle_starttag(self, tag, attrs):
        amap = dict(attrs)
        if tag == 'html':
            self.lang = amap.get('lang')
        elif tag == 'meta' and (amap.get('name') or '').strip().lower() == 'viewport':
            if (amap.get('content') or '').strip():
                self.viewport = True
        elif tag == 'img':
            self.imgs.append({
                'alt': 'alt' in amap,
                'dims': 'width' in amap and 'height' in amap,
            })
        for key in amap:
            if key.lower().startswith('aria-'):
                self.aria_hits += 1
                break
        role = (amap.get('role') or '').strip().lower()
        if role in LANDMARK_ROLES or tag in SEMANTIC_LANDMARKS:
            self.landmark = True
        if tag in HEADINGS:
            self.head_levels.append(int(tag[1]))
            if tag == 'h1':
                self.h1_count += 1


def heading_skips(levels):
    """Число скачков уровней заголовков (например, h2 сразу на h4)."""
    skips = 0
    prev = None
    for lvl in levels:
        if prev is not None and lvl > prev + 1:
            skips += 1
        prev = lvl
    return skips


def check_llms(root):
    """Проверка llms.txt в корне: существует, непуст, упоминает PULSE/README."""
    path = os.path.join(root, 'llms.txt')
    if not os.path.isfile(path):
        return {'exists': False, 'mentions': False,
                'finds': ['llms.txt отсутствует в корне']}
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError as exc:
        return {'exists': False, 'mentions': False,
                'finds': ['llms.txt не читается: %s' % exc]}
    if not text.strip():
        return {'exists': True, 'mentions': False,
                'finds': ['llms.txt пуст']}
    low = text.lower()
    if 'pulse' not in low and 'readme' not in low:
        return {'exists': True, 'mentions': False,
                'finds': ['llms.txt не упоминает PULSE и README']}
    return {'exists': True, 'mentions': True, 'finds': []}


def load_page_text(root, page, base_url):
    """Текст страницы из каталога либо (живой режим) по HTTP. (текст, ошибка)."""
    if base_url:
        url = base_url.rstrip('/') + '/' + page
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
            return raw.decode('utf-8', errors='replace'), None
        except Exception as exc:  # сеть/HTTP — честная находка, не падение
            return None, 'живой режим, страница не получена: %s' % exc
    path = os.path.join(root, page)
    if not os.path.isfile(path):
        return None, 'файл не найден: %s' % page
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read(), None
    except OSError as exc:
        return None, 'файл не читается: %s' % exc


def audit_page(text):
    """Разбор страницы: (внутренняя готовность 0..100, список находок)."""
    auditor = PageAuditor()
    try:
        auditor.feed(text)
        auditor.close()
    except Exception as exc:
        return 0, ['HTML не разобран: %s' % exc]
    finds = []
    pts = 0
    if auditor.lang:
        pts += PAGE_WEIGHTS['lang']
    else:
        finds.append('<html> без lang')
    if auditor.viewport:
        pts += PAGE_WEIGHTS['viewport']
    else:
        finds.append('нет meta viewport')
    if auditor.aria_hits > 0 or auditor.landmark:
        pts += PAGE_WEIGHTS['aria']
    else:
        finds.append('нет aria-атрибутов и landmark-ролей')
    total_imgs = len(auditor.imgs)
    if total_imgs == 0:
        pts += PAGE_WEIGHTS['alt'] + PAGE_WEIGHTS['dims']  # зачёт: картинок нет
    else:
        with_alt = sum(1 for img in auditor.imgs if img['alt'])
        pts += PAGE_WEIGHTS['alt'] * with_alt / total_imgs
        if with_alt < total_imgs:
            finds.append('img без alt: %d из %d' % (total_imgs - with_alt, total_imgs))
        with_dims = sum(1 for img in auditor.imgs if img['dims'])
        pts += PAGE_WEIGHTS['dims'] * with_dims / total_imgs
        if with_dims < total_imgs:
            finds.append('img без width/height (CLS): %d из %d' % (total_imgs - with_dims, total_imgs))
    if auditor.h1_count == 1:
        pts += PAGE_WEIGHTS['h1']
    else:
        finds.append('h1: %d (нужно ровно один)' % auditor.h1_count)
    skips = heading_skips(auditor.head_levels)
    if skips == 0:
        pts += PAGE_WEIGHTS['order']
    else:
        finds.append('скачков уровней заголовков: %d' % skips)
    return pts, finds


def run_audit(root, pages, base_url=None):
    """Полный аудит: (score 0..100, markdown-отчёт)."""
    llms = check_llms(root)
    total = 0.0
    if llms['exists']:
        total += GLOBAL_WEIGHTS['llms_exists']
    if llms['mentions']:
        total += GLOBAL_WEIGHTS['llms_mentions']
    per_page = PAGE_BLOCK / len(pages)
    rows = []  # (где, готовность%, находки)
    for find in llms['finds']:
        rows.append(('llms.txt (корень)', '-', find))
    for page in pages:
        text, err = load_page_text(root, page, base_url)
        if err is not None:
            rows.append((page, '0%', err))
            continue
        pts, finds = audit_page(text)
        total += per_page * pts / 100.0
        for find in finds:
            rows.append((page, '%d%%' % int(round(pts)), find))
    score = max(0, min(100, int(round(total))))
    lines = ['# agent-readiness: %d' % score, '']
    lines.append('Формула и веса — в шапке tools/agent_readiness.py; гейт: ниже %d — exit 1.' % GATE)
    lines.append('')
    if rows:
        lines.append('| где | готовность страницы | находка |')
        lines.append('|---|---|---|')
        for where, share, find in rows:
            lines.append('| %s | %s | %s |' % (where, share, find))
    else:
        lines.append('Находок нет: все проверки зачтены.')
    lines.append('')
    return score, '\n'.join(lines)


POSITIVE_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Позитивный синтетический пример</title>
</head>
<body>
<header><h1>Единственный заголовок первого уровня</h1></header>
<nav aria-label="Основная навигация"><a href="#razdel">раздел</a></nav>
<main role="main">
<h2>Раздел</h2>
<p>Текст страницы.</p>
<h3>Подраздел</h3>
<p>Ещё текст.</p>
<img src="hero.jpg" alt="Обложка выпуска" width="640" height="360">
<img src="decor.png" alt="" width="16" height="16">
</main>
<footer role="contentinfo"><p>Подвал.</p></footer>
</body>
</html>
"""

NEGATIVE_HTML = """<!DOCTYPE html>
<html>
<head><title>Негативный синтетический пример</title></head>
<body>
<h1>Первый заголовок</h1>
<h1>Второй заголовок</h1>
<h4>Скачок уровня после h1</h4>
<img src="a.jpg">
<img src="b.jpg" alt="Есть alt">
</body>
</html>
"""

LLMS_GOOD = """# Машинный индекс роя

- PULSE.md — пульс роя: живые числа и последний отчёт.
- README.md — что это за витрина и как ей пользоваться.
"""


def selftest():
    """Самопроверка без сети: позитив выше порога, негатив — ниже. 0/1."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, 'good')
        os.makedirs(good)
        with open(os.path.join(good, 'llms.txt'), 'w', encoding='utf-8') as fh:
            fh.write(LLMS_GOOD)
        with open(os.path.join(good, 'page.html'), 'w', encoding='utf-8') as fh:
            fh.write(POSITIVE_HTML)
        pos_score, _ = run_audit(good, ['page.html'])
        print('позитив: agent-readiness %d (порог %d)' % (pos_score, GATE))
        if pos_score < GATE:
            ok = False
            print('провал: позитив ожидаемо выше порога, а он ниже')
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, 'bad')
        os.makedirs(bad)
        with open(os.path.join(bad, 'llms.txt'), 'w', encoding='utf-8') as fh:
            fh.write('')  # пустой llms.txt — глобальные очки сгорают
        with open(os.path.join(bad, 'page.html'), 'w', encoding='utf-8') as fh:
            fh.write(NEGATIVE_HTML)
        neg_score, _ = run_audit(bad, ['page.html'])
        print('негатив: agent-readiness %d (порог %d)' % (neg_score, GATE))
        if neg_score >= GATE:
            ok = False
            print('провал: негатив ожидаемо ниже порога, а он выше')
    if ok:
        print('SELFTEST OK')
        return 0
    print('SELFTEST FAIL')
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Статический аудит агент-читаемости сайтов роя (метрика agent-readiness).')
    ap.add_argument('--root', default='.',
                    help='корень сайта: здесь лежат llms.txt и страницы (по умолчанию .)')
    ap.add_argument('--pages',
                    default='index.html,elevator-26.html,lacornia.html,wave3/kiosk-player.html',
                    help='страницы для аудита через запятую')
    ap.add_argument('--base-url', default=None,
                    help='живой режим: снимать страницы по HTTP с этого адреса вместо каталога')
    ap.add_argument('--selftest', action='store_true',
                    help='самопроверка на встроенной синтетике, без сети')
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    pages = [p.strip() for p in args.pages.split(',') if p.strip()]
    if not pages:
        print('ошибка: список страниц пуст', file=sys.stderr)
        return 2
    score, report = run_audit(args.root, pages, args.base_url)
    print(report)
    if score < GATE:
        print('гейт: %d < %d — провал' % (score, GATE), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
