# Estado de implementación (Abril 2026)

Este documento resume qué partes del PRD ya están implementadas en el repositorio y qué quedó parcial.

## Resumen ejecutivo

- **Completado**: las 6 tareas iniciales del plan de arranque **y el cierre de P0 de scoring PRD**.
- **Completado**: hardening de conectores por universidad en dominios prioritarios Shenzhen (SUSTech/HITSZ/SZU + SIGS Tsinghua + PKU Shenzhen Graduate School), incluyendo fallback chain y retry por dominio.
- **En progreso (P1-3)**: normalización EN/ZH reforzada (idioma/fecha/moneda + variantes de programa/departamento).
- **Pendiente**: escalado operativo (alertas, métricas avanzadas, calidad por fuente en dashboard).

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
- Retry/backoff exponencial con jitter por dominio (`DEFAULT_RETRY_POLICY`, `_retry_policy_for_url`); logging enriquecido de intentos, espera y status final.
- Metadatos técnicos de conector (`selectors_used`, `normalizer_used`, `connector_version`) para trazabilidad de troubleshooting.

## Tarea 3 — Snapshots y drift monitor (✅)

Implementado en `database.py` + `scraper.py`:
- Creación/cierre de snapshots por corrida.
- Etiquetado de entidades por snapshot (`snapshot_entities`).
- Detección de cambios sensibles e inconsistencias con registro en `audit_records`.
- Resumen de cambios para consumo en UI.

## Tarea 4 — Motor de scoring explicable (✅ Completado)

Implementado en `scoring.py` + `scraper.py` + `database.py` + `config.py` + `views/decision_console.py`:
- Job automático de scoring por snapshot (`score_snapshot`) ejecutado al final de `run_full_scan`.
- Sub-scores PRD calculados y persistidos (`admission_fit`, `strategic_fit`, `lifestyle_fit`, `contact_leverage`, `information_confidence`).
- Persistencia trazable en `score_breakdowns` (`score_value`, `components`, `explanation`, `confidence_score`).
- Umbral global de confianza (`MIN_CONFIDENCE_TO_RANK`) para bloquear programas de baja confiabilidad.
- Decision Console actualizada para mostrar bloqueos de ranking y motivo principal.

Notas:
- El scoring es reproducible por snapshot y desacoplado del render de UI.
- Se mantiene prioridad por trazabilidad: no hay score útil sin `components` + `explanation`.

## Tarea 5 — Decision Console (✅)

Implementado en `views/decision_console.py` y enrutado desde `app.py`:
- Top-N programas por score.
- Delta de score respecto al corte anterior.
- Motivos de cambio por auditoría de campos sensibles.
- Filtros por idioma/universidad/confianza/deadline.
- Indicador de freshness.
- Ranking de docentes por objetivo con score heurístico + confianza.

## Tarea 6 — Plan por sprints y continuidad (✅)

Se consolida con documentación operativa en:
- `README.md` (overview y arquitectura actualizada).
- `docs/NEXT_STEPS.md` (priorización P0/P1/P2 y entregables).

---

## Tarea 7 — Tests de contrato y fixtures de conectores (✅ Completado)

Implementado en `tests/scraper/`:
- Fixtures HTML reales por conector (`sustech_program.html`, `hitsz_program.html`, `szu_program.html`, `tsinghua_sigs_program.html`, `pku_sgs_program.html`).
- Test parametrizado `test_connector_fixtures_extract_all_critical_fields_and_evidence` que valida: todos los `CRITICAL_FIELD_KEYS` presentes, evidencia no-`not_found` por campo, y `selectors_used` correcto.
- Tests de regresión para edge cases de fecha/moneda (`date_currency_edge_cases.txt`) y table-fallback (`table_fallback_edge_cases.html`).
- Tests unitarios de política de retry: selección por hostname (`test_retry_policy_selection_uses_hostname_profile`) y cumplimiento de intentos mínimos (`test_fetch_retry_enforces_minimum_attempts`).
- Tests de calidad de snapshot (`test_extraction_quality_snapshot.py`).

---

## Riesgos actuales

1. **Cobertura variable por universidad**: depende de estructura HTML y calidad de páginas oficiales.
2. **Observabilidad limitada**: hay logs y metadatos por conector, pero faltan métricas agregadas persistentes de extracción/calidad por fuente.

## Decisión recomendada

Mantener foco en panel de calidad/observabilidad agregada y operación continua de conectores ya hardenizados antes de ampliar cobertura a nuevas regiones.
