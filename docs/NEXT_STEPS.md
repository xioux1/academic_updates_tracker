# Siguientes pasos (Roadmap técnico accionable)

Este roadmap prioriza cerrar brechas del PRD sin perder velocidad de entrega.

## P0 (1-2 semanas) — Cerrar scoring PRD y confiabilidad mínima

### 1) Job de scoring multicriterio por snapshot
- Implementar módulo dedicado (p.ej. `scoring.py`) con funciones por sub-score:
  - `admission_fit`
  - `strategic_fit`
  - `lifestyle_fit`
  - `contact_leverage`
  - `information_confidence`
- Persistir cada ejecución en `score_breakdowns` con `components` y `explanation`.
- Ejecutar scoring al final de cada `run_full_scan`.

**Definition of Done**
- Cada programa nuevo/actualizado termina con `overall_score` trazable.
- Decision Console deja de depender de cargas manuales de score.

### 2) Política de confianza y bloqueo de ranking
- Definir umbral global de confianza (configurable en `config.py`).
- Si el score de confianza cae bajo umbral, marcar programa como "no rankeable".
- Mostrar en UI la razón del bloqueo.

**Definition of Done**
- Ningún programa con confianza crítica aparece en Top-N sin advertencia explícita.

### 3) Hardening de extracción oficial
- Añadir conectores específicos por universidad (selectores/patrones dedicados).
- Tests unitarios de parsing con fixtures HTML reales.
- Backoff/retry por dominio para disminuir fallos intermitentes.

**Definition of Done**
- Tasa de éxito estable por universidad objetivo.

---

## P1 (2-4 semanas) — Calidad de datos y operaciones

### 4) Panel de calidad de datos
- Métricas por snapshot: cobertura de programas, freshness, inconsistencias, campos nulos.
- Vista en dashboard para detectar degradación temprana.

### 5) Normalización e internacionalización robusta (EN/ZH)
- Pipeline de normalización de fechas, moneda, idioma y nomenclaturas.
- Reglas para mapear variaciones de nombres de programas/departamentos.

### 6) Backfill histórico inicial
- Ejecutar corridas controladas para generar historial base de snapshots.
- Establecer baseline para tendencias de cambios.

---

## P2 (4-8 semanas) — Escalado y producto

### 7) Perfil de usuario y pesos dinámicos en UI
- Editor de `UserProfile.weights`.
- Recalcular ranking en tiempo real por perfil.

### 8) Alertas periódicas
- Digest de cambios críticos por email/Slack.
- Trigger por deadlines cercanos y cambios sensibles.

### 9) Observabilidad de jobs
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
