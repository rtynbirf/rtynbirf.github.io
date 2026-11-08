# AGENT-READINESS

Метрика `agent-readiness` (0-100) — наш собственный повторяемый статический аудит готовности сайтов роя к browsing-агентам. Lighthouse-семейство «Agentic Browsing» в CI отдельно не ставится: внешний инструмент может отличаться версией, а наше число само себя пишет в CI.

Формула: 30 очков за llms.txt в корне (существует, непуст, упоминает PULSE/README — это машинный индекс мембраны, не SEO) + 70 очков поровну на аудируемые страницы: `<html lang>`, meta viewport, aria-атрибуты/landmark-роли, доля img с alt (пустой alt допустим как декоративный, отсутствующий — находка), явные width/height у img (CLS-гигиена), ровно один h1, порядок заголовков без скачков. Точные веса — в шапке tools/agent_readiness.py.

Аудируются четыре страницы: index.html, elevator-26.html, lacornia.html, wave3/kiosk-player.html (список задаётся флагом --pages).

Как поднять число: пройтись по таблице находок в отчёте — добавить lang и viewport, alt и width/height у картинок, оставить один h1 без скачков уровней, добавить aria/landmark-разметку.

Где смотреть: Actions → воркфлоу agent-readiness → шаг «Живой аудит четырёх страниц роя» → $GITHUB_STEP_SUMMARY (число и таблица находок). Гейт: ниже 60 — шаг падает с exit 1.

Связи: llms.txt — машинный индекс мембраны для агентов, это не SEO; человеческую доступность киоска проверяет соседний гейт kiosk-a11y-gate — эти аудиты про разное и не дублируют друг друга.

Запуск локально: `python3 tools/agent_readiness.py --selftest`, затем `python3 tools/agent_readiness.py --root . --pages index.html,elevator-26.html,lacornia.html,wave3/kiosk-player.html`.
