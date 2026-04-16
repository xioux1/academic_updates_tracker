# AcademicRadar — Master Intelligence System (Shenzhen)

AcademicRadar evolucionó de un radar académico general a un **sistema de inteligencia de admisión** para másteres en Shenzhen.

Este repositorio hoy combina:
- Ingesta de fuentes académicas generales (Scholar/arXiv/GitHub/CNKI/Baidu/RSS).
- Ingesta de fuentes oficiales universitarias para programas de máster.
- Versionado por snapshot y auditoría de cambios sensibles.
- Consola de decisión para priorizar programas y docentes.

## Estado actual

- ✅ Las 6 tareas iniciales del plan de implementación están incorporadas en código (modelo de datos PRD, tracking de universidades/programas, snapshots/diff, consola de decisión y semillas configurables).
- ⚠️ El scoring multicriterio completo del PRD está parcialmente implementado (existe infraestructura `score_breakdowns`, pero faltan jobs de cálculo sistemático por sub-score).

Ver detalle en:
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/NEXT_STEPS.md`
- `docs/PRD_Master_Intelligence_System_Shenzhen.md`

## Arquitectura funcional

1. **Discovery & Extraction**
   - `scraper.py` descubre URLs de admisión desde seeds de universidades y extrae campos críticos de programas.
2. **Storage & Audit**
   - `database.py` persiste entidades del PRD (`universities`, `programs`, `faculty`, `source_documents`, `evidence_snippets`, `scan_snapshots`, `audit_records`, `score_breakdowns`, etc.).
3. **Analysis**
   - `analyzer.py` mantiene el análisis de findings (Claude) del radar clásico.
4. **Decision UI**
   - `views/decision_console.py` muestra ranking Top-N, cambios desde último snapshot, freshness y recomendación de docentes.

## Estructura rápida

- `app.py`: entrada Streamlit y navegación.
- `scraper.py`: scans generales + pipeline Shenzhen.
- `database.py`: schema y operaciones SQLite.
- `views/`: pantallas UI, incluyendo Decision Console.
- `docs/`: PRD, estado de implementación y roadmap operativo.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

Variables útiles:
- `DB_PATH`
- `UNIVERSITY_SOURCE_SEEDS` (JSON)
- `SCRAPER_DELAY`, `ARXIV_MAX_RESULTS`, `SCHOLAR_MAX_RESULTS`, `DAYS_LOOKBACK`
- `ANTHROPIC_API_KEY` (si se usa análisis con Claude)

### Corrida semanal (producción)

```bash
python run_weekly.py
```

### Backfill histórico operativo (nuevo)

Backfill recomendado: **últimas 4–8 semanas** (default: 6), en corridas secuenciales con control de carga.

```bash
python run_backfill.py --weeks 6 --sleep-between-runs 15 --no-mail
```

Frecuencia sugerida por fuente durante backfill (`source_frequency_weeks`):
- semanal: `google_scholar`, `arxiv`, `rss`, `university`
- quincenal: `github`, `cnki`, `baidu_scholar`

Cada snapshot de backfill queda etiquetado en `run_metadata` con:
- `run_kind=backfill`
- ventana (`backfill_window_start`, `backfill_window_end`)
- `source_frequency_weeks`

Además, cada corrida valida que `change_summary` persistido en `summary_json` coincida con el `change_summary` calculado durante ejecución.

#### Criterio de corte por calidad

El backfill se detiene si el índice de calidad cae bajo umbral:

```text
quality_ratio = 0.7 * coverage_ratio + 0.3 * freshness_ratio
```

Umbral por defecto: `BACKFILL_MIN_QUALITY_RATIO=0.55` (configurable por variable de entorno o `--min-quality`).

## Roadmap inmediato

Los siguientes pasos técnicos priorizados están documentados en `docs/NEXT_STEPS.md` y se enfocan en:
- consolidar scoring PRD explicable;
- robustecer conectores por universidad;
- y endurecer calidad/observabilidad de datos.
