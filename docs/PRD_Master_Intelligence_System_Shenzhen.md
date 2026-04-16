# PRD Técnico — Master Intelligence System (Shenzhen)

## 1) Objetivo del producto

Construir un sistema continuo de inteligencia de admisión para programas de máster en Shenzhen que:

1. Descubra y mantenga fuentes oficiales de universidades, escuelas, programas y docentes.
2. Extraiga y normalice datos explícitos (requisitos, idioma, costos, deadlines, etc.).
3. Calcule señales derivadas e inferidas con trazabilidad.
4. Puntúe el **fit personalizado** entre usuario, programas, docentes y universidades.
5. Audite cambios en el tiempo y alerte drift/inconsistencias.
6. Presente una consola de decisión accionable.

---

## 2) Alcance

### En alcance (v1-v2)
- Universidades objetivo en Shenzhen (seed configurable).
- Programas de máster y páginas de admisión oficiales.
- Directorios de faculty y labs relevantes.
- Scoring multicriterio configurable por pesos.
- Historial de snapshots + changelog de cambios.
- Dashboard operativo para ranking y priorización.

### Fuera de alcance inicial
- Automatización de aplicaciones.
- Integración con CRM externo.
- Predicción probabilística avanzada con modelos black-box sin explicabilidad.

---

## 3) Usuarios y jobs-to-be-done

### Usuario primario
Candidato internacional que quiere optimizar admisión + calidad de vida + valor industrial en Shenzhen.

### Jobs principales
- “Encontrar los programas con mayor probabilidad de admisión y mayor retorno estratégico.”
- “Detectar con quién conviene contactar y cuándo.”
- “Entender qué cambió esta semana y cómo afecta mi shortlist.”

---

## 4) Requisitos funcionales por módulo

## A. University Tracker
**Debe**:
- Detectar universidades objetivo por seed list.
- Registrar páginas oficiales (institucional, admissions, graduate school, schools/departments).
- Mantener estado de scraping y fecha de última auditoría.

**Salida**:
- Tabla viva de universidades con `institution_score` y metadatos de cobertura.

## B. Program Tracker
**Debe extraer**:
- Nombre, grado, escuela, idioma, duración, modalidad, tuition, becas, requisitos, documentos, deadlines, portal.
- Señales explícitas: supervisor requerido, entrevista, tesis, internship, cursos visibles.

**Debe inferir**:
- Rigidez, orientación industrial/academia, dependencia de supervisor, opacidad, riesgo de mismatch.

**Salida**:
- Tabla viva de programas versionada por snapshot.

## C. Faculty Tracker
**Debe extraer**:
- Nombre, cargo, escuela/lab, áreas, email, perfiles oficiales, publicaciones recientes (si hay fuente).

**Debe inferir**:
- Actividad, accesibilidad, sponsor-likelihood, encaje con áreas del usuario.

**Salida**:
- Tabla scoreada de docentes “actores de admisión y fit”.

## D. Academic Activity Engine
**Debe calcular**:
- Frecuencia de publicaciones, coautorías, diversidad temática, volumen por universidad/programa/lab.

**Salida**:
- Indicadores de “pulso académico” y vitalidad.

## E. Fit & Match Engine
**Input**:
- Perfil estructurado del usuario (background, idiomas, prioridades, tolerancias, pesos).

**Output**:
- Sub-scores y score global por programa/docente/universidad.

## F. Audit & Drift Monitor
**Debe detectar**:
- Cambios en requisitos, duración, tuition, deadlines, faculty, enlaces y consistencia interfuente.

**Salida**:
- Changelog, alertas y score de confianza por dato.

## G. Decision Console
**Debe responder**:
- Top-N programas hoy.
- Qué subió/bajó desde último corte y por qué.
- Qué docentes son mejores contactos por objetivo.

---

## 5) Modelo de datos (núcleo)

## Entidades
- `University`
- `SchoolDepartment`
- `Program`
- `Faculty`
- `Publication`
- `UserProfile`
- `AuditRecord`
- `SourceDocument`
- `EvidenceSnippet`
- `ScoreBreakdown`
- `Snapshot`

## Principios de modelado
1. Separar `official_data`, `derived_data` e `inferred_data`.
2. Toda inferencia requiere evidencia + explicación + confianza.
3. Datos versionados por snapshot para comparabilidad temporal.

## Campos mínimos recomendados

### University
- `id`, `name`, `city`, `district`, `official_urls`, `school_count`, `program_count`, `faculty_count`,
  `publication_volume`, `industrial_signal_score`, `transparency_score`, `livability_score`, `updated_at`.

### Program
- `id`, `university_id`, `school_id`, `name`, `degree_type`, `language`, `duration`, `tuition`,
  `scholarship_info`, `requirements`, `deadlines`, `supervisor_required`, `interview_required`,
  `internship_signal`, `industriality_score`, `opacity_score`, `admission_fit_score`, `confidence_score`.

### Faculty
- `id`, `university_id`, `school_id`, `lab_id`, `name`, `title`, `research_areas`, `email`,
  `publication_count_recent`, `sponsor_likelihood`, `industry_link_score`, `accessibility_score`, `fit_score`.

### AuditRecord
- `id`, `entity_type`, `entity_id`, `field_name`, `old_value`, `new_value`, `source_url`,
  `change_type`, `confidence`, `detected_at`, `snapshot_id`.

