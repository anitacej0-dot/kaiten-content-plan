# Первый запуск (по шагам)

## 1. Установить Python 3.11+

Windows (PowerShell):
```powershell
winget install Python.Python.3.12
```
Или скачайте с https://python.org и при установке отметьте **«Add python.exe to PATH»**.

Проверка:
```powershell
python --version
```
Если печатается только «Python» без версии — в PATH стоит заглушка Microsoft Store.
Установите настоящий Python (команда выше) или отключите заглушку:
Параметры → Приложения → «Псевдонимы выполнения приложения» → выключить `python.exe`.

## 2. Создать окружение и поставить зависимости

Из корня проекта:
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 3. Положить данные

Минимум — Excel контент-плана в `inputs\current_cycle\`. Аналитику (Roistat, Метрика) —
в `inputs\current_cycle\analytics\`. Подробнее — `docs/inputs.md`.

## 4. Запустить pipeline

```powershell
.venv\Scripts\python scripts\run_pipeline.py
```
Или горизонт/старт явно:
```powershell
.venv\Scripts\python scripts\run_pipeline.py --start 2026-07-28 --weeks 7
```

## 5. Посмотреть результат

Папка `outputs\<дата>_<дата>\`:
- начните с `plan_summary.md` (сводка и вопросы к вам);
- откройте `content_plan.xlsx` в Excel;
- при вопросах — `01_input_audit.md` и `10_validation_report.md`.

## 6. Внести решения и пересобрать

Правки — в `inputs\current_cycle\decisions.csv` (шаблон в `inputs\templates\`),
затем снова `run_pipeline.py`. Решения не теряются.

Готово. Дальше — `docs/monthly_usage.md`.
