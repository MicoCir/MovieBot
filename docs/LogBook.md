# Project LogBook

Registro resumido de la evolución del proyecto. Las entradas se ordenan mediante un identificador secuencial y no incluyen fechas ni horas.

## LB-0001 — Definición del alcance y plan del MVP

**Sprint:** S00 — Kick-off  
**Tarea:** Analizar el assessment y definir el plan de desarrollo

### Resumen

Se revisaron el assessment y el briefing para consolidar los requisitos, las restricciones y el alcance del prototipo. Se definió un chatbot con cuatro rutas: `trending`, `netflix`, `clarification` y `out_of_scope`, ejecutando como máximo un agente de recomendación por consulta.

Se acordó utilizar FastAPI, Server-Sent Events y una interfaz web mínima. El agente de tendencias se limitará al endpoint autorizado de TMDB y el agente Netflix trabajará sobre un snapshot histórico, sin garantizar disponibilidad actual.

El desarrollo se organizó en sprints, priorizando grounding, reproducibilidad, tests offline y evaluación antes de ajustar los agentes. También se definió una política de recorte para mantener viable el MVP dentro del plazo disponible.

---

## LB-0002 — Arquitectura y decisiones técnicas

**Sprint:** S00 — Kick-off  
**Tarea:** Definir la arquitectura de ejecución, búsqueda y trazabilidad

### Resumen

Se definió una arquitectura Docker Compose con cuatro servicios: `frontend`, `backend`, `netflix-db` y `trace-db`.

Para el catálogo Netflix se seleccionó Meilisearch Community Edition como motor de búsqueda léxica, semántica e híbrida. Esta decisión sustituyó una propuesta inicial basada en Qdrant, al considerarse Meilisearch más adecuado para búsquedas por título, errores tipográficos, filtros y similitud semántica dentro de un único servicio.

Las trazas de ejecución se almacenarán en PostgreSQL y permitirán reconstruir routing, llamadas a herramientas, retrieval, generación, streaming, errores y latencias. Los controles de licencia y uso de funcionalidades Community Edition se validarán mediante tests técnicos y controles de build, no mediante la evaluación funcional del agente.

---

## LB-0003 — Estrategia del Silver Dataset

**Sprint:** S01 — Silver Dataset  
**Tarea:** Definir la evaluación sintética del sistema

### Resumen

Se definió un Silver Dataset sintético y reproducible para evaluar el sistema por componentes, no únicamente por la respuesta final.

La evaluación se dividirá en tres suites: routing end-to-end, agente TMDB y agente Netflix RAG. Cada caso separará la ruta esperada, la herramienta esperada y la acción esperada, e incluirá fixtures deterministas para evitar depender de resultados externos variables.

Las etiquetas se derivarán de especificaciones estructuradas antes de generar las consultas en lenguaje natural. Se utilizarán splits `dev`, `test` y `holdout`, manteniendo juntas las variaciones de una misma semilla. Las métricas cubrirán routing, tool calls, retrieval, grounding, errores y estabilidad.

El Silver Dataset se utilizará para comparar versiones y detectar fallos, pero no se considerará un dataset Gold ni una validación de producción.

## LB-0004 — Spikes de viabilidad de fuentes de datos

**Sprint:** S00 — Kick-off  
**Tarea:** E0-T4 — Adquirir, inspeccionar y validar las tres fuentes de datos

### Resumen

Se implementaron tres spikes independientes para validar la viabilidad de las fuentes de datos del proyecto: TMDB API, dataset Netflix/Kaggle y Meilisearch Community Edition.

El spike TMDB valida credenciales, genera un snapshot sanitizado (sin secretos) y produce un inventario de campos del endpoint `trending/movie/{day|week}`. El spike Netflix perfila el dataset (tipos, nulos, duplicados), extrae una muestra mínima estratificada y calcula un fingerprint SHA-256. El spike Meilisearch levanta un contenedor efímero y verifica capacidades CE (full-text con typos, filtros facetados, búsqueda semántica e híbrida) sin activar features Enterprise.

Los tres resultados se consolidan en un Manifiesto de Viabilidad (`viability_manifest.json`) que registra procedencia, versión, checksum, limitaciones y decisiones por fuente. Un clasificador de artefactos diferencia lo apto para Git de lo excluido.

Se escribieron 180 tests (10 property-based con Hypothesis + unit tests con mocks/respx) cubriendo las 10 propiedades de correctness definidas en el diseño. Se verificó el aislamiento de imports: ningún spike referencia módulos de agente, routing ni recomendación.

---

## LB-0005 — Implementación del módulo Silver Dataset

**Sprint:** S01 — Silver Dataset  
**Tarea:** Implementar el pipeline completo de generación, validación, versionado y evaluación

### Resumen

Se implementó el módulo `silver_dataset/` completo con todos los componentes del pipeline definidos en la especificación.

**Modelos y contratos:** Se crearon los modelos Pydantic centrales (`SilverCase`, `LatentSpecification`, `GenerationMetadata`, `CoverageMatrix`) con enums normalizados en minúsculas. El `SilverCase` incluye un validador de consistencia route/tool/action que impide combinaciones inválidas antes de llegar a cualquier componente downstream.

**Generación:** Se implementó la expansión de la matriz de cobertura en especificaciones latentes, la derivación determinista de etiquetas (separada de la generación LLM), el generador de queries via Ollama con reintentos y backoff exponencial, el `CheckpointManager` para reanudación sin duplicados, y el motor de variaciones (typos, code-switching).

**I/O y acceso:** Se implementaron `read_jsonl`/`write_jsonl` con reporte de errores por línea, `PrettyPrinter`, y `SilverDatasetLoader` con filtros combinables, control de acceso al split holdout y validación de checksum.

**Fixtures:** Se crearon 16 ficheros JSON (8 TMDB + 8 Netflix) cubriendo resultados normales, vacíos, parciales, timeout, error de autenticación y payload inválido. Se implementó `FixtureRegistry` para gestión determinista.

**Validación:** Pipeline completo con `SchemaValidator`, `RuleValidator` (integridad de fixtures e IDs), `Critic` LLM (sin modificar etiquetas), `Deduplicator` (exacto, normalizado, semántico via SequenceMatcher) y lógica de asignación de `automatic_validation_status`.

**Versionado:** `compute_dataset_checksum` con SHA-256 sobre JSON canónico ordenado, `VersionRegistry`, y generación de `silver_dataset_card.md` con estadísticas de distribución.

**Evaluación:** Cuatro capas de métricas (routing, tool calls, retrieval, grounding), `BaselineRunner` con detección de errores de infraestructura, generación de scorecard y análisis de fallos con propuesta de nuevas semillas para hard-cases.

**CLI:** Tres comandos (`generate`, `validate`, `evaluate`) con checkpoint idempotente, reporte de progreso y resumen al finalizar.

**Tests:** 22 property-based tests con Hypothesis (≥100 ejemplos cada uno) cubriendo las 22 propiedades de correctness del design document, más ~175 unit tests adicionales. Total: ~197 tests en el módulo.

---