---

## 6) Fuentes y jerarquía de confianza

## Prioridad 1 (autoridad)
- Sitios oficiales de admisión, graduate schools, escuelas/departamentos, páginas de programa.

## Prioridad 2 (enriquecimiento)
- Google Scholar, ORCID, dblp, ResearchGate, sitios de lab, noticias institucionales.

## Regla de resolución
1. Si hay conflicto en admisión: gana fuente oficial más reciente y específica.
2. Si persiste conflicto: marcar `inconsistency_flag = true` + revisión humana.
3. Toda resolución deja traza en `AuditRecord`.

---

## 7) Scoring framework (explicable)

## Sub-scores (0-100)
1. **Admission Fit**
2. **Strategic Fit**
3. **Lifestyle Fit**
4. **Contact Leverage**
5. **Information Confidence**

## Fórmula default
`overall_score = 0.30*strategic + 0.25*admission + 0.20*lifestyle + 0.15*contact + 0.10*confidence`

> Pesos editables por usuario (`UserProfile.weights`).

## Reglas de explicabilidad
- Guardar cada score con desglose por factores (`ScoreBreakdown`).
- Exponer evidencia puntual (snippets y URLs).
- Bloquear score final si `confidence_score` bajo umbral crítico configurable.

---

## 8) Pipeline de procesamiento

1. **Discovery**: semillas de universidades + crawling de hubs oficiales.
2. **Extraction**: HTML/PDF parsing, NLP ligero, normalización de campos.
3. **Structuring**: dedupe, linkage entre universidades/programas/docentes.
4. **Scoring**: cálculo explícito + inferencias con reglas.
5. **Auditing**: diff vs snapshot previo + alertas.
6. **Reporting**: dashboards, ranking y resumen narrativo.

---

## 9) Arquitectura técnica propuesta

## Backend
- Python
- Scrapy/Playwright para adquisición
- BeautifulSoup/lxml para parsing
- pdfplumber/PyMuPDF para PDFs
- FastAPI para API de lectura/escritura de resultados

## Datos
- PostgreSQL (core transaccional)
- opcional pgvector (similitud semántica)
- Redis opcional (colas/caché)

## Orquestación
- APScheduler/Celery Beat/cron
- Frecuencias sugeridas:
  - admisión: diario/semanal
  - faculty/labs: semanal
  - publicaciones: semanal/quincenal

## Frontend
- Streamlit (v1) o React minimal (v2)

## Observabilidad
- Logs por job + métricas de scrape success/error.
- Trazabilidad de cambios y confidence por dato.

---

## 10) Requisitos no funcionales

- **Trazabilidad**: 100% de inferencias con evidencia enlazada.
- **Confiabilidad**: retries, backoff y control de fallos por fuente.
- **Escalabilidad**: arquitectura por módulos y jobs idempotentes.
- **Mantenibilidad**: parser por conector/fuente con pruebas unitarias.
- **Internacionalización**: soporte chino/inglés + normalización UTF-8.

---

## 11) KPIs de producto

- Cobertura de programas detectados (% vs benchmark manual).
- Freshness: edad promedio de datos críticos (deadline/requisitos).
- Tasa de conflictos detectados y resueltos.
- Precisión percibida de ranking (feedback del usuario).
- Tiempo a shortlist accionable.

---

## 12) Roadmap

## Fase 0 — Diseño
- Modelo de datos, diccionario de señales, seed list inicial, pesos default.

## Fase 1 — MVP catálogo vivo
- University + Program trackers.
- Snapshots y diff básico.
- Dashboard simple de programas.

## Fase 2 — Faculty intelligence
- Scraper de docentes/labs.
- Contact leverage + sponsor-likelihood.

## Fase 3 — Activity analytics
- Agregación de publicaciones y vitalidad académica.

## Fase 4 — Inferencia implícita robusta
- Industriality, lifestyle, transparency, supervisor dependence.

## Fase 5 — Sistema vivo
- Alertas, recalculado continuo, reportes periódicos.

---

## 13) Riesgos y mitigaciones

1. **Inconsistencia web institucional**
   - Mitigar con source versioning + confidence + revisión humana.

2. **Dedupe de faculty/programas ambiguos**
   - Mitigar con llaves compuestas + heurísticas + validación manual parcial.

3. **Inferencias espurias**
   - Mitigar con reglas deterministas y evidencia auditable.

4. **Cambios de estructura HTML**
   - Mitigar con selectores resilientes y tests por fuente.

---

## 14) Criterios de aceptación (v1)

- [ ] Base con universidades seed y páginas oficiales registradas.
- [ ] Al menos un pipeline funcional de extracción de programas.
- [ ] Tabla de programas con campos críticos completos (idioma, duración, requisitos, deadline).
- [ ] Score inicial de `admission_fit`, `strategic_fit`, `confidence`.
- [ ] Changelog de cambios entre snapshots.
- [ ] Vista de ranking con explicación de score.

---

## 15) Principios de decisión

1. No hay score sin trazabilidad.
2. No hay inferencia sin evidencia.
3. No se mezcla dato oficial con inferido sin etiquetado explícito.
4. Mejor cobertura confiable que cobertura masiva opaca.

