# Siguientes pasos (Roadmap técnico accionable)

Este roadmap prioriza cerrar brechas del PRD sin perder velocidad de entrega.

## Estado de avance

- ✅ **P0 cerrado**: scoring PRD automático por snapshot, umbral global de confianza y bloqueo de ranking aplicado en consola.
- ▶️ **En foco actual**: P1 de calidad/operación para estabilizar cobertura y observabilidad.

## P1 (2-4 semanas) — Calidad de datos y operaciones

### 1) Hardening de extracción oficial por universidad (✅ completado en conectores prioritarios)
- Se añadieron perfiles por dominio/universidad para: **SUSTech, HITSZ, SZU, SIGS Tsinghua y PKU Shenzhen Graduate School**.
- Se dejó activa cadena de fallback por dominio: **selector-first → table parsing → regex**.
- Se incorporaron políticas de retry/backoff exponencial con jitter por dominio (`DEFAULT_RETRY_POLICY`, `_retry_policy_for_url`) para reducir fallos intermitentes; logging enriquecido de intentos, duración y status final.
- Se persisten metadatos técnicos de conector (`selectors_used`, `connector_version`, `normalizer_used`) para troubleshooting.
- Fixtures HTML reales por conector (SUSTech, HITSZ, SZU, Tsinghua SIGS, PKU SGS) y tests parametrizados de contrato que validan todos los `CRITICAL_FIELD_KEYS` + evidencia trazable.
- Tests de regresión para edge cases de fecha/moneda y table-fallback.
- Tests unitarios de política de retry por hostname y cumplimiento de intentos mínimos.

**Definition of Done**
- ✅ Tasa de éxito estable por universidad objetivo (conectores prioritarios Shenzhen).
- ✅ Suite de contrato en CI que detecta regresiones de parsing por conector.

### 2) Panel de calidad de datos
- Métricas por snapshot: cobertura de programas, freshness, inconsistencias, campos nulos.
- Vista en dashboard para detectar degradación temprana.

**Definition of Done**
 - Snapshot reciente visible con semáforos de calidad y tendencia vs snapshot previo.

### 3) Normalización e internacionalización robusta (EN/ZH)
- Pipeline de normalización de fechas, moneda, idioma y nomenclaturas.
- Reglas para mapear variaciones de nombres de programas/departamentos.

### 4) Backfill histórico inicial
- Ejecutar corridas controladas para generar historial base de snapshots (`run_backfill.py`).
- Definir ventana operativa de 4–8 semanas (default recomendado: 6).
- Definir frecuencia por fuente para controlar carga:
  - semanal: `google_scholar`, `arxiv`, `rss`, `university`
  - quincenal: `github`, `cnki`, `baidu_scholar`
- Etiquetar snapshots de backfill en `run_metadata` para separarlos de producción.
- Persistir y validar `change_summary` por snapshot para monitorear estabilidad de diffs.
- Aplicar criterio de corte si la calidad de extracción cae bajo umbral.

---

## P2 (4-8 semanas) — Escalado y producto

### 5) Perfil de usuario y pesos dinámicos en UI
- Editor de `UserProfile.weights`.
- Recalcular ranking en tiempo real por perfil.

### 6) Alertas periódicas
- Digest de cambios críticos por email/Slack.
- Trigger por deadlines cercanos y cambios sensibles.

### 7) Observabilidad de jobs
- Persistir métricas de ejecución: duración, errores por fuente, registros procesados.
- Alertar ante fallos consecutivos por universidad/fuente.

---

## Checklist operativo semanal

1. Ejecutar scan completo.
2. Verificar cambios sensibles detectados.
3. Revisar programas con `inconsistency_flag`.
4. Validar Top-N y docentes recomendados.
5. Ajustar seeds/conectores según fallos observados.

---

## Entregable objetivo de corto plazo

En 2 semanas, el sistema debería ofrecer:
- ranking reproducible y explicable por snapshot;
- trazabilidad campo-a-evidencia en programas críticos;
- y una consola de decisión confiable para priorizar postulación/contacto.
