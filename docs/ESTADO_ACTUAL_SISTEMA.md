# Estado actual del sistema (auditoría técnica)

Fecha de revisión: 2026-04-16 (UTC)

## Resumen ejecutivo

**Estado general:** el sistema actual **sí está ejecutado y operativo** como `AcademicRadar`, pero **no está listo aún** para el objetivo nuevo de “Master Intelligence System — Shenzhen”.

- ✅ **Ejecutado hoy:** pipeline de monitoreo académico (scraping multi-fuente + análisis LLM + digest + dashboard).
- ⚠️ **Parcial:** scheduler semanal y ejecución manual desde UI, dependiente de credenciales/entorno.
- ❌ **Faltante crítico para MIS:** entidades de universidades/programas/faculty de admisión, scoring de fit de admisión, auditoría de drift por requisitos/deadlines y consola de decisión orientada a másters.

---

## 1) Qué está ejecutado (implementado en código)

## A. Ingesta y tracking (AcademicRadar actual)
- Base de datos SQLite con tablas productivas para:
  - `professors`, `keywords`, `sources`, `findings`, `digests`, `scan_history`.
- Seed inicial de profesores, keywords y fuentes.
- Scraping multi-fuente implementado:
  - Google Scholar (con toggle por entorno), arXiv, GitHub, CNKI, Baidu Scholar, RSS.
- Dedupe por URL (en `findings.url` único) y registro de historial de scan.

**Conclusión:** esta capa está ejecutada para “hallazgos académicos”, no para “catálogo de admisiones de máster”.

## B. Análisis inteligente
- Integración con API de Anthropic para analizar findings no analizados.
- Prompt estructurado y guardado de:
  - resumen, score de relevancia, razón, actionable, sugerencia, traducción.

**Conclusión:** ejecutado para relevancia de hallazgos, no para scoring de admisión/fit de programa.

## C. Digest y reporting
- Digest semanal en JSON + render HTML/texto.
- Envío por SMTP (si credenciales están completas).
- Persistencia de digest en DB.

**Conclusión:** ejecutado y funcional bajo credenciales correctas.

## D. Interfaz y operación
- App Streamlit con vistas: Dashboard, Profesores, Keywords, Findings, Digest, Configuración.
- Ejecución manual del pipeline desde UI (scan + análisis + digest).
- Scheduler semanal APScheduler con lock por PID para evitar duplicación.
- Script standalone `run_weekly.py` para ejecución completa por CLI/cron/CI.

**Conclusión:** operación diaria/semanal implementada.

---

## 2) Qué falta ejecutar para cumplir el objetivo MIS-Shenzhen

## Bloque 1 — Modelo de datos de admisión (NO ejecutado)
Falta crear entidades núcleo del nuevo producto:
- `universities`, `schools_departments`, `programs`, `faculty_profiles`, `publications`, `audit_records`, `score_breakdowns`, `snapshots`, `source_documents`, `evidence_snippets`, `user_profile_weights`.

## Bloque 2 — Crawlers de admisión oficial (NO ejecutado)
Falta implementar conectores específicos para:
- páginas oficiales de admisión,
- graduate schools,
- páginas de programas de máster,
- páginas faculty/lab institucionales.

## Bloque 3 — Normalización de programas (NO ejecutado)
Falta parser para campos críticos:
- idioma, duración, tuition, becas, requisitos, documentos, deadlines,
- supervisor/interview/thesis/internship signals.

## Bloque 4 — Scoring MIS (NO ejecutado)
Falta motor de sub-scores:
- admission_fit,
- strategic_fit,
- lifestyle_fit,
- contact_leverage,
- information_confidence,
- y score global con pesos configurables.

## Bloque 5 — Auditoría y drift de admisión (NO ejecutado)
Falta comparar snapshots para detectar:
- cambios de TOEFL/HSK,
- cambios de deadlines,
- cambios de tuition,
- altas/bajas de programas,
- contradicciones entre fuentes oficiales.

## Bloque 6 — Consola de decisión (NO ejecutado)
Faltan vistas orientadas a decisión de admisión:
- ranking Top-N de programas para tu perfil,
- tablero de cambios semanales por impacto,
- tablero de docentes sponsoreables por programa/universidad.

---

## 3) ¿Está todo listo?

**Respuesta corta: NO.**

El sistema actual está listo como **AcademicRadar de vigilancia académica**.
No está listo todavía como **Master Intelligence System de admisión para Shenzhen**.

---

## 4) Estado por semáforo

- ✅ **Listo / ejecutado:**
  - Infra base (DB + scheduler + UI + pipeline scraping/análisis/digest).
  - Operación semanal automática y manual.

- ⚠️ **Listo con dependencias externas:**
  - Análisis LLM (requiere `ANTHROPIC_API_KEY`).
  - Envío email (requiere SMTP + email destino).
  - Google Scholar en cloud (deshabilitado por defecto por bloqueo de IP; habilitable por env var).

- ❌ **No listo (objetivo MIS):**
  - Tracking de universidades/programas de admisión.
  - Faculty intelligence para admisión (no solo papers/repos).
  - Scoring de fit de máster.
  - Auditoría de drift de requisitos/deadlines.
  - Decision Console de aplicación.

---

## 5) Próxima ejecución recomendada (orden exacto)

1. Implementar nuevo esquema DB MIS (sin romper tablas actuales).
2. Cargar seed de universidades objetivo de Shenzhen.
3. Construir scraper de admisiones oficiales + parser de programas.
4. Guardar snapshots y diffs por entidad/campo.
5. Implementar scoring explícito v1 (sin inferencia opaca).
6. Construir vistas de ranking y change feed.
7. Añadir capa de inferencias explicables con evidencia.

