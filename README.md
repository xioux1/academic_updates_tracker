# AcademicRadar — Master Intelligence System (Shenzhen)

AcademicRadar es un **sistema de inteligencia de admisión** para másteres en universidades de Shenzhen.

Combina ingesta de fuentes académicas generales (Scholar/arXiv/GitHub/CNKI/Baidu/RSS) con rastreo oficial de programas universitarios, scoring multicriterio y una consola de decisión para priorizar postulaciones.

## Estado actual (Abril 2026)

| Componente | Estado |
|---|---|
| Modelo de datos PRD (universidades, programas, facultad, evidencia) | ✅ |
| Scraping oficial de programas (SUSTech, HITSZ, SZU, SIGS, PKU-SZ) | ✅ |
| Snapshots + auditoría de campos sensibles | ✅ |
| Scoring multicriterio explicable (5 sub-scores) | ✅ |
| Decision Console (Top-N, deltas, freshness, ranking docentes) | ✅ |
| Automatización semanal (APScheduler + `run_weekly.py`) | ✅ |
| Backfill histórico con quality gates | ✅ |
| Panel de calidad de datos ("📈 Calidad") | ✅ |
| Alertas automáticas por deadline y cambios sensibles | ✅ |
| Observabilidad de jobs — timing persistido + vista "🔧 Jobs" | ✅ |
| Selectores CSS dedicados para SUSTech, HITSZ, SZU, SIGS, PKU-SZ | ✅ |

Ver detalle en `docs/IMPLEMENTATION_STATUS.md` y `docs/NEXT_STEPS.md`.

---

## Arquitectura funcional

```
INGESTA                   ALMACENAMIENTO           ANÁLISIS & DECISIÓN
scraper.py ──────────► database.py (SQLite) ──► scoring.py
  ├─ universidades         ├─ universities            └─ score_breakdowns
  ├─ programas             ├─ programs
  ├─ Scholar/arXiv         ├─ scan_snapshots       analyzer.py (Claude API)
  ├─ GitHub/RSS            ├─ audit_records
  └─ CNKI/Baidu            └─ evidence_snippets    digest.py
                                                     ├─ weekly digest
                                                     └─ deadline alerts

UI (Streamlit app.py)
  ├─ 📊 Dashboard          métricas generales
  ├─ 🧭 Decision Console   ranking Top-N + docentes
  ├─ 📈 Calidad            semáforo P0, tendencias, inconsistencias
  ├─ 📬 Digest             historial de digests
  ├─ 👨‍🏫 Profesores        tracking de docentes
  ├─ 🔑 Keywords           gestión de keywords
  ├─ 📄 Findings           browser de findings
  └─ ⚙️ Configuración      perfil de usuario, pesos, seeds
```

---

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Variables de entorno clave

| Variable | Descripción | Default |
|---|---|---|
| `DB_PATH` | Ruta al archivo SQLite | `academic_radar.db` |
| `ANTHROPIC_API_KEY` | API key para análisis con Claude | — |
| `UNIVERSITY_SOURCE_SEEDS` | JSON con seeds de universidades | — |
| `SMTP_HOST/USER/PASSWORD` | Config SMTP para email | — |
| `EMAIL_TO` | Destinatario de digests y alertas | — |
| `SCRAPER_DELAY` | Segundos entre requests | `2.0` |
| `MIN_CONFIDENCE_TO_RANK` | Umbral de confianza para ranking | `0.35` |
| `BACKFILL_MIN_QUALITY_RATIO` | Quality gate para backfill | `0.55` |

---

## Scripts operativos

### Scan semanal completo
```bash
python run_weekly.py              # con email
python run_weekly.py --no-mail    # sin email
python run_weekly.py --no-alerts  # sin alerta de deadlines
```

El pipeline ejecuta 4 pasos instrumentados (con log de tiempo): scraping → análisis Claude → alertas → digest.

### Backfill histórico
```bash
python run_backfill.py --weeks 6 --sleep-between-runs 15 --no-mail
```

Frecuencia por fuente durante backfill:
- **semanal**: `google_scholar`, `arxiv`, `rss`, `university`
- **quincenal**: `github`, `cnki`, `baidu_scholar`

El backfill se corta si `quality_ratio = 0.7 × coverage + 0.3 × freshness` cae bajo `BACKFILL_MIN_QUALITY_RATIO`.

---

## Panel de calidad ("📈 Calidad")

La vista de calidad muestra por snapshot:
- **Semáforo P0** (verde/amarillo/rojo) con motivos de degradación.
- **Métricas con indicadores de tráfico**: cobertura, freshness, inconsistencias, nulos críticos.
- **Gráfico de tendencia** sobre últimos 20 snapshots.
- **Breakdown** por universidad y por conector.
- **Drill-down** de programas con valores contradictorios entre fuentes.
- **Registro de auditoría** de cambios sensibles en los últimos 14 días.

---

## Sistema de alertas

`check_and_send_alerts()` corre automáticamente en cada scan semanal:
- Detecta programas con **deadline en los próximos 14 días** (vía `derived_data.critical_fields.deadlines.normalized`).
- Detecta **cambios sensibles** en `audit_records` desde el último scan.
- Envía email HTML+texto con tabla de urgencia y diff de campos si hay algo que alertar.

---

## Despliegue en Render.com

Ver `render.yaml` para configuración de free tier (DB efímera) o paid tier ($7/mes con disco persistente).
Alternativa recomendada para persistencia sin costo: **Turso** (SQLite en cloud, free tier).
