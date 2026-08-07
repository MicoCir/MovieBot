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
