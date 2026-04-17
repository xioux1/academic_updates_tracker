# Siguientes pasos (Roadmap técnico accionable)

## Estado de avance

- ✅ **P0 cerrado**: scoring PRD automático por snapshot, umbral global de confianza y bloqueo de ranking.
- ✅ **P1 cerrado**: calidad de datos, alertas periódicas, observabilidad de jobs.
- ✅ **P2 cerrado**: job metrics persistidos + vista UI de jobs, selectores CSS para SUSTech/HITSZ.
- **Sistema operacionalmente completo.**

---

## P1 (✅ Completo) — Calidad de datos y operaciones

### 1) Hardening de extracción oficial por universidad ✅
- Conectores con retries/backoff por dominio en `scraper.py`.
- `CONNECTOR_REGISTRY` con selectores CSS dedicados para SUSTech, HITSZ, SZU, SIGS Tsinghua, PKU-SZ.
- Cadena de fallback: `selector → regex → table`.
- Tests unitarios de parsing con fixtures HTML reales (`tests/scraper/`).

### 2) Panel de calidad de datos ✅
- `views/quality.py` — semáforo P0, métricas, tendencia histórica, inconsistencias, audit records.

### 3) Normalización robusta (EN/ZH) ✅
- `normalization.py` — fechas, moneda, idioma, nomenclaturas de programa/departamento.

### 4) Backfill histórico ✅
- `run_backfill.py` con ventana configurable, frecuencia por fuente, quality gates.

---

## P2 (✅ Completo) — Escalado y producto

### 5) Alertas periódicas ✅
- `check_and_send_alerts()` en `digest.py` — deadlines próximos + cambios sensibles.
- Email HTML+texto automático en cada scan semanal.

### 6) Observabilidad de jobs ✅
- `scan_history` gana `step_durations_json`, `total_duration_s`, `analysis_failed`, `alerts_count`.
- `run_weekly.py` persiste timing de cada paso (scraping, análisis, alertas, digest).
- `views/jobs.py` — "🔧 Jobs" en sidebar: tabla de ejecuciones, gráfico de tiempos, fallos consecutivos, botón de scan rápido.
- `get_consecutive_scan_failures()` en `database.py` detecta patrones de fallo recurrente.

### 7) Selectores CSS por universidad ✅
- `CONNECTOR_REGISTRY` actualizado para SUSTech y HITSZ con `field_selectors` y `normalizers: ["selector","regex","table"]`.
- `_record_connector_counter()` ahora registra `normalizers_used` por conector en el `summary_json` del snapshot.

---

## Checklist operativo semanal

1. Ejecutar scan (`python run_weekly.py`).
2. Revisar "📈 Calidad" — semáforo P0, tendencia.
3. Revisar "🔧 Jobs" — duración por paso, fallos consecutivos.
4. Verificar alertas enviadas (deadline próximos, cambios sensibles).
5. Validar Top-N en Decision Console.
6. Ajustar seeds/conectores si la tasa de éxito baja.

---

## Posibles mejoras futuras (sin urgencia)

- Recalculo de ranking en tiempo real al cambiar perfil activo (sin full reload).
- Vista UI de duración de steps con drill-down por fuente.
- Slack/webhook como canal alternativo al email para alertas.
- Ampliar cobertura a universidades fuera de Shenzhen.
