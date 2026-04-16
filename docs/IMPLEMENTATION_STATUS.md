# Estado de implementación (Abril 2026)

Este documento resume qué partes del PRD ya están implementadas en el repositorio y qué quedó parcial.

## Resumen ejecutivo

- **Completado**: las 6 tareas iniciales del plan de arranque **y el cierre de P0 de scoring PRD**.
- **Parcial**: hardening de conectores por universidad, normalización EN/ZH y observabilidad persistente.
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

## Riesgos actuales

1. **Cobertura variable por universidad**: depende de estructura HTML y calidad de páginas oficiales.
2. **Conectores aún genéricos en algunos dominios**: faltan selectores dedicados para más universidades.
3. **Observabilidad limitada**: hay logs, pero faltan métricas persistentes de extracción/calidad por fuente.

## Decisión recomendada

Priorizar P1 de `docs/NEXT_STEPS.md` antes de ampliar fuerte la cobertura de nuevas universidades, para asegurar estabilidad y calidad sostenida.
