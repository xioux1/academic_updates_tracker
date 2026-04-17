# Siguientes pasos (Roadmap técnico accionable)

Este roadmap prioriza cerrar brechas del PRD sin perder velocidad de entrega.

## Estado de avance

- ✅ **P0 cerrado**: scoring PRD automático por snapshot, umbral global de confianza y bloqueo de ranking aplicado en consola.
- ✅ **P1 cerrado**: calidad de datos, alertas periódicas y observabilidad de jobs implementados.
- ▶️ **En foco actual**: P2 — escalado de conectores y refinamiento de normalización.

---

## P1 (✅ Completo) — Calidad de datos y operaciones

### 1) Hardening de extracción oficial por universidad ✅
- Conectores genéricos con arquitectura de retries por dominio implementados.
- Tests unitarios de parsing con fixtures HTML reales (`tests/scraper/`).
- Backoff/retry por conector en `scraper.py`.

### 2) Panel de calidad de datos ✅
- Nueva vista `views/quality.py` en la navegación principal ("📈 Calidad").
- Muestra: semáforo P0, métricas del último snapshot (cobertura, freshness, inconsistencias, nulos críticos).
- Gráfico de tendencia histórica (línea) sobre últimos 20 snapshots.
- Tabla de breakdown por universidad y por conector.
- Drill-down en programas con `inconsistency_flag = 1` y sus valores contradictorios por fuente.
- Registro de cambios sensibles (audit_records) de los últimos 14 días.

### 3) Normalización e internacionalización robusta (EN/ZH) ✅
- Pipeline de normalización de fechas, moneda, idioma y nomenclaturas en `normalization.py`.
- Reglas para mapear variaciones de nombres en `PROGRAM_NAME_VARIANTS` / `DEPARTMENT_NAME_VARIANTS`.

### 4) Backfill histórico inicial ✅
- `run_backfill.py` con ventana configurable, frecuencia por fuente, quality gates y etiquetado de snapshots.

---

## P2 (▶️ En foco) — Escalado y producto

### 5) Alertas periódicas ✅ (implementado)
- `check_and_send_alerts()` en `digest.py`:
  - Detecta programas con deadline en los próximos 14 días (`get_upcoming_deadline_programs`).
  - Detecta cambios sensibles vía `audit_records` (`get_recent_audit_changes`).
  - Envía email HTML+texto con tablas de urgencia y diff de campos.
- Llamado automáticamente en APScheduler (`app.py`) y en `run_weekly.py` (paso 3/4).
- CLI: `python run_weekly.py --no-alerts` para saltar alertas.

### 6) Observabilidad de jobs ✅ (implementado)
- `run_weekly.py` registra duración por paso con `_step()` context manager.
- `get_consecutive_scan_failures()` en `database.py` detecta patrones de fallo recurrente.
- `_warn_consecutive_failures()` emite warning al final de cada run.
- **Pendiente**: dashboard UI para métricas de ejecución (duración por paso, historial de errores).

### 7) Conectores dedicados por universidad (pendiente)
- Añadir selectores CSS/XPath específicos para SUSTech, HITSZ, SZU en clases dedicadas.
- Validar contra fixtures HTML actualizados.
- Agregar tasa de éxito por universidad al panel de calidad.

### 8) Perfil de usuario y pesos dinámicos en UI (pendiente)
- Editor de `UserProfile.weights` ya implementado en `views/settings.py`.
- Falta: recalcular ranking en tiempo real al cambiar perfil activo sin recargar página.

---

## Checklist operativo semanal

1. Ejecutar scan completo (`python run_weekly.py`).
2. Revisar panel "📈 Calidad" — semáforo P0 y tendencia.
3. Verificar cambios sensibles detectados (audit drill-down en panel de calidad).
4. Revisar programas con `inconsistency_flag`.
5. Validar Top-N y docentes recomendados en Decision Console.
6. Ajustar seeds/conectores según fallos observados.

---

## Entregable objetivo de corto plazo

En 2 semanas, el sistema debería ofrecer:
- Conectores dedicados con tasa de éxito ≥ 80% por universidad objetivo.
- Panel de calidad con historial de tendencias y drill-down accionable.
- Alertas de deadline disparadas automáticamente, sin intervención manual.
