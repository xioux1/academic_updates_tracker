# Estado de implementación (Abril 2026)

Este documento resume qué partes del PRD ya están implementadas en el repositorio y qué quedó parcial.

## Resumen ejecutivo

- **Completado**: P0, P1 y P2 completos. Sistema operacionalmente completo.
- **Parcial**: recalculo dinámico de ranking en UI sin full reload (UX menor).
- **No urgente**: Slack/webhooks, ampliar cobertura fuera de Shenzhen.

---

## Tarea 1 — Modelo de datos PRD (✅)

Implementado en `database.py`:
- Nuevas entidades: `universities`, `schools_departments`, `programs`, `faculty`, `source_documents`, `evidence_snippets`, `snapshots`, `scan_snapshots`, `snapshot_entities`, `audit_records`, `score_breakdowns`, `user_profiles`.
- Índices para lookup y auditoría temporal.
- Soporte para separación semántica por campos JSON (`official_data`, `derived_data`, `inferred_data`) en entidades clave.

## Tarea 2 — Tracker de universidades/programas oficiales (✅)

Implementado en `scraper.py` + `config.py`:
- Seeds configurables por `UNIVERSITY_SOURCE_SEEDS`.
- Discovery de URLs candidatas de admisión.
- Extracción de campos críticos de programa desde HTML.
- Persistencia de `source_documents` y `evidence_snippets` con trazabilidad.

## Tarea 3 — Snapshots y drift monitor (✅)

Implementado en `database.py` + `scraper.py`:
- Creación/cierre de snapshots por corrida.
- Etiquetado de entidades por snapshot (`snapshot_entities`).
- Detección de cambios sensibles e inconsistencias con registro en `audit_records`.
- Resumen de cambios para consumo en UI.

## Tarea 4 — Motor de scoring explicable (✅)

Implementado en `scoring.py` + `scraper.py` + `database.py` + `config.py` + `views/decision_console.py`:
- Job automático de scoring por snapshot ejecutado al final de `run_full_scan`.
- Sub-scores PRD calculados y persistidos (`admission_fit`, `strategic_fit`, `lifestyle_fit`, `contact_leverage`, `information_confidence`).
- Persistencia trazable en `score_breakdowns`.
- Umbral global de confianza (`MIN_CONFIDENCE_TO_RANK`).
- Decision Console actualizada para mostrar bloqueos de ranking y motivo principal.

## Tarea 5 — Decision Console (✅)

Implementado en `views/decision_console.py`:
- Top-N programas por score, delta vs snapshot anterior.
- Motivos de cambio por auditoría de campos sensibles.
- Filtros por idioma/universidad/confianza/deadline.
- Indicador de freshness y ranking de docentes.

## Tarea 6 — Plan por sprints y continuidad (✅)

Documentación operativa en `README.md` y `docs/NEXT_STEPS.md`.

## Tarea 7 — Panel de calidad de datos (✅)

Implementado en `views/quality.py` (nueva vista "📈 Calidad"):
- Semáforo P0 + métricas del último snapshot con indicadores de tráfico verde/amarillo/rojo.
- Gráfico de tendencia histórica (línea) sobre últimos 20 snapshots cerrados.
- Tabla de breakdown por universidad y por conector.
- Drill-down de programas con `inconsistency_flag = 1` y valores contradictorios por fuente.
- Listado de cambios sensibles de `audit_records` de los últimos 14 días.
- Integrado en navegación de `app.py`.

## Tarea 8 — Alertas periódicas (✅)

Implementado en `digest.py` + `database.py`:
- `generate_alerts()` — detecta deadlines próximos y cambios sensibles.
- `send_alert_email()` — email HTML+texto con tablas de urgencia.
- `check_and_send_alerts()` — orquestador llamado desde `run_weekly.py` y APScheduler.
- `get_upcoming_deadline_programs()` en `database.py` — query sobre `derived_data.critical_fields.deadlines.normalized`.
- `get_recent_audit_changes()` en `database.py` — cambios sensibles desde `audit_records`.

## Tarea 9 — Observabilidad de jobs (✅ Completo)

Implementado en `run_weekly.py` + `database.py` + `views/jobs.py`:
- `scan_history` tiene `step_durations_json`, `total_duration_s`, `analysis_failed`, `alerts_count`.
- `_step()` context manager acumula tiempos en `step_times` dict; se persisten en `log_scan()`.
- `get_consecutive_scan_failures()` detecta patrones de fallo en historial de scans.
- `views/jobs.py` — "🔧 Jobs" en sidebar: tabla de ejecuciones, gráfico de tiempos por paso, fallos consecutivos, botón de scan rápido.

## Tarea 10 — Selectores CSS por universidad (✅ Completo)

Implementado en `scraper.py`:
- `CONNECTOR_REGISTRY` para SUSTech y HITSZ ahora incluye `field_selectors` por campo crítico y `normalizers: ["selector","regex","table"]`, alineándolos con SZU/SIGS/PKU-SZ.
- `_record_connector_counter()` registra `normalizers_used` (cuántas URLs usaron selector vs regex vs table) en el `connector_counters` del `summary_json` del snapshot — visible en "📈 Calidad".

---

## Riesgos actuales

1. **Conectores aún genéricos**: falta implementar selectores CSS/XPath dedicados para SUSTech, HITSZ, SZU.
2. **Deadline parsing parcial**: `normalize_date` en `normalization.py` cubre 7+ formatos pero aún puede fallar en variantes regionales (ej. fechas chinas con caracteres).
3. **Observabilidad UI incompleta**: las métricas de duración por paso se loggean pero no se persisten ni visualizan en dashboard.
