# Primer borrador del plan de desarrollo

## 1. Control del documento

| Campo | Valor |
| --- | --- |
| Proyecto | Agentic Movie Recommendation Chatbot |
| Estado | Borrador integrado para validación |
| Versión | 0.4 |
| Fecha | 6 de agosto de 2026 |
| Horizonte | Una semana conforme al *take-home assessment*, con control explícito de alcance |
| Método | Agile adaptado a un proyecto individual y de plazo corto |
| Fuentes | `AI_eng - Take_Home_Assessment.pdf`, `primer_briefing.md` y `primer_borrador_silver_dataset_generation.md` |

Este documento transforma el enunciado y el briefing en un backlog ejecutable. Las estimaciones son orientativas y se expresan en horas de trabajo efectivo. En un proyecto individual, la revisión de producto y la revisión técnica se materializan mediante criterios de aceptación, pruebas automatizadas y evidencias reproducibles.

## 2. Lectura consolidada del encargo

### 2.1 Objetivo de producto

Construir un prototipo de chatbot de recomendación audiovisual que:

1. Clasifique cada consulta y seleccione un único agente especializado.
2. Consulte exclusivamente el endpoint autorizado de películas en tendencia de TMDB cuando la intención sea de actualidad.
3. Realice RAG sobre el dataset estático de títulos de Netflix cuando la intención sea temática, de género o de catálogo.
4. Genere de una a tres recomendaciones explicables y limitadas a los datos recuperados.
5. Entregue la respuesta progresivamente mediante streaming.
6. Oculte fallos técnicos al usuario y conserve información suficiente para diagnosticarlos.
7. Sea instalable, comprobable y reproducible en un entorno limpio.
8. Registre una traza estructurada de cada ejecución para monitorización, depuración y evaluación posterior.
9. Se ejecute como una aplicación de cuatro servicios aislados y orquestados con Docker Compose.

### 2.2 Decisiones de interpretación

| Tema | Decisión adoptada | Justificación |
| --- | --- | --- |
| Uso de los agentes | Cada consulta activa como máximo un agente de recomendación; `clarification` y `out_of_scope` no invocan agentes externos. | El texto original contiene una frase ambigua, pero exige routing al agente apropiado; el briefing también fija esta interpretación. |
| Interfaz | FastAPI, endpoint REST con Server-Sent Events y una interfaz web mínima. | El enunciado deja la interfaz abierta; esta opción demuestra streaming con poco coste de implementación. |
| “Reciente” o “mejor” | Tendencia no equivale a estreno. La selección empleará una heurística documentada sobre los resultados del endpoint permitido. | Evita atribuir a TMDB información que el endpoint no garantiza. |
| Netflix | El dataset es un snapshot histórico; no se afirmará disponibilidad actual ni regional. | Limitación intrínseca de la fuente. |
| Modelo LLM | Cliente OpenAI configurable mediante `OPENAI_API_KEY`, `OPENAI_BASE_URL` y nombre de modelo. | Permite usar el API Gateway facilitado sin acoplar el dominio al proveedor. |
| Calidad | Los unit tests, aunque solo estén recomendados en el enunciado, se consideran obligatorios para componentes críticos. | El foco declarado es código mantenible y probado. |
| Idioma | La respuesta seguirá el idioma detectado en la consulta; el MVP deberá cubrir inglés y español. | Amplía robustez sin alterar el dominio funcional. |
| Propósito del Silver Dataset | No es un corpus de entrenamiento ni una verdad experta: es una suite sintética versionada para evaluar decisiones intermedias y respuesta final. | Permite medir routing, tool calls, retrieval, grounding, errores y estabilidad sin confundir Silver con Gold. |
| Evaluación | Se separan `expected_route`, `expected_tool` y `expected_action`, y se usan fixtures deterministas de herramientas. | Una respuesta aparentemente correcta no debe ocultar una ejecución incorrecta. |
| Trazas | Cada ejecución genera una traza jerárquica, correlacionada y persistente, compatible conceptualmente con OpenTelemetry. | La evaluación necesita reconstruir decisiones, latencias, uso de herramientas, tokens, errores y evidencias. |
| Base Netflix | Meilisearch Community Edition autocontenido en Docker almacenará documentos, vectores e índices léxicos del snapshot Netflix. | Proporciona hybrid search, filtros y tolerancia a typos en un servicio local reproducible. |
| Licencia de búsqueda | Solo se utilizará Meilisearch Community Edition bajo MIT; toda función Enterprise/BUSL queda prohibida. | Mantiene el stack plenamente self-hosted y open source sin dependencia comercial. |
| Base de trazas | PostgreSQL separado almacenará runs, spans/eventos y resultados de evaluación; los atributos variables usarán `JSONB`. | Las trazas requieren consultas analíticas, relaciones estables, versionado e indexación flexible. |
| Contenedores | Se crearán cuatro servicios runtime: `frontend`, `backend`, `netflix-db` y `trace-db`, coordinados por Compose. | Mantiene responsabilidades y persistencias separadas sin introducir orquestación distribuida innecesaria. |

### 2.3 Alcance comprometido del MVP

- Router con salidas estructuradas: `trending`, `netflix`, `clarification` y `out_of_scope`.
- Trending Movie Agent limitado al endpoint `trending/movie/{time_window}` de TMDB.
- Netflix RAG Agent con ingesta, embeddings configurables, Meilisearch CE local, filtros y recuperación híbrida léxica/vectorial.
- Respuestas grounded, con procedencia y limitaciones visibles.
- API FastAPI, streaming SSE e interfaz web mínima.
- Configuración por entorno, errores seguros, logs estructurados y métricas básicas de latencia.
- Dataset sintético de evaluación o *silver dataset*, generado mediante GPT por API.
- Tres suites silver: routing/end-to-end, agente TMDB y agente Netflix RAG, con fixtures deterministas.
- Runner de evaluación que asocia cada ejecución con caso, suite, versión, repetición y métricas.
- Trazas persistentes de routing, tool calls, retrieval, generación, streaming, errores, tokens, coste y latencias.
- API de consulta/exportación de trazas para monitorización y análisis de fallos.
- Cuatro imágenes/servicios Docker y un `compose.yaml` que levanta el sistema completo.
- Tests unitarios, tests de integración sin red real y evaluación offline.
- README, `.env.example`, informe breve y diagrama de arquitectura.
- Evidencia temprana y reproducible de viabilidad de las fuentes: snapshot sanitizado de TMDB, fingerprint y perfil del dataset Netflix, y smoke test de Meilisearch CE.

### 2.4 Fuera de alcance

- Autenticación, perfiles, historial persistente o personalización por comportamiento.
- Collaborative filtering, fine-tuning o entrenamiento de modelos.
- Consulta de servicios distintos de TMDB y del dataset indicado.
- Endpoints adicionales de TMDB, incluso si mejorarían el enriquecimiento de resultados.
- Disponibilidad regional, precios, reproducción o compra.
- Despliegue productivo, infraestructura distribuida y escalado horizontal.
- Interfaz visual avanzada.
- Plataforma completa de observabilidad, collector o dashboard externo; el MVP almacenará y expondrá las trazas desde el backend.
- Revisión humana exhaustiva del Silver Dataset; esa actividad pertenece a la futura evolución a Gold.
- Sharding, replication, network/remotes, analytics, personalización o cualquier funcionalidad Enterprise/Cloud de Meilisearch.

### 2.5 Evaluación del planteamiento multi-servicio

El camino es **arquitectónicamente correcto**, con dos condiciones:

1. Debe hablarse de un servicio o contenedor por responsabilidad, no de “un Docker”. Docker Compose es la unidad de ejecución del sistema completo.
2. El alcance añadido debe reconocerse: tres suites Silver, trazas persistentes, cuatro contenedores y los spikes tempranos de fuentes elevan la estimación de 40 a unas 52 horas.

La separación de bases está justificada porque sus workloads son distintos: Meilisearch CE optimiza full-text, búsqueda vectorial/híbrida, filtros y typo tolerance; PostgreSQL ofrece relaciones, consultas temporales y `JSONB` indexable para trazas. Compartir una única base reduciría contenedores, pero mezclaría responsabilidades y requeriría compromisos de almacenamiento. Añadir ahora un Collector, Jaeger, Grafana o plataforma LLM-observability completa sería sobreingeniería para el take-home; el contrato compatible con OpenTelemetry permite incorporarlos después.

La decisión de licencia es un constraint arquitectónico: se fijará una imagen/version Community Edition y se verificará que el sistema no configure ni invoque sharding, replication, `useNetwork`, personalización u otras capacidades Enterprise. Hybrid search, full-text, AI-powered search y filtros requeridos pertenecen al alcance Community/MIT.

Esta restricción **no forma parte del Silver Dataset ni de las métricas del agente**. Se verificará mediante unit tests sobre builders/schemas de requests, contract tests del adaptador y controles de imagen/SBOM en CI.

No se necesita una sesión abierta de brainstorming antes de continuar. Sí se debe registrar esta decisión como ADR y confirmar al cerrar Sprint 0 el presupuesto real de horas/API. El Sprint 0 debe cerrar también los riesgos de acceso y forma de los datos mediante spikes acotados, no mediante la construcción anticipada de los agentes. Si el límite es estricto, se reduce volumen/analítica avanzada, no grounding, trazas, reproducibilidad ni validación temprana de las fuentes.

## 3. Principios de ejecución

1. **Evaluation first:** el contrato de evaluación se fija antes de implementar los agentes.
2. **Trace first:** cada operación evaluable define sus eventos y atributos antes de implementarse.
1. **Validate sources early:** se comprueban cuanto antes el acceso, contrato, forma y restricciones de TMDB, Kaggle y Meilisearch, sin adelantar la implementación completa.
3. **Grounding estricto:** ningún título puede aparecer si no está en la respuesta de TMDB o en los documentos recuperados.
4. **Núcleo determinista:** filtros, ranking, validaciones y estados se implementan como lógica comprobable; el LLM se reserva para clasificación asistida y redacción.
5. **Dependencias invertidas:** clientes LLM, embeddings, TMDB, caché, vector store y trace store se consumen mediante interfaces sustituibles.
6. **Sin red en unit tests:** toda dependencia externa utiliza fakes, stubs o transporte HTTP simulado.
7. **Persistencia separada:** datos Netflix y trazas tienen ciclos de vida, esquemas y volúmenes distintos.
8. **Contenedor por servicio:** cada componente runtime tiene imagen, healthcheck, configuración y responsabilidad propia; Compose gestiona red y dependencias.
9. **Entrega vertical:** cada sprint termina con un incremento verificable y no solo con componentes aislados.
10. **Alcance congelado:** primero se completa el MVP; las mejoras ideales se mantienen como backlog opcional.

## 4. Modelo Agile propuesto

### 4.1 Fases y sprints

| Fase | Sprint | Duración objetivo | Objetivo | Epics principales | Gate de salida |
| --- | --- | ---: | --- | --- | --- |
| Descubrimiento | Sprint 0 — Kick-off | 4 h | Consolidar información, alcance, límites y primer plan. | E0 | Backlog inicial revisable y decisiones explícitas. |
| Medición | Sprint 1 — Silver Dataset | 9 h | Definir y producir las tres suites sintéticas y el contrato de su runner. | E1 | `silver_v1` válido, versionado, con fixtures, splits bloqueados y listo para baseline. |
| Fundaciones | Sprint 2 — Core y Routing | 7 h | Crear la base técnica, contratos de trazas y cerrar routing. | E2, E3, E7 | Routing evaluable y trazas persistibles. |
| Agente online | Sprint 3 — Trending | 5 h | Entregar el agente TMDB grounded y resiliente. | E4 | Flujo trending completo con TMDB simulado. |
| Agente RAG | Sprint 4 — Netflix | 8 h | Ingerir, configurar Meilisearch CE, ejecutar hybrid search y responder desde Netflix. | E5, E8 | Flujo RAG híbrido completo contra el contenedor y métricas comparativas calculables. |
| Integración | Sprint 5 — UX, Trazas y Docker | 10 h | Integrar agentes, SSE, UI, persistencia de trazas y los cuatro servicios. | E6, E7, E8 | Demo end-to-end con trazas consultables mediante Compose. |
| Cierre | Sprint 6 — Evaluación y Entrega | 7 h | Validar, endurecer, documentar y empaquetar. | E9 | Todos los criterios del MVP trazados y evidenciados. |

## 5. Backlog detallado por epic

## Epic E0 — Descubrimiento, alcance y planificación

**Sprint:** 0 — Kick-off  
**Objetivo:** convertir las fuentes disponibles en una definición compartida y ejecutable del MVP, cerrando temprano los principales riesgos de acceso y forma de los datos.  
**Valor:** reduce ambigüedad, previene sobreingeniería y crea trazabilidad desde el enunciado hasta la entrega.

### E0-T1 — Analizar fuentes y extraer requisitos

**Estimación:** 1,5 h  
**Alcance:** leer el assessment y el briefing; clasificar requisitos funcionales, no funcionales, restricciones, entregables, riesgos y supuestos; detectar contradicciones o vacíos. No incluye diseño técnico detallado ni implementación.

**Criterios de aprobación:**

- Las dos fuentes están identificadas y resumidas.
- Se recogen los dos agentes, routing, streaming, gestión de errores, reproducibilidad, testing, evaluación y documentación.
- Se destaca que TMDB queda limitado a un único endpoint y que Netflix es un snapshot.
- Toda ambigüedad relevante dispone de una decisión o queda registrada como pregunta abierta.

**Pruebas unitarias y verificaciones:**

- No aplica unit test de código por tratarse de análisis documental.
- Verificación mediante checklist de trazabilidad: cada requisito explícito del PDF aparece en al menos una sección o tarea del plan.
- Revisión de consistencia entre términos (`trending`, `netflix`, `clarification`, `out_of_scope`) y sus definiciones.

### E0-T2 — Fijar alcance, límites y criterios del MVP

**Estimación:** 1 h  
**Alcance:** declarar decisiones de interpretación, alcance comprometido, fuera de alcance, métricas y restricciones temporales. No incluye comprometer funcionalidades ideales que no sean necesarias para la evaluación.

**Criterios de aprobación:**

- Existe una lista explícita de inclusiones y exclusiones.
- Las decisiones sobre interfaz, selección de agente y uso de fuentes están justificadas.
- Los criterios del MVP son medibles y compatibles con el plazo de una semana.
- Se diferencia claramente requisito obligatorio, decisión de diseño y mejora opcional.

**Pruebas unitarias y verificaciones:**

- No aplica unit test de código.
- Verificación de contradicciones: ninguna tarea puede requerir endpoints extra de TMDB ni disponibilidad actual de Netflix.
- Revisión de factibilidad: la suma de estimaciones no supera la capacidad de 40 horas sin consumir backlog opcional.

### E0-T3 — Crear el primer borrador del plan de desarrollo

**Estimación:** 1,5 h  
**Alcance:** definir fases, sprints, epics, tareas, dependencias, aceptación y estrategia de tests. El entregable es este documento y no incluye todavía código de producto.

**Criterios de aprobación:**

- Todos los sprints tienen objetivo, backlog y gate de salida.
- Cada epic contiene tareas con alcance, criterios de aprobación y pruebas previstas.
- Sprint 1 queda reservado a la definición y generación del silver dataset, usando evidencias obtenidas en los spikes de Sprint 0.
- El plan incluye riesgos, prioridades, métricas y trazabilidad final.

**Pruebas unitarias y verificaciones:**

- No aplica unit test de código.
- Validación estructural del Markdown: encabezados, tablas, enlaces y listas se renderizan correctamente.
- Checklist automática o manual que confirme que cada identificador de tarea es único y pertenece a un sprint.


### E0-T4 — Adquirir e inspeccionar fuentes y ejecutar spikes de viabilidad

**Estimación:** 2 h  
**Alcance:** reducir antes del diseño detallado los riesgos técnicos que condicionan el Silver Dataset y los agentes. La tarea incluye tres comprobaciones acotadas:

1. **TMDB:** validar credenciales y acceso al endpoint autorizado `trending/movie/{day|week}`, inspeccionar el payload real y guardar un snapshot sanitizado junto con un inventario de campos. No incluye todavía cliente de producción, caché, ranking ni fallbacks.
2. **Netflix/Kaggle:** obtener una copia local del dataset o, cuando la autenticación impida automatizarla, dejar un procedimiento reproducible de adquisición; comprobar licencia y condiciones de redistribución, columnas, tamaño, nulos, duplicados y valores representativos; calcular checksum/fingerprint y conservar una muestra mínima para fixtures. No incluye todavía la normalización definitiva ni la ingesta completa.
3. **Meilisearch CE:** levantar una instancia desechable de la versión candidata, verificar edición/licencia y ejecutar un smoke test sobre una muestra mínima para confirmar full-text, filtros y los modos léxico, semántico e híbrido requeridos. No incluye todavía el índice definitivo, embeddings de todo el corpus ni operación persistente.

Los artefactos se almacenarán fuera de los datasets finales mediante un manifiesto de viabilidad que registre procedencia, versión, checksum, campos observados, limitaciones y decisiones derivadas.

**Criterios de aprobación:**

- Se confirma que TMDB responde mediante el único endpoint permitido o se documenta un bloqueo reproducible con fixture contractual equivalente.
- Existe un snapshot TMDB sanitizado y sin credenciales, apto para diseñar fixtures y modelos.
- Existe una copia local verificable del dataset Netflix o un procedimiento probado de adquisición, junto con perfil de columnas, calidad básica y fingerprint.
- Se documentan las condiciones conocidas de uso y redistribución antes de decidir qué datos o derivados incluir en la entrega.
- Meilisearch CE arranca con versión fijada y el smoke test demuestra las capacidades mínimas requeridas sin parámetros Enterprise.
- Los spikes no introducen código de agente ni acoplamiento prematuro; sus resultados alimentan `E1-T2`, `E1-T4`, `E4`, `E5` y `E8`.

**Pruebas unitarias y verificaciones:**

- Verificación de que la URL TMDB utilizada pertenece exclusivamente a `trending/movie/day|week`.
- Escaneo del snapshot y logs para confirmar ausencia de API keys, headers de autorización y datos sensibles.
- Validación del checksum, schema observado y estadísticas básicas del CSV sobre una muestra reproducible.
- Smoke test de contenedor que registra tag/digest, healthcheck y resultado de búsqueda/filtro/hybrid sobre el corpus mínimo.
- Checklist de licencia y allow-list que rechaza `useNetwork`, network/remotes, sharding, replication, personalización u otras capacidades Enterprise.
- Los artefactos grandes o sujetos a restricciones de redistribución quedan fuera de Git; el repositorio conserva manifiestos, scripts y muestras permitidas.

## Epic E1 — Definición y generación del Silver Dataset

**Sprint:** 1 — Silver Dataset  
**Objetivo:** crear mediante GPT y API una suite de evaluación sintética, reproducible y suficientemente diversa para medir decisiones intermedias y respuesta final.  
**Valor:** evita desarrollar a ciegas, impide que una respuesta plausible oculte una ejecución incorrecta y crea una base versionada para regresión.  
**Propósito y límites:** Silver es un artefacto de evaluación, no de entrenamiento. Sus etiquetas proceden de especificaciones estructuradas, reglas y validación automática, pero no de revisión exhaustiva por expertos. Por tanto, permite comparar versiones y descubrir fallos, pero no sustituye un futuro Gold Dataset ni demuestra por sí solo rendimiento de producción.

### E1-T1 — Definir contrato, taxonomía y métricas del dataset

**Estimación:** 1,5 h  
**Alcance:** definir esquema, taxonomía, distribución, idiomas, dificultad y reglas de etiquetado para tres suites: `e2e_routing_silver`, `tmdb_agent_silver` y `netflix_agent_silver`. La meta completa será de 250–350 casos: 120–160 E2E, 60–90 TMDB y 80–110 Netflix. Se buscará diversidad en inglés, español, code-switching, errores, negaciones, multi-intent y multivuelta.

Se normalizarán en minúsculas los enums de aplicación y evaluación:

- `expected_route`: `trending`, `netflix`, `clarification`, `out_of_scope`.
- `expected_tool`: `tmdb_trending`, `netflix_search`, `none`.
- `expected_action`: `call_tool`, `ask_clarifying_question`, `return_out_of_scope`, `answer_from_tool_output`, `return_no_results`, `return_controlled_error`.

Esta separación es obligatoria: una ruta funcional no se modelará como si fuera una herramienta y una tool correcta no bastará si la acción posterior es incorrecta.

El esquema mínimo será:

| Campo | Propósito |
| --- | --- |
| `case_id` | Identificador estable y único. |
| `dataset_version` / `suite` / `split` | Versión, suite y partición del caso. |
| `scenario_family` / `scenario_type` | Familia funcional y variante concreta. |
| `query` | Consulta sintética del usuario. |
| `conversation_context` | Contexto multivuelta requerido, si aplica. |
| `language` / `response_language` | Idioma de consulta y respuesta esperada. |
| `expected_route` | Clase de routing esperada. |
| `expected_tool` / `expected_action` | Herramienta y comportamiento esperados. |
| `expected_tool_request` | Endpoint, ventana, query semántica y filtros esperados. |
| `user_constraints` | Tipo, género, tema, año, ventana temporal u otras restricciones. |
| `tool_output_fixture_id` | Fixture determinista que sustituye la dependencia variable. |
| `expected_selected_items` | IDs cuya selección se espera. |
| `acceptable_selected_items` | Alternativas correctas para no imponer un único título. |
| `forbidden_selected_items` | Distractores que nunca deben recomendarse. |
| `required_facts` / `optional_facts` | Hechos exigibles y permitidos en la respuesta. |
| `forbidden_claims` | Afirmaciones no soportadas que deben detectarse. |
| `expected_response_type` | Recomendación, aclaración, fuera de alcance, sin resultados o error. |
| `difficulty` | `easy`, `medium` o `hard`. |
| `tags` | Multietiqueta para análisis por segmento. |
| `seed_scenario_id` | Escenario latente del que derivan las variaciones. |
| `generation_metadata` | Método, modelo, prompt, timestamp, lote y tipo de variación. |
| `automatic_validation_status` | `passed`, `failed` o `warning`. |
| `review_status` | `not_human_reviewed` para Silver. |

Los casos se dividirán por familia/semilla, no por consulta individual: `dev` 60 %, `test` 25 % y `holdout` 15 %. Todas las mutaciones de una misma semilla permanecerán en el mismo split para evitar fuga por paráfrasis. `holdout` quedará bloqueado y no se usará para ajustar prompts, reglas o thresholds.

**Criterios de aprobación:**

- El esquema está expresado como modelo Pydantic y JSON Schema exportable.
- Cada suite y clase tiene definición positiva, fronteras, casos negativos y familias de escenario.
- Los casos Netflix están ligados a filas reales o fixtures controlados y no a IDs inventados por GPT.
- Los casos TMDB usan fixtures compatibles con el endpoint permitido y no dependen de tendencias vivas.
- Las expectativas admiten varios elementos correctos y no comparan la respuesta con un único texto exacto.
- Están definidas métricas de routing, tool request, retrieval, selección, grounding, respuesta, operación y estabilidad.

**Pruebas unitarias:**

- Acepta un registro mínimo válido de cada suite y cada ruta.
- Rechaza combinaciones incompatibles de route/tool/action, enums desconocidos y rangos de recomendaciones inválidos.
- Rechaza IDs duplicados, consultas vacías, fixtures inexistentes y selecciones ausentes del fixture.
- Comprueba que `clarification` y `out_of_scope` tengan `expected_tool=none`.
- Comprueba serialización y deserialización sin pérdida y exportación de JSON Schema.

### E1-T2 — Construir matriz de cobertura y especificaciones latentes

**Estimación:** 1 h  
**Alcance:** definir primero una matriz de cobertura por suite, ruta, familia, idioma, dificultad y variación. Cada caso nacerá de una especificación latente estructurada; las etiquetas se derivarán de ella antes de generar la consulta natural. No se aceptará una generación genérica de preguntas y etiquetado posterior por inferencia.
**Alcance:** definir primero una matriz de cobertura por suite, ruta, familia, idioma, dificultad y variación. Cada caso nacerá de una especificación latente estructurada; las etiquetas se derivarán de ella antes de generar la consulta natural. La matriz y los schemas de tool output se contrastarán con el snapshot TMDB, el perfil del dataset Netflix y el smoke test de Meilisearch producidos en `E0-T4`. No se aceptará una generación genérica de preguntas y etiquetado posterior por inferencia.

**Criterios de aprobación:**

- La matriz cubre routing, tool request, procesamiento de output, no-results y errores controlados.
- Incluye escenarios directos, ambiguos, multi-intent, multivuelta, negativos, distractores y prompt injection.
- Las etiquetas funcionales se derivan mediante código determinista desde la especificación latente.
- Los casos Netflix parten de campos o documentos reales; los TMDB parten de un contrato de fixture controlado.
- Cada variación conserva `seed_scenario_id` y declara si puede cambiar la ruta esperada.

**Pruebas unitarias:**

- Valida que cada celda de cobertura produzca el número configurado de semillas.
- Deriva route/tool/action y filtros esperados para ejemplos conocidos.
- Mantiene todas las variaciones de una semilla enlazadas al mismo escenario.
- Rechaza especificaciones contradictorias o imposibles antes de llamar al LLM.

### E1-T3 — Diseñar prompts y generar consultas mediante GPT API

**Estimación:** 1,5 h  
**Alcance:** diseñar prompts versionados y un comando idempotente que use `OPENAI_API_KEY`, `OPENAI_BASE_URL` y modelo configurable para convertir especificaciones latentes en consultas naturales y variaciones. El comando validará salida estructurada, reintentará de forma acotada y guardará parciales sin exponer secretos. GPT no decidirá las etiquetas de verdad.

**Criterios de aprobación:**

- Los prompts exigen JSON conforme al schema y prohíben texto adicional o etiquetas internas en la consulta.
- Modelo, temperatura, lote, versión de prompt y estrategia de reintento son configurables.
- La generación cubre paráfrasis, typos, coloquialidad, traducción, code-switching, negación y distractores.
- El comando puede reanudarse sin duplicar casos y registra modelo, prompt, lote, tokens y coste si están disponibles.
- Cada ejecución y lote genera un `generation_run_id` y un manifiesto de traza JSONL compatible con el trace schema; al estar disponible `trace-db`, estos registros se importan sin regenerar el dataset.
- La ausencia de API key o salida inválida produce error controlado y artefacto de rechazo.

**Pruebas unitarias:**

- Snapshot test de prompts y validación de configuración antes de cualquier llamada.
- Fake OpenAI procesa salida válida, JSON inválido, schema inválido, timeout, rate limit y error no reintentable.
- Reanudación no solicita semillas completadas ni duplica filas.
- Confirma que query generada conserva restricciones y no expone nombres de etiquetas.
- Sanitización garantiza que claves y headers no aparecen en logs ni artefactos.
- Export/import del manifiesto conserva run, lotes, tokens, retries, accepted/rejected y versiones.

### E1-T4 — Crear fixtures y derivar expectativas de procesamiento

**Estimación:** 1,25 h  
**Alcance:** construir fixtures deterministas de TMDB y Netflix. Los fixtures TMDB respetarán el esquema del único endpoint permitido e incluirán resultados válidos, distractores, vacíos y errores. Los fixtures Netflix usarán filas reales, relevancia graduada, metadatos y distractores. A partir del fixture se derivarán elementos esperados, aceptables, prohibidos, hechos requeridos y claims prohibidos.
**Alcance:** construir fixtures deterministas de TMDB y Netflix a partir de las evidencias obtenidas en Sprint 0. Los fixtures TMDB respetarán el contrato observado del único endpoint permitido y utilizarán snapshots sanitizados o plantillas compatibles. Los fixtures Netflix usarán filas de la copia local verificada del dataset, relevancia graduada, metadatos y distractores. A partir del fixture se derivarán elementos esperados, aceptables, prohibidos, hechos requeridos y claims prohibidos.

**Criterios de aprobación:**

- Ninguna evaluación offline depende de TMDB vivo ni de un ranking vectorial variable.
- Todo ID esperado, aceptable o prohibido existe en su fixture.
- Varios títulos razonables se representan como alternativas, no como falso top-1 único.
- Los fixtures cubren respuesta vacía, baja relevancia, datos incompletos, contradicciones y error técnico.
- La generación conserva fingerprint y procedencia del snapshot o plantilla.
- Los fixtures quedan trazados hasta los artefactos de viabilidad generados en `E0-T4`.

**Pruebas unitarias:**

- Valida fixtures TMDB compatibles, vacíos, incompletos y erróneos.
- Verifica que fixtures Netflix referencien IDs reales y etiquetas de relevancia válidas.
- Rechaza expectativas cuyos IDs no aparezcan en el fixture.
- Deriva correctamente hechos requeridos y claims prohibidos para escenarios conocidos.
- Un mismo input y semilla producen fixtures y checksums estables.

### E1-T5 — Validar, criticar, deduplicar y versionar `silver_v1`

**Estimación:** 1,5 h  
**Alcance:** ejecutar JSON/schema validation, reglas de consistencia, un modelo crítico independiente, deduplicación exacta/normalizada/semántica y split agrupado por familia. El crítico emitirá estado, confianza y warnings, pero no modificará etiquetas directamente. Versionar dataset, prompts, configuración, fixtures y dataset card.

**Criterios de aprobación:**

- La meta completa contiene 250–350 casos y las tres suites; el corte P0 mínimo queda definido en la sección 11.
- Todos los casos pasan schema y reglas críticas; warnings permanecen identificables.
- No existen duplicados significativos ni familias compartidas entre splits.
- Modelo crítico, prompt, confidence y warnings quedan registrados por caso.
- Todos los registros Silver declaran `review_status=not_human_reviewed`.
- Dataset, fixtures, configuración y prompts tienen versión/checksum; `holdout` queda congelado.

**Pruebas unitarias:**

- El validador detecta combinaciones route/tool/action inválidas, fixture ausente, IDs inexistentes y contradicciones.
- El crítico fake clasifica `pass`, `warning` y `failed` sin mutar el caso.
- El cálculo de distribución cubre suite, ruta, tool, action, idioma, dificultad y familia.
- El split por grupos es reproducible, no pierde registros y no separa mutaciones de una semilla.
- Detecta duplicados exactos, normalizados, semánticos y fuga entre splits.
- El checksum cambia al alterar un caso y se mantiene para contenido idéntico.

### E1-T6 — Implementar loader, validadores y métricas

**Estimación:** 1 h  
**Alcance:** crear una API para cargar por versión, suite, split, ruta y tags; ejecutar validadores deterministas y calcular métricas de routing, tool calls, retrieval, selección, grounding, respuesta, operación y estabilidad. Las comprobaciones semánticas se ejecutarán como capa separada y no sustituirán checks deterministas.

**Criterios de aprobación:**

- El loader valida versión y checksum antes de devolver casos.
- Los filtros son combinables y conservan un orden estable.
- El acceso a `holdout` exige un modo explícito de evaluación final.
- Se calculan, como mínimo, route accuracy/Macro F1, unnecessary tool call rate, tool request validity, Recall/Precision/nDCG, grounded title rate, unsupported claim rate, task success y controlled failure rate.
- Las métricas operativas incluyen latencias, TTFT, llamadas, tokens, coste, errores y reintentos.
- Las fixtures no realizan llamadas de red ni requieren API keys.

**Pruebas unitarias:**

- Carga las tres suites y filtra por cada dimensión y combinaciones.
- Rechaza versión desconocida, checksum incorrecto y registros corruptos.
- Bloquea `holdout` en modo desarrollo y lo permite en modo final.
- Cada métrica se verifica contra una fixture con resultado calculado manualmente.
- Devuelve una lista vacía, no una excepción inesperada, cuando un filtro válido no tiene casos.

### E1-T7 — Ejecutar baseline y preparar hard-case mining

**Sprint:** 6  
**Estimación:** 1,25 h  
**Alcance:** ejecutar una versión baseline contra `dev`, persistir una traza por intento y producir scorecard, distribución y análisis de fallos. Los casos repetidos usarán `attempt_number` para calcular pass@1, repeated pass rate, decision stability y recommendation stability. Los fallos podrán originar nuevas semillas, siempre en una nueva versión del dataset.

**Criterios de aprobación:**

- Cada caso ejecutado tiene `run_id`, `case_id`, versión de dataset, versión de código/configuración y número de intento.
- El scorecard separa routing, tool selection/request, retrieval/selección, grounding y respuesta/errores.
- Los fallos se agrupan por causa y tags, sin cambiar etiquetas para favorecer al baseline.
- Hard-case mining genera propuestas versionadas y no contamina `test` ni `holdout`.
- Se produce `silver_dataset_card.md`, `baseline_results.md` y `failure_analysis.md`.

**Pruebas unitarias:**

- Runner fake asocia correctamente caso, intento y trace ID.
- Repeated pass rate y estabilidad se calculan sobre ejecuciones repetidas conocidas.
- Una ejecución incompleta queda como error de infraestructura, no como fallo funcional silencioso.
- El minero agrupa fallos equivalentes y conserva la familia/split de la semilla.
- Exportación de resultados no contiene claves, prompts sensibles ni payloads no autorizados.

## Epic E2 — Fundaciones técnicas y contratos de dominio

**Sprint:** 2 — Core y Routing  
**Objetivo:** establecer una base modular, reproducible y fácil de probar antes de integrar lógica externa.

### E2-T1 — Crear estructura, dependencias y configuración

**Estimación:** 1,5 h  
**Alcance:** crear paquete Python 3.11+, configuración Pydantic, gestión de dependencias, `.env.example`, comandos principales y estructura por responsabilidades. No se añadirán frameworks de agentes si una composición explícita resulta suficiente.

**Criterios de aprobación:**

- Una instalación limpia permite importar y arrancar la aplicación.
- Están declaradas todas las variables del briefing y las nuevas `MEILISEARCH_URL`, `MEILISEARCH_API_KEY`, `MEILI_MASTER_KEY`, `MEILISEARCH_INDEX_UID`, `MEILISEARCH_EMBEDDER`, `MEILISEARCH_SEMANTIC_RATIO`, `TRACE_DATABASE_URL`, `TRACE_CAPTURE_MODE`, `TRACE_RETENTION_DAYS` y `APP_VERSION`, con defaults solo cuando sea seguro.
- Los secretos nunca tienen defaults reales ni se incluyen en el repositorio.
- Configuración inválida produce mensajes accionables.
- Existen comandos documentables para servidor, indexación, tests y evaluación.

**Pruebas unitarias:**

- Carga configuración mínima válida desde entorno simulado.
- Rechaza ausencia de variables obligatorias solo cuando la funcionalidad correspondiente las necesita.
- Valida URLs, timeouts, rutas y nombres de modelos.
- Confirma que la representación de settings enmascara secretos.

### E2-T2 — Definir modelos, puertos y errores de dominio

**Estimación:** 1,25 h  
**Alcance:** definir modelos Pydantic para consulta, decisión de routing, restricciones, candidato, recomendación, eventos SSE, trazas y errores; además de protocolos para LLM, embedder, TMDB, vector store, trace store y caché.

**Criterios de aprobación:**

- Las interfaces públicas están tipadas y no dependen de implementaciones concretas.
- Los modelos impiden confianza fuera de `[0,1]`, recomendaciones vacías inválidas y fuentes desconocidas.
- Los errores técnicos se traducen a un conjunto cerrado de errores de aplicación.
- Los agentes y el orquestador pueden probarse inyectando fakes de Meilisearch y PostgreSQL.

**Pruebas unitarias:**

- Valida límites, enums y campos obligatorios de cada modelo.
- Comprueba conversión de cada error técnico a error de aplicación.
- Comprueba serialización de eventos SSE sin datos internos.
- Usa implementaciones fake para demostrar sustitución de cada puerto, incluido trace store con éxito y fallo.

### E2-T3 — Preparar infraestructura común de testing

**Estimación:** 0,75 h  
**Alcance:** configurar Pytest, fixtures deterministas, fakes de LLM/embeddings, transporte HTTP simulado, datos Netflix mínimos y utilidades de captura de streaming. No incluye tests funcionales de cada agente.

**Criterios de aprobación:**

- `pytest` se ejecuta sin claves y sin acceso de red.
- Las fixtures son pequeñas, legibles y reutilizables.
- Existe un mecanismo que hace fallar un test si intenta usar red real.
- Los fakes permiten simular éxito, timeout, respuesta vacía, salida inválida y persistencia de traza fallida.

**Pruebas unitarias:**

- Smoke tests verifican el comportamiento configurado de cada fake.
- El bloqueo de red detecta una llamada accidental.
- La fixture temporal no modifica datos reales ni deja archivos tras la prueba.

## Epic E3 — Routing híbrido y control de intención

**Sprint:** 2 — Core y Routing  
**Objetivo:** seleccionar de forma fiable una sola ruta, extraer restricciones y evitar llamadas innecesarias.

### E3-T1 — Implementar clasificación estructurada

**Estimación:** 1,5 h  
**Alcance:** implementar un router híbrido: reglas deterministas para señales inequívocas y LLM estructurado para casos restantes. Devolver ruta, confianza, restricciones y motivo breve apto para logs, sin exponer razonamiento interno.

**Criterios de aprobación:**

- Solo devuelve las cuatro rutas permitidas.
- “Current”, “trending”, “lately” y equivalentes priorizan trending cuando la intención es clara.
- Género, temática, documental, película o serie de catálogo priorizan Netflix cuando no se exige actualidad.
- Las restricciones extraídas se normalizan sin inventar valores.
- Salida inválida del LLM activa un fallback seguro y observable.

**Pruebas unitarias:**

- Tabla parametrizada con ejemplos directos y paráfrasis en inglés y español.
- Casos con mayúsculas, puntuación, texto vacío y entradas excesivamente largas.
- Parseo de salida estructurada válida, inválida, incompleta y con confianza fuera de rango.
- Confirma que una regla concluyente evita llamar al fake LLM.

### E3-T2 — Resolver ambigüedad y fuera de alcance

**Estimación:** 0,75 h  
**Alcance:** definir umbral de confianza, política para señales contradictorias y mensajes breves de aclaración o rechazo. Estas rutas no deben llamar a TMDB, índice, embeddings ni agente generador.

**Criterios de aprobación:**

- Una consulta ambigua solicita una única aclaración concreta.
- Una petición ajena a recomendación audiovisual recibe una respuesta segura y útil.
- Una mezcla incompatible no elige arbitrariamente un agente con baja confianza.
- No se filtran detalles internos ni prompts.

**Pruebas unitarias:**

- Casos en el umbral, justo por encima y justo por debajo.
- Consultas que mezclan actualidad con disponibilidad Netflix sin prioridad clara.
- Verifica cero invocaciones a los puertos externos en ambas rutas.
- Verifica idioma y contenido mínimo de los mensajes de aclaración y fuera de alcance.

### E3-T3 — Evaluar y ajustar routing con el silver dataset

**Estimación:** 1,25 h  
**Alcance:** ejecutar el split `dev`, producir matriz de confusión, analizar errores por tags y ajustar reglas/prompts sin consultar `holdout`. Confirmar resultado sobre `test` al cerrar el sprint.

**Criterios de aprobación:**

- Accuracy global de routing ≥90 % en `test`.
- Accuracy por clase ≥80 %, para evitar ocultar una clase débil en el promedio.
- Se reportan falsos positivos que provocarían llamadas externas innecesarias.
- Cada ajuste conserva versión y razón; no se usa el split final.

**Pruebas unitarias:**

- Cálculo correcto de accuracy, accuracy por clase y matriz de confusión sobre una fixture conocida.
- Manejo explícito de dataset vacío y de clases sin ejemplos.
- Verifica que el runner de desarrollo rechace el split `holdout`.
- El reporte conserva IDs de fallos sin incluir secretos ni respuestas completas sensibles.

## Epic E4 — Trending Movie Agent

**Sprint:** 3 — Trending  
**Objetivo:** recomendar desde tendencias actuales sin usar endpoints no autorizados ni inventar títulos.

### E4-T1 — Implementar cliente TMDB autorizado y caché

**Estimación:** 1,25 h  
**Alcance:** crear cliente HTTPX asíncrono para `trending/movie/{day|week}`, con autenticación, timeout, validación de respuesta y caché TTL local. No se implementa ningún otro endpoint.

**Criterios de aprobación:**

- Solo se pueden construir URLs del endpoint permitido y ventanas `day` o `week`.
- Todo acceso externo tiene timeout explícito.
- Respuestas 2xx, vacías, 4xx, 5xx y JSON inválido se convierten a resultados o errores tipados.
- Una entrada válida de caché evita una nueva petición y una expirada se renueva.
- La API key no aparece en logs ni errores.

**Pruebas unitarias:**

- Transporte HTTP simulado verifica método, ruta, autenticación, parámetros y timeout.
- Casos 200 válido, 200 vacío, 401, 429, 500, timeout y payload malformado.
- Cache hit, cache miss, expiración y separación entre ventanas.
- Test de contrato que falla ante cualquier ruta distinta de `trending/movie/day|week`.

### E4-T2 — Implementar filtrado y ranking explicable

**Estimación:** 1 h  
**Alcance:** seleccionar entre candidatos TMDB mediante funciones deterministas que consideren coincidencia temática disponible, fecha de estreno, popularidad y votos. Documentar la heurística de “mejor” y no confundir tendencia con estreno reciente.

**Criterios de aprobación:**

- Devuelve de uno a tres candidatos pertenecientes a la entrada.
- Aplica restricciones solo sobre campos presentes; no infiere géneros ausentes mediante otro endpoint.
- La puntuación y desempates son deterministas.
- Si no hay coincidencia fiable, devuelve un estado de baja confianza en lugar de forzar una recomendación.
- La explicación de score es auditable en logs internos.

**Pruebas unitarias:**

- Ranking con coincidencia temática, recencia, popularidad y número de votos controlados.
- Empates, campos nulos, fechas inválidas, lista vacía y menos de tres candidatos.
- Ningún resultado contiene un ID ausente de la entrada.
- Diferencia explícitamente un título trending antiguo de uno estrenado recientemente.

### E4-T3 — Generar respuesta grounded de tendencias

**Estimación:** 1 h  
**Alcance:** redactar en streaming una respuesta con título, año cuando exista, tipo, explicación y procedencia. El prompt recibirá solo candidatos seleccionados y la salida se validará contra sus IDs o títulos.

**Criterios de aprobación:**

- Toda recomendación pertenece a los candidatos autorizados.
- La respuesta incluye procedencia `TMDB Trending` y distingue tendencia de fecha de estreno.
- Respeta el idioma de la consulta y el máximo de tres recomendaciones.
- Una salida LLM no grounded se rechaza o sustituye por una plantilla determinista segura.

**Pruebas unitarias:**

- Fake LLM con salida válida produce recomendaciones esperadas.
- Fake LLM que añade un título ajeno activa el validador y fallback.
- Campos opcionales ausentes no generan afirmaciones falsas.
- Verifica procedencia, disclaimer, idioma y límite de recomendaciones.

### E4-T4 — Implementar fallbacks y errores del agente

**Estimación:** 0,75 h  
**Alcance:** manejar credenciales ausentes, timeout, rate limit, servicio no disponible, lista vacía y baja coincidencia. El usuario recibe un mensaje seguro y el sistema registra causa y correlación.

**Criterios de aprobación:**

- Cada fallo conocido tiene código interno y mensaje público accionable.
- No se muestra stack trace, URL con credenciales ni payload interno.
- Si existe caché válida o stale permitida por política, se usa y se informa de la limitación.
- El error puede emitirse como evento SSE válido.

**Pruebas unitarias:**

- Tabla parametrizada de error técnico → código interno → mensaje público.
- Verifica fallback de caché y ausencia de fallback cuando no es seguro.
- Serializa cada error como evento SSE y cierra el stream correctamente.
- Captura de logs confirma presencia de correlation ID y ausencia de secretos.

## Epic E5 — Netflix RAG Agent

**Sprint:** 4 — Netflix  
**Objetivo:** construir un pipeline local reproducible que recupere títulos relevantes y genere respuestas limitadas al snapshot.

### E5-T1 — Ingerir y normalizar el dataset Netflix

**Estimación:** 1,25 h  
**Alcance:** leer el CSV configurado, validar columnas, normalizar nulos/listas/fechas/tipo, eliminar duplicados y producir documentos con ID estable. El texto indexable combinará título, descripción, géneros y metadatos útiles sin alterar el dato original.
**Alcance:** formalizar el pipeline reproducible sobre la copia del dataset adquirida y perfilada en Sprint 0: resolver la ruta local o el mecanismo documentado de adquisición, leer el CSV configurado, validar columnas, normalizar nulos/listas/fechas/tipo, eliminar duplicados y producir documentos con ID estable. El texto indexable combinará título, descripción, géneros y metadatos útiles sin alterar el dato original. La inspección inicial no se repite; aquí se implementa la transformación definitiva e idempotente.

**Criterios de aprobación:**

- Un comando procesa el dataset desde `NETFLIX_DATASET_PATH`.
- Columnas obligatorias ausentes y fichero inválido producen errores claros.
- Cada documento tiene ID, título, descripción normalizada, tipo, año y géneros cuando existan.
- La transformación es determinista y genera fingerprint del snapshot.
- Se registra número de filas leídas, aceptadas, descartadas y deduplicadas.

**Pruebas unitarias:**

- Fixtures con fila completa, nulos, listas serializadas, Unicode y año inválido.
- Detecta fichero ausente, CSV corrupto y columnas obligatorias ausentes.
- Deduplicación e IDs son estables entre ejecuciones.
- El texto indexable contiene solo campos autorizados y no introduce la cadena `nan`.

### E5-T2 — Configurar índice híbrido Meilisearch CE reproducible

**Estimación:** 1,5 h  
**Alcance:** crear un índice Meilisearch Community Edition con primary key estable, documentos Netflix, embedder configurable y settings versionados. Definir `searchableAttributes` para título, descripción y géneros; `filterableAttributes` para tipo, género, año y restricciones soportadas; y `sortableAttributes` solo cuando exista una señal de calidad válida. Incluir comando idempotente de configuración/ingesta y detección de índice obsoleto.

**Criterios de aprobación:**

- El índice se genera con un único comando contra `netflix-db` levantado por Compose, sin Meilisearch Cloud.
- Documento y vector mantienen correspondencia estable.
- Cambios de snapshot, modelo, dimensión, template o settings invalidan el índice con un mensaje accionable.
- Los lotes parciales pueden reanudarse sin duplicación.
- Las operaciones asíncronas de Meilisearch esperan y verifican el estado de sus tasks.
- La implementación concreta se consume mediante `SearchBackend` y puede sustituirse por un fake.
- La configuración declara `edition=community` y no usa sharding, replication, network/remotes ni otras funciones Enterprise.

**Pruebas unitarias:**

- Fake embedder determinista verifica batching, orden, dimensiones y normalización.
- Upsert/consulta conserva documentos, IDs, metadatos y vectores.
- Detecta índice ausente, task fallida, settings obsoletos o dimensión incompatible.
- Reanudación procesa solo lotes pendientes y no duplica documentos.
- Verifica configuración idempotente de searchable/filterable/sortable attributes y embedder.
- Unit test del builder usa una allow-list CE y no puede serializar `useNetwork`, network/remotes, sharding, replication o personalización.
- Unit test de settings factory rechaza cualquier clave no incluida en el contrato Community acordado.

### E5-T3 — Implementar hybrid search, filtros y reranking

**Estimación:** 1,5 h  
**Alcance:** consultar Meilisearch CE en tres modos comprobables: léxico (`semanticRatio=0`), semántico (`semanticRatio=1`) e híbrido (`0<semanticRatio<1`). Aplicar filtros por tipo, género y año, solicitar top-k y realizar reranking ligero en backend solo si aporta una señal documentada. Incluir umbral/fallback de baja relevancia.

**Criterios de aprobación:**

- Devuelve candidatos ordenados con modo, score/ranking details y evidencia de campos coincidentes.
- Los filtros obligatorios se cumplen al 100 % o se devuelve fallback sin resultados.
- El top-k, embedder, `semanticRatio` y umbral son configurables y quedan registrados en la traza.
- La configuración inicial se calibra contra baselines léxico y semántico usando Silver; no se presupone que hybrid sea siempre superior.
- Coincidencias exactas, prefijos y typos aprovechan el ranking léxico; consultas conceptuales mantienen señal semántica.
- Ninguna búsqueda envía `useNetwork`, personalización u otro parámetro Enterprise.
- La recuperación local tiene objetivo p95 inferior a 1 segundo para el corpus completo.

**Pruebas unitarias:**

- Search backend fake valida orden, top-k y los tres valores/modos de `semanticRatio`; integración separada valida Meilisearch CE real.
- Filtros individuales y combinados por tipo, género y rango de año.
- Título exacto, typo, prefijo, query conceptual, empate, corpus vacío y candidatos bajo umbral.
- Ningún candidato incumple un filtro obligatorio.
- Contract test técnico —fuera del Silver Dataset— prohíbe todo parámetro o feature Enterprise.

### E5-T4 — Generar respuesta RAG grounded y fallback

**Estimación:** 1 h  
**Alcance:** construir contexto solo con documentos recuperados, pedir una respuesta de una a tres recomendaciones y validar cada título. Añadir procedencia `Netflix Dataset` y aviso de snapshot histórico.

**Criterios de aprobación:**

- Ningún título de la respuesta está fuera del conjunto recuperado.
- Se incluyen título, año y tipo únicamente cuando están disponibles.
- La explicación se apoya en descripción, géneros o metadatos recuperados.
- Siempre se muestra la limitación de disponibilidad actual.
- Baja similitud o contexto vacío produce fallback sin inventar recomendaciones.

**Pruebas unitarias:**

- Salida válida con uno, dos y tres títulos recuperados.
- Título inventado, año alterado o tipo incorrecto activa validación y fallback.
- Contexto vacío y todos los scores bajo umbral producen mensaje seguro.
- Verifica idioma, procedencia y disclaimer histórico.

### E5-T5 — Evaluar retrieval con oracles del silver dataset

**Estimación:** 1,25 h  
**Alcance:** ejecutar casos Netflix con relevancia graduada y elementos esperados/aceptables en sus fixtures; calcular Recall@k, Precision@k, MRR, nDCG y coincidencia de filtros para baseline léxico, baseline semántico y configuración híbrida. Ajustar solo con `dev`, confirmar en `test` y no consultar `holdout`.

**Criterios de aprobación:**

- Recall@5 objetivo ≥0,80 y Precision@5 objetivo ≥0,60 en los casos con oracle.
- Coincidencia de filtros obligatorios =100 %.
- Se reportan métricas agregadas y por segmento, junto con tamaño de muestra.
- Se reporta hybrid uplift frente al mejor baseline puro y éxito específico en queries exactas, typos y conceptuales.
- Si una meta no se alcanza, queda documentado el análisis y una mejora priorizada; no se falsea el resultado.

**Pruebas unitarias:**

- Métricas verificadas contra ejemplos manuales con relevancia conocida.
- Manejo de varios relevantes, cero recuperados, k mayor que resultados y oracle vacío.
- El evaluador rechaza IDs de consulta o documentos inexistentes.
- El runner no accede a red ni al split `holdout` en modo de desarrollo.
- Comparación de tres modos usa exactamente los mismos casos, filtros y corpus.

## Epic E6 — Orquestación, streaming, UX y operación

**Sprint:** 5 — UX y Operación  
**Objetivo:** integrar el producto verticalmente y ofrecer una experiencia simple, observable y segura.

### E6-T1 — Implementar orquestador de conversación

**Estimación:** 1 h  
**Alcance:** coordinar validación de entrada, routing, selección de un único agente, propagación de correlation ID y traducción de resultados a eventos. No incorpora memoria persistente.

**Criterios de aprobación:**

- Cada consulta sigue exactamente una ruta terminal y abre/cierra un run de traza.
- `clarification` y `out_of_scope` no invocan servicios de datos.
- Las dependencias se inyectan y pueden sustituirse en tests.
- Cancelación y error no dejan tareas en segundo plano.

**Pruebas unitarias:**

- Una prueba por ruta verifica agente invocado y agentes no invocados.
- Propaga correlation ID, trace ID y run ID en éxito, aclaración y error.
- Cancela correctamente una operación simulada.
- Rechaza consulta vacía o por encima del límite antes de rutear.

### E6-T2 — Exponer FastAPI y streaming SSE

**Estimación:** 1,5 h  
**Alcance:** crear endpoint de salud y endpoint de chat SSE con eventos `status`, `content`, `error` y `done`; soportar desconexión y headers adecuados. El contenido se emitirá progresivamente y los estados no revelarán chain-of-thought.

**Criterios de aprobación:**

- El cliente recibe un evento inicial rápidamente y termina siempre con `done` salvo desconexión.
- Los eventos tienen esquema estable, correlation ID, trace ID y orden válido.
- Éxitos y errores controlados usan el mismo canal SSE.
- Desconectar el cliente cancela trabajo pendiente.
- El objetivo con dependencias simuladas es primer evento <500 ms; el objetivo funcional de primer contenido es <5 s excluyendo indisponibilidad externa.

**Pruebas unitarias:**

- TestClient valida status, headers y secuencia de eventos en las cuatro rutas.
- Chunking parcial reconstruye exactamente el texto final.
- Error antes y durante contenido produce una secuencia válida y sin stack trace.
- Desconexión simulada ejecuta cancelación y cierre de recursos.

### E6-T3 — Crear interfaz web mínima

**Estimación:** 1 h  
**Alcance:** vista única con caja de consulta, botón/enviar, estados breves, render progresivo, procedencia, errores comprensibles y accesibilidad básica. No incluye framework visual complejo ni historial persistente.

**Criterios de aprobación:**

- Puede usarse tras arrancar el servidor, sin instalación adicional del lado cliente.
- Impide envíos vacíos y evita dobles envíos accidentales.
- Muestra streaming, procedencia, limitaciones y errores sin detalles técnicos.
- Mantiene una interacción usable con teclado y tamaños de pantalla habituales.

**Pruebas unitarias y verificaciones:**

- Unit tests de funciones JS puras para parseo de eventos, acumulación de chunks y transición de estados, si se separan como módulos.
- Test de API/UI verifica que el HTML inicial carga y referencia el endpoint correcto.
- Verificación manual: éxito trending, éxito Netflix, aclaración, fuera de alcance y fallo simulado.
- Verificación básica de accesibilidad: labels, foco visible, región viva para streaming y contraste legible.

### E6-T4 — Añadir errores seguros y observabilidad

**Estimación:** 1,5 h  
**Alcance:** centralizar manejo de excepciones y logging estructurado correlacionado con la traza persistente: ruta, agente, duraciones, número de documentos, primer token y duración total. No registrar prompts completos, claves ni datos sensibles.

**Criterios de aprobación:**

- Toda petición tiene correlation ID, trace ID y run ID generado o validado.
- Se registran las métricas exigidas por el briefing cuando aplican.
- Los mensajes públicos son estables y accionables; los logs conservan la causa técnica.
- El redactor de logs elimina claves, tokens y parámetros sensibles.
- Fallos del logger no rompen la respuesta del usuario.

**Pruebas unitarias:**

- Captura de logs valida campos obligatorios y correlación con la traza en cada ruta.
- Redacción de API keys en headers, URLs, excepciones y estructuras anidadas.
- Reloj simulado valida duraciones y time-to-first-token.
- Excepción del logger no sustituye el resultado original ni rompe SSE.

### E6-T5 — Crear tests de integración vertical sin red

**Estimación:** 1 h  
**Alcance:** probar API → router → agente → streaming con fakes y transporte HTTP simulado. Cubrir caminos felices y fallos críticos sin API keys reales.

**Criterios de aprobación:**

- Existe al menos un flujo completo por ruta.
- Existen flujos de timeout TMDB, índice ausente, LLM inválido y fallo durante streaming.
- Las aserciones comprueban respuesta, fuente, llamadas realizadas, traza resultante y ausencia de llamadas prohibidas.
- La suite es determinista y apta para CI.

**Pruebas:**

- Integración trending con payload TMDB conocido y respuesta grounded.
- Integración Netflix con índice de fixture y recomendación grounded.
- Integración de aclaración/out-of-scope con cero llamadas externas.
- Integración de errores antes y después del primer chunk.

## Epic E7 — Generación, persistencia y explotación de trazas

**Sprints:** 2, 5 y 6  
**Objetivo:** reconstruir cada ejecución de extremo a extremo para monitorización, depuración, evaluación offline y comparación entre versiones.  
**Valor:** permite distinguir si un fallo procede del router, tool request, retrieval, ranking, grounding, streaming o infraestructura, en lugar de observar solo la respuesta final.

### E7-T1 — Definir contrato, eventos y política de trazas

**Sprint:** 2  
**Estimación:** 1,25 h  
**Alcance:** diseñar una traza jerárquica compatible conceptualmente con OpenTelemetry, con root run y spans hijos. Definir nombres estables, atributos, eventos, estados, versionado y relación con correlation ID y caso de evaluación. La compatibilidad conceptual no obliga a desplegar un Collector en el MVP.

Spans mínimos:

- `request.handle` como raíz.
- `router.classify`.
- `agent.trending` o `agent.netflix`.
- `tool.tmdb.request` o `retrieval.meilisearch.search`.
- `embedding.generate`, `rerank.candidates` y `llm.generate` cuando apliquen.
- `stream.response`.
- `evaluation.validate` durante ejecuciones silver.

Atributos/eventos mínimos:

| Grupo | Campos |
| --- | --- |
| Identidad | `trace_id`, `span_id`, `parent_span_id`, `run_id`, `correlation_id`. |
| Tipo de run | `chat`, `evaluation` o `dataset_generation`. |
| Versión | `trace_schema_version`, `app_version`, `config_version`, `prompt_version`, `model`, `dataset_version`. |
| Evaluación | `case_id`, `suite`, `split`, `attempt_number`, `expected_route/tool/action`. |
| Routing | Ruta, tool y action observadas, confianza y restricciones normalizadas. |
| Tool request | Tool, endpoint lógico, parámetros sanitizados, timeout, retry y cache hit. |
| Retrieval | Motor/versión, index UID, modo, query sanitizada/hash, filtros, embedder, `semanticRatio`, top-k, ranking details, IDs y candidatos. |
| Generación | Modelo, tokens de entrada/salida, finish reason, coste estimado y IDs grounded. |
| Rendimiento | Inicio, fin, duración, TTFT y duración total. |
| Resultado | Estado `started/completed/failed/cancelled`, error tipado y response type. |

**Criterios de aprobación:**

- El contrato distingue run, span y evento y permite reconstruir su orden.
- Los nombres de span tienen cardinalidad acotada; IDs de casos/títulos son atributos, no nombres.
- Cada métrica del Silver Dataset identifica exactamente qué campos de traza necesita.
- Se define política de captura: payloads completos desactivados por defecto, secretos siempre redactados y consultas de usuarios reales configurables entre `none`, `hash`, `redacted` o `full`.
- En runtime normal el fallo del trace store es fail-open con log seguro; en evaluación es fail-closed para no aceptar resultados sin evidencia auditable.

**Pruebas unitarias:**

- Valida trace/span IDs, relación padre-hijo, timestamps, estados y transición final única.
- Rechaza spans huérfanos, fin anterior al inicio y atributos fuera del schema.
- Verifica mapeo de cada ruta a la secuencia mínima de spans esperada.
- Sanitiza API keys, authorization headers, prompts y payloads anidados.
- Snapshot test del schema y catálogo de eventos para exigir versionado ante cambios.

### E7-T2 — Diseñar schema PostgreSQL y migraciones

**Sprint:** 5  
**Estimación:** 1,25 h  
**Alcance:** modelar y migrar una base separada con tablas `execution_runs`, `execution_spans`, `execution_events` y `evaluation_results`. Usar columnas tipadas para identidad, tiempos, estado y dimensiones frecuentes; reservar `JSONB` para atributos versionados y detalles variables. Definir índices, claves, retención y borrado por lote.

**Criterios de aprobación:**

- Runs, spans, eventos y resultados tienen claves foráneas e integridad referencial.
- Existen índices para `trace_id`, `run_id`, `case_id`, `created_at`, `status`, `route`, `model`, `dataset_version` y `app_version`.
- Los atributos JSONB consultados por análisis disponen de índice o columna promovida documentada.
- Las migraciones pueden aplicarse desde cero y actualizar una base ya creada.
- La retención es configurable; holdout/evaluación puede marcar runs protegidos frente al borrado automático.

**Pruebas unitarias y de integración:**

- Modelos y repositorio se prueban contra fake/unit of work sin PostgreSQL.
- Test de integración aplica `upgrade`, inserta datos, consulta y ejecuta `downgrade/upgrade` sobre `trace-db` efímero.
- Constraints rechazan IDs duplicados, span sin run y evaluation result sin caso/run.
- Consultas por versión, estado, ruta y rango temporal devuelven resultados esperados.
- Retención elimina solo runs elegibles y conserva runs protegidos.

### E7-T3 — Implementar TraceRecorder e instrumentación

**Sprint:** 5  
**Estimación:** 1,5 h  
**Alcance:** implementar un puerto `TraceRecorder`, adaptador PostgreSQL asíncrono y context managers/decoradores para abrir, anotar y cerrar spans. Instrumentar router, agentes, TMDB, Meilisearch, LLM, streaming y errores sin acoplar la lógica de negocio al driver SQL.

**Criterios de aprobación:**

- Toda petición genera un run con exactamente un estado final.
- Los spans conservan contexto a través de operaciones async y streaming.
- Tool requests, retrieval y selección registran argumentos/evidencias sanitizados.
- Tokens, coste y TTFT se guardan solo cuando estén disponibles; su ausencia no rompe la ejecución.
- El recorder soporta idempotencia por `run_id` y evita duplicados ante reintentos de persistencia.
- La política fail-open/fail-closed se aplica según `TRACE_CAPTURE_MODE`.

**Pruebas unitarias:**

- Fake recorder verifica secuencia y atributos de las cuatro rutas.
- Éxito, timeout, excepción, cancelación y desconexión cierran spans con estado correcto.
- Context propagation mantiene trace/span IDs en tareas asíncronas hijas.
- Reintento de escritura no duplica run, span ni evento.
- Fallo del recorder no rompe chat en runtime y sí invalida el caso en modo evaluación.

### E7-T4 — Exponer consulta, monitorización y exportación

**Sprint:** 5  
**Estimación:** 1 h  
**Alcance:** añadir endpoints internos o CLI para listar runs, ver detalle jerárquico, filtrar por tipo/caso/versión/ruta/estado/fecha, exportar JSONL e importar manifiestos de generación producidos antes de desplegar `trace-db`. El MVP no incluye dashboard dedicado; la UI de monitorización avanzada queda como P2.

**Criterios de aprobación:**

- Puede localizarse una ejecución por `run_id`, `trace_id`, `correlation_id` o `case_id`.
- La vista detalle muestra spans ordenados, tiempos, decisiones, evidencias y errores sanitizados.
- La exportación incluye schema version y es consumible por el runner de evaluación.
- La importación es idempotente y acepta runs `dataset_generation` conformes al schema.
- Paginación y límites evitan lecturas sin cota.
- Los endpoints de trazas no se exponen públicamente sin una configuración explícita.

**Pruebas unitarias:**

- Filtros individuales/combinados, paginación, orden y ausencia de resultados.
- Serialización de árbol con spans anidados y eventos ordenados.
- Export/import conserva identidad y atributos permitidos.
- Importar dos veces el mismo manifiesto no duplica runs, spans ni eventos.
- Run inexistente produce 404 seguro y filtros inválidos producen 422.
- Configuración pública desactivada bloquea endpoints desde la red pública.

### E7-T5 — Vincular trazas con evaluación y scorecards

**Sprint:** 6  
**Estimación:** 1,25 h  
**Alcance:** hacer que el runner use la traza como fuente de verdad para route/tool/action, parámetros, retrieval, grounding, latencias, tokens, coste, retries y errores. Persistir cada verdict en `evaluation_results` sin mutar la traza original.

**Criterios de aprobación:**

- Cada resultado referencia `run_id`, `case_id`, validador, versión y timestamp.
- Puede reevaluarse una misma traza con una nueva versión de validadores sin reejecutar el agente.
- Métricas deterministas se calculan desde eventos/atributos estructurados, no mediante parsing de logs.
- Repeticiones del mismo caso se distinguen y alimentan estabilidad/pass rate.
- Trazas incompletas o incompatibles con el schema se reportan como error de infraestructura.

**Pruebas unitarias:**

- Una traza fixture produce route/tool/retrieval/grounding metrics conocidas.
- Dos versiones de evaluador conviven sin sobrescribir resultados.
- Trazas incompletas, duplicadas o de versión desconocida fallan de forma explícita.
- Repeticiones se agrupan por caso y conservan `attempt_number`.
- El evaluador no puede alterar runs, spans ni eventos ya cerrados.

## Epic E8 — Arquitectura Docker multi-servicio

**Sprints:** 2, 4 y 5  
**Objetivo:** ejecutar el sistema completo mediante cuatro servicios aislados, reproducibles y persistentes, coordinados con Docker Compose.  
**Valor:** reduce diferencias de entorno, separa ciclos de vida y permite arrancar el take-home con pocos comandos.

### E8-T1 — Definir topología, redes, volúmenes y contratos

**Sprint:** 2  
**Estimación:** 1 h  
**Alcance:** definir `compose.yaml` con cuatro servicios runtime: `frontend`, `backend`, `netflix-db` y `trace-db`. Crear red `public` para frontend/backend, red `data` para backend/databases y volúmenes `netflix_data` y `trace_data`. Migraciones e ingesta se ejecutarán como comandos one-off con la imagen del backend, no como servicios runtime adicionales.

**Criterios de aprobación:**

- Solo `frontend` expone puerto público por defecto; backend puede exponerse mediante profile de desarrollo.
- Las bases de datos solo son accesibles desde la red `data`.
- Cada servicio tiene imagen versionada, healthcheck, límites/configuración y política de restart apropiada para desarrollo.
- `depends_on` usa condiciones de salud donde sean necesarias, sin asumir que orden de arranque equivale a disponibilidad.
- Los secretos se inyectan en runtime y no se copian a imágenes ni al Compose versionado.

**Pruebas unitarias y verificaciones:**

- `docker compose config` valida sintaxis, interpolación y servicios esperados.
- Script/check de arquitectura confirma cuatro servicios, dos redes y dos volúmenes.
- Verifica que ningún database service publique puerto al host en el perfil por defecto.
- Verifica que imágenes no contengan valores de `.env` ni claves conocidas.

### E8-T2 — Construir imagen del frontend

**Sprint:** 5  
**Estimación:** 0,75 h  
**Alcance:** crear una imagen mínima que sirva assets estáticos y actúe como reverse proxy de `/api` al backend. Si se usa toolchain Node, se aplicará multi-stage build y la imagen final no incluirá dependencias de desarrollo.

**Criterios de aprobación:**

- La imagen arranca como usuario no privilegiado cuando la base lo permita.
- Sirve la UI y proxy SSE sin buffering que impida streaming.
- No contiene source maps, dependencias o secretos innecesarios.
- Tiene healthcheck HTTP y tamaño razonable documentado.

**Pruebas unitarias y verificaciones:**

- Unit tests de UI se ejecutan en el stage de build.
- Build limpio y smoke test HTTP de `/` y healthcheck.
- Test de proxy reconstruye correctamente un stream SSE del backend.
- Inspección de imagen confirma usuario, archivos esperados y ausencia de secretos.

### E8-T3 — Construir imagen del backend

**Sprint:** 5  
**Estimación:** 1 h  
**Alcance:** crear imagen Python 3.11+ multi-stage para FastAPI, CLI de ingesta, migraciones y evaluación. Separar dependencias de build/runtime, ejecutar como usuario no root y manejar señales/cierre graceful.

**Criterios de aprobación:**

- La misma imagen ejecuta servidor y comandos one-off mediante distintos commands.
- El contenedor no arranca si la configuración obligatoria del modo seleccionado es inválida.
- Healthcheck distingue proceso vivo de backend preparado.
- Cierre detiene streams y conexiones a Meilisearch/PostgreSQL correctamente.
- Dependencias están fijadas y la imagen no incluye caches ni tooling innecesario.

**Pruebas unitarias y verificaciones:**

- Suite backend se ejecuta durante build o CI antes de publicar imagen.
- Smoke test importa app, arranca healthcheck y procesa una consulta con fakes.
- Test de señal valida cierre graceful sin runs de traza abiertos.
- Inspección confirma usuario no root y ausencia de secrets/dataset embebido.

### E8-T4 — Configurar `netflix-db` con Meilisearch CE/MIT

**Sprint:** 4  
**Estimación:** 0,75 h  
**Alcance:** usar una imagen oficial y versionada de Meilisearch Community Edition, volumen persistente, healthcheck, master key inyectada y configuración local. Crear índice, settings y documentos mediante el comando de ingesta del backend. No exponer Meilisearch públicamente en el perfil normal ni activar funciones Enterprise.

**Criterios de aprobación:**

- Reiniciar el servicio conserva índice, documentos, settings y vectores.
- Recrear el índice desde cero es posible con un único comando documentado.
- Healthcheck bloquea ingesta/consultas hasta disponibilidad.
- El índice registra fingerprint de dataset, modelo, dimensión, template y settings.
- Searchable, filterable y sortable attributes quedan configurados antes de la carga.
- La edición queda identificada como Community/MIT y el build no habilita sharding, replication, network/remotes ni código/configuración Enterprise.
- La licencia y image digest quedan documentados en SBOM o reporte de dependencias.

**Pruebas unitarias y de integración:**

- Arranque limpio, creación idempotente, ingesta, búsqueda lexical/semantic/hybrid, filtros y persistencia tras restart.
- Dataset/modelo incompatible se detecta antes de servir consultas.
- Verifica que la red pública no alcanza el puerto de Meilisearch.
- License/contract test confirma CE/MIT y rechaza parámetros o features Enterprise.
- Backup/export mínimo o regeneración completa queda probado y documentado.

### E8-T5 — Configurar `trace-db` con PostgreSQL

**Sprint:** 5  
**Estimación:** 0,75 h  
**Alcance:** usar imagen oficial PostgreSQL fijada por versión, volumen persistente, healthcheck y credenciales de entorno. Aplicar migraciones mediante backend one-off. No exponer la base públicamente en el perfil normal.

**Criterios de aprobación:**

- Reiniciar conserva trazas y resultados.
- Base vacía se inicializa y migra con un comando documentado.
- Backend no se declara ready si falta una migración requerida.
- Usuario de aplicación tiene privilegios mínimos y credenciales no versionadas.
- Existe procedimiento de exportación/backup para resultados de evaluación.

**Pruebas unitarias y de integración:**

- Healthcheck, migración desde cero, reinicio y consulta de persistencia.
- Credenciales inválidas y schema desactualizado producen errores accionables.
- Verifica privilegios de aplicación y aislamiento de red.
- Export/import conserva runs, spans, eventos y resultados relacionados.

### E8-T6 — Validar Compose end-to-end

**Sprint:** 5  
**Estimación:** 1 h  
**Alcance:** automatizar build, arranque, espera de healthchecks, migración, ingesta de fixture, ejecución de las cuatro rutas, consulta de trazas y apagado limpio. Debe probar el sistema como lo recibirá el evaluador.

**Criterios de aprobación:**

- `docker compose up --build` levanta los cuatro servicios sin pasos manuales ocultos.
- Tras bootstrap, UI y API responden; Netflix consulta Meilisearch CE y todas las rutas generan trazas en PostgreSQL.
- Reiniciar conserva ambas bases y recrear volúmenes permite bootstrap desde cero.
- El smoke test falla con diagnóstico si un healthcheck, migración, ingesta o traza no está disponible.
- README documenta arranque, parada, reset seguro, logs, migración, ingesta y evaluación.

**Pruebas:**

- Smoke end-to-end happy path de trending y Netflix.
- Aclaración y out-of-scope confirman cero tool calls en la traza.
- Fault injection detiene cada database service y verifica el comportamiento acordado.
- Test de persistencia compara conteos/checksums antes y después de restart.
- Validación final confirma exactamente cuatro contenedores runtime saludables.

## Epic E9 — Evaluación final, endurecimiento y entrega

**Sprint:** 6 — Evaluación y Entrega  
**Objetivo:** demostrar el cumplimiento del assessment y entregar un repositorio ejecutable y comprensible.

### E9-T1 — Ejecutar evaluación final bloqueada

**Estimación:** 1,25 h  
**Alcance:** ejecutar una sola evaluación formal sobre `silver_v1/holdout` una vez congelados código, imágenes y configuración; consolidar routing, tool calls, retrieval, grounding, filtros, fallos, estabilidad, coste y latencias desde las trazas. No reajustar con el resultado sin declarar una nueva versión.

**Criterios de aprobación:**

- El reporte incluye versión de código/configuración, imágenes, dataset, modelos, prompts, trace schema y timestamp.
- Routing global ≥90 %; títulos no soportados =0 %; filtros obligatorios =100 %.
- Se presentan Macro F1, tool request accuracy, Recall@5, Precision@5, nDCG, grounding, errores controlados, estabilidad, coste y latencias con tamaño de muestra.
- Cada score puede auditarse hasta `case_id`, `run_id`, spans y evidencias.
- Todo incumplimiento se declara como limitación y genera una tarea futura, sin ocultarlo.
- Los resultados son reproducibles mediante un comando documentado, salvo variación externa explícita.

**Pruebas unitarias:**

- Agregador de métricas probado con fixtures de resultados completos, parciales y fallidos.
- Verifica que el modo final use solo `holdout` y no sobrescriba artefactos o resultados previos.
- El reporte conserva precisión numérica y marca métricas no calculables.
- Detecta títulos no soportados comparando salida con evidencia recuperada.

### E9-T2 — Validar rendimiento, seguridad y resiliencia

**Estimación:** 1 h  
**Alcance:** medir p50/p95 con dependencias controladas, revisar timeouts, límites de entrada, sanitización, caché y degradación. No incluye load testing productivo.

**Criterios de aprobación:**

- Routing p95 <2 s y retrieval Meilisearch p95 <1 s en el entorno documentado.
- Primer evento SSE <500 ms con dependencias simuladas y primer contenido objetivo <5 s en condiciones normales.
- Todas las llamadas externas tienen timeout y política de error explícita.
- No hay secretos en repositorio, imágenes, logs, trazas ni artefactos de evaluación.
- Los fallos críticos se transforman en respuestas controladas.

**Pruebas unitarias y verificaciones:**

- Benchmarks repetibles de router y retrieval con reloj y corpus fijados.
- Tests de límites para tamaño de consulta, caracteres de control y parámetros inválidos.
- Escaneo del árbol versionado para patrones de secretos y ficheros `.env` no permitidos.
- Fault injection para timeout, rate limit, fichero corrupto, índice ausente, trace-db no disponible y cierre de stream.

### E9-T3 — Completar empaquetado y reproducibilidad

**Estimación:** 0,75 h  
**Alcance:** fijar dependencias e imágenes, completar `.env.example`, `compose.yaml`, migraciones, configuración/ingesta Meilisearch, bootstrap y comandos de evaluación. Docker Compose es el mecanismo principal y debe funcionar en entorno limpio.

**Criterios de aprobación:**

- Una secuencia documentada construye, configura, migra, ingiere, prueba y arranca los cuatro servicios.
- Las versiones son compatibles con Python 3.11+.
- Los artefactos generados y secretos están excluidos correctamente de Git.
- El arranque detecta y explica configuración, migración o índice faltante.
- Las imágenes usan tags fijados y los volúmenes permiten persistencia/reconstrucción documentada.

**Pruebas unitarias y verificaciones:**

- Smoke test importa el paquete y crea la aplicación con configuración fake.
- Test de comandos de migración e ingesta sobre fixtures y contenedores efímeros.
- Verificación completa con Docker Compose desde volúmenes vacíos.
- Validación de que `.env.example` contiene nombres, nunca valores secretos.

### E9-T4 — Redactar README, informe y arquitectura

**Estimación:** 1 h  
**Alcance:** documentar instalación end-to-end, configuración, uso, tests, evaluación, diseño, heurísticas, retos, resultados, limitaciones, siguientes pasos y estrategia de productización. Añadir diagrama de arquitectura mantenible en texto, Mermaid o formato fuente.

**Criterios de aprobación:**

- Un evaluador puede ejecutar el proyecto siguiendo solo el README.
- El informe explica decisiones y metodología, no solo enumera componentes.
- Se documentan endpoint único de TMDB, snapshot Netflix, Meilisearch CE/MIT, hybrid search, schema de trazas, heurística de ranking y variabilidad LLM.
- El informe incluye ADR de selección Meilisearch, comparación de baselines y checklist de exclusión Enterprise.
- Se enlazan comandos y resultados reales de evaluación.
- El diagrama representa los cuatro contenedores, redes, volúmenes, router, agentes, fuentes, streaming y trazas.

**Pruebas unitarias y verificaciones:**

- No aplica unit test de lógica de negocio.
- Se ejecutan todos los comandos documentados en el orden publicado.
- Verificación de enlaces/rutas locales y renderizado del diagrama.
- Checklist de secciones exigidas por el assessment: enfoque, desafíos, resultados, decisiones, herramientas/modelos, siguientes pasos y productización.

### E9-T5 — Realizar aceptación final y preparar entrega

**Estimación:** 1 h  
**Alcance:** ejecutar suite completa, revisar trazabilidad, limpiar artefactos, comprobar contenido del repositorio y preparar ZIP o repositorio privado. No incluye despliegue público.

**Criterios de aprobación:**

- Todos los tests obligatorios pasan o toda excepción está documentada con causa.
- Cada requisito del assessment tiene implementación, prueba o justificación explícita.
- El repositorio no contiene API keys, `.env`, volúmenes, dumps sensibles, cachés ni datos temporales.
- La entrega incluye código, Dockerfiles/Compose, migraciones, documentación, tests, silver dataset permitido, trazas/resultados exportados y reporte.
- La entrega incluye evidencia de Meilisearch Community Edition/MIT y cero dependencias de Enterprise/BUSL.
- La demo crítica se ejecuta desde un entorno limpio antes de empaquetar.

**Pruebas y verificaciones:**

- Suite completa de unit, integration, contract y smoke tests.
- Test end-to-end local de las cuatro rutas y de un fallo por fuente externa.
- Test de exactamente cuatro servicios saludables y persistencia de ambas bases tras restart.
- Escaneo final de secretos y revisión del listado de ficheros del entregable.
- Escaneo de licencia/SBOM y contract test de parámetros Meilisearch CE.
- Comparación automática de la matriz de trazabilidad con estados de tareas y evidencias.

## 6. Dependencias y camino crítico

```text
E0 -> E1 -> E2 -> E3 -> E4/E5 -> E6 -> E9
             |                  ^
             +-> E7 -----------+
             +-> E8 -----------+
```

- E1 precede al ajuste del router y fija casos, fixtures, métricas y campos de traza requeridos.
- E2 precede a cualquier integración porque define configuración, puertos y fakes.
- E7 comienza con el contrato de trazas en Sprint 2 y completa persistencia antes de la integración final.
- E8 define topología en Sprint 2; Meilisearch CE debe estar listo para E5 y los cuatro servicios para E6.
- E4 y E5 pueden desarrollarse en paralelo con más de una persona; en ejecución individual se hacen en ese orden.
- E9 solo comienza con alcance, imágenes y `holdout` congelados.

## 7. Estrategia global de pruebas

| Nivel | Objetivo | Dependencias reales | Ejecución |
| --- | --- | --- | --- |
| Unit | Validar reglas, modelos, ranking, filtros, validadores, métricas y errores. | Ninguna | En cada tarea y en CI. |
| Component | Validar router y agentes mediante puertos fake. | Ninguna | En cada sprint funcional. |
| Contract | Validar OpenAI Gateway, TMDB, Meilisearch CE, PostgreSQL, dataset y trace schema. | Payloads/fixtures; red opcional separada | Antes de integración y bajo comando explícito. |
| Integration | Validar FastAPI, SSE, Meilisearch, trace store y migraciones. | Contenedores efímeros o servicios simulados | Sprints 4–5 y CI. |
| Compose smoke | Validar imágenes, redes, healthchecks, volúmenes y bootstrap. | Cuatro contenedores locales | Sprint 5 y aceptación. |
| Evaluation | Medir comportamiento desde trazas sobre Silver. | Meilisearch CE local; LLM real solo en ejecución declarada | `dev/test` durante desarrollo y `holdout` al cierre. |
| Manual UX | Validar utilidad, claridad, diversidad, streaming y mensajes. | Entorno local; APIs reales opcionales | Reviews de sprints 3 a 6. |

Reglas de la suite:

- Semilla fija para operaciones aleatorias controlables.
- Temperatura baja o cero en evaluaciones cuando el modelo lo permita.
- Unit tests sin red y sin consumo de API.
- Tests online separados por marcador y nunca ejecutados por defecto.
- Fixtures pequeñas; datasets, índice Meilisearch y schema PostgreSQL se gestionan como artefactos reproducibles.
- Tests de contenedor se separan de unit tests y pueden ejecutarse con un marker específico.
- Todo bug corregido debe incorporar un test de regresión en el nivel más bajo capaz de reproducirlo.

## 8. Métricas y gates de producto

| Dimensión | Métrica | Umbral de aceptación MVP |
| --- | --- | ---: |
| Routing | Accuracy global | ≥90 % |
| Routing | Accuracy por clase | ≥80 % |
| Routing | Unnecessary tool call rate | 0 % en `clarification`/`out_of_scope` |
| Tool calls | Endpoint TMDB permitido | 100 % |
| Tool calls | Request schema y parámetros críticos | 100 % válidos |
| Retrieval Netflix | Recall@5 | Objetivo ≥0,80 |
| Retrieval Netflix | Precision@5 | Objetivo ≥0,60 |
| Retrieval Netflix | nDCG@5 | Reportado y versionado |
| Retrieval Netflix | Hybrid uplift frente al mejor baseline puro | Reportado; objetivo >0 |
| Ingeniería | Unit/contract/build tests de licencia Meilisearch CE/MIT | 100 % passing; fuera del Silver Dataset |
| Filtros | Cumplimiento de restricciones obligatorias | 100 % |
| Grounding | Títulos no presentes en evidencia | 0 % |
| Seguridad | Errores conocidos convertidos en respuesta segura | 100 % de casos definidos |
| Trazabilidad | Runs con traza completa en evaluación | 100 % |
| Trazabilidad | Métricas auditables hasta run/caso | 100 % |
| Rendimiento | Routing p95 | <2 s |
| Rendimiento | Retrieval local p95 | <1 s |
| UX | Primer evento SSE con fakes | <500 ms |
| UX | Primer contenido en condiciones normales | <5 s, excluyendo indisponibilidad de terceros |
| Calidad | Unit/integration tests obligatorios | 100 % passing |
| Operación | Servicios Compose saludables | 4 de 4 |

Los umbrales de retrieval se consideran objetivos de calidad y no una razón para falsear etiquetas silver. Si no se alcanzan en una semana, se entrega el resultado medido, el análisis causal y el siguiente experimento recomendado.

## 9. Matriz de trazabilidad

| Requisito del assessment/briefing | Epics responsables | Evidencia esperada |
| --- | --- | --- |
| Dos agentes especializados | E4, E5 | Tests de componente e integración. |
| Routing por contenido | E3 | Métricas y matriz de confusión. |
| Solo endpoint trending de TMDB | E0, E4 | Snapshot/contrato temprano y test de contrato de URL y cliente. |
| RAG con dataset Netflix | E0, E5, E8 | Dataset adquirido y perfilado, índice Meilisearch CE, ingesta, métricas y respuestas grounded. |
| Streaming | E6 | Tests de secuencia SSE y demo. |
| UX simple y mínimo setup | E6, E8, E9 | UI mínima y Compose ejecutado desde limpio. |
| Ocultar errores | E4, E6 | Fault injection y mensajes públicos seguros. |
| Código modular y mantenible | E2 | Puertos, modelos tipados y estructura. |
| Entorno reproducible | E2, E8, E9 | Cuatro imágenes, `.env.example`, Compose smoke test. |
| Tests automatizados/end-to-end | E2, E6, E8, E9 | Pytest, contract, Compose smoke y comandos documentados. |
| Dataset de evaluación por componentes | E1 | Tres suites, fixtures, schema, dataset card y baseline. |
| Trazas por ejecución | E7 | Runs/spans/eventos persistidos y exportables. |
| Bases separadas | E5, E7, E8 | Meilisearch CE y PostgreSQL en volúmenes/contenedores distintos. |
| Stack MIT sin Enterprise | E0, E2, E5, E8, E9 | Smoke test temprano, versión/image digest, SBOM y contract tests de licencia. |
| Informe de enfoque, retos y resultados | E9 | Informe Markdown/PDF. |
| Decisiones, herramientas y modelos | E0, E9 | ADR y secciones de diseño/metodología. |
| Siguientes pasos/productización | E9 | Backlog futuro priorizado. |

## 10. Riesgos y mitigaciones

| Riesgo | Probabilidad/impacto | Mitigación | Señal temprana |
| --- | --- | --- | --- |
| Gateway incompatible con cliente OpenAI | Media/Alta | Spike de configuración, puerto LLM y fake desde Sprint 1. | Primera llamada no devuelve salida estructurada. |
| Etiquetas silver ruidosas | Alta/Media | Especificación latente, reglas, crítico independiente y warnings; no presentarlo como Gold. | Muchos rechazos o baja confianza del crítico. |
| Sobreajuste al silver dataset | Media/Alta | Split por familias y holdout bloqueado. | Mejora en `dev` sin mejora en `test`. |
| Alucinación de títulos | Media/Alta | Allow-list de candidatos y fallback determinista. | Validador rechaza títulos con frecuencia. |
| Dataset o índice no reproducible | Media/Alta | Adquisición e inspección temprana, fingerprint, settings, volumen y comando idempotente. | El fichero no puede recuperarse, cambia el schema o produce índices distintos con la misma entrada. |
| Baja relevancia semántica | Media/Media | Filtros, reranking, evaluación por segmentos. | Recall@5 bajo en géneros concretos. |
| Fallo o rate limit de TMDB | Media/Media | Spike temprano del endpoint, timeout, caché TTL, errores tipados y fallback. | El endpoint, credencial o payload no coincide con el contrato esperado; aumento de 429 o latencia externa. |
| Plazo insuficiente | Alta/Alta | Reestimación a 52 h y corte P0 de 40 h; los spikes tempranos permanecen en P0. | Desviación >20 % al cerrar Sprint 1. |
| Secretos en logs/trazas/repositorio | Baja/Alta | Redacción central, capture mode y escaneo de imágenes/exportaciones. | Test de sanitización falla. |
| Streaming frágil | Media/Media | Modelo explícito de eventos y tests de desconexión/fallo. | Streams sin `done` o tareas huérfanas. |
| Trace DB afecta al usuario | Media/Alta | Fail-open en runtime, fail-closed en evaluación y persistencia asíncrona acotada. | Latencia o errores de escritura crecientes. |
| Volúmenes Docker inconsistentes | Media/Media | Migraciones, fingerprints, healthchecks y bootstrap idempotente. | Backend ready con schema/collection obsoleta. |
| Complejidad operativa excesiva | Media/Media | Exactamente cuatro servicios; sin Collector/dashboard en MVP. | Se proponen nuevos contenedores antes de cerrar P0. |
| Activación accidental de Enterprise | Baja/Alta | Imagen CE fijada, SBOM, allow-list de parámetros y test de licencia. | Aparece feature BUSL, `useNetwork` o requisito de licencia. |

## 11. Priorización y política de recorte

### 11.1 Obligatorio — P0

- Tres suites Silver, schema, generador GPT, fixtures, validadores y baseline trazable.
- Spikes tempranos de TMDB, adquisición/perfilado del dataset Netflix y smoke test de Meilisearch CE.
- Routing de cuatro rutas.
- Cliente TMDB limitado, ranking y grounding.
- Ingesta, Meilisearch CE, hybrid retrieval y grounding Netflix.
- FastAPI con SSE y errores seguros.
- Generación, almacenamiento, consulta y exportación de trazas.
- Cuatro servicios Docker (`frontend`, `backend`, `netflix-db`, `trace-db`) y Compose reproducible.
- Meilisearch Community Edition/MIT con contract tests que bloquean funcionalidades Enterprise.
- Tests sin red, integration/Compose smoke, README, configuración y reporte.

**Corte P0 para 40 horas:** conservar los spikes tempranos de fuentes y mantener las tres suites con un mínimo de 180 casos —80 E2E, 40 TMDB y 60 Netflix—, cubrir todas las familias críticas y ejecutar una repetición por caso. La ampliación hasta 250–350 casos queda para P1. No se elimina ninguna suite, fixture crítico, traza, contenedor ni verificación temprana de acceso/contrato.

### 11.2 Importante — P1

- Interfaz web mínima.
- Caché TMDB stale-on-error.
- Reranking avanzado y métricas por segmento.
- Ampliación del Silver Dataset hasta 250–350 casos.
- Ejecuciones repetidas para métricas de estabilidad.
- Evaluador semántico/modelo crítico sobre el 100 % de casos; en P0 puede aplicarse a warnings y muestra de riesgo.

### 11.3 Opcional — P2

- Búsqueda híbrida semántica/léxica.
- CLI alternativa.
- Dashboard visual, OpenTelemetry Collector, Jaeger o Grafana.
- Evaluación LLM-as-judge adicional; nunca sustituirá métricas deterministas.

Si un sprint supera su capacidad en más del 20 %, se elimina primero P2 y después P1. No se recortan grounding, tests críticos, manejo seguro de errores, captura/persistencia mínima de trazas, los cuatro servicios ni documentación end-to-end.

## 12. Resultado esperado por sprint

| Sprint | Demo al cierre | Artefactos |
| --- | --- | --- |
| 0 | Revisión del alcance y del backlog. | Este plan, decisiones, riesgos y trazabilidad inicial. |
| 0 | Alcance revisado y viabilidad de fuentes demostrada sin construir aún los agentes. | Este plan, decisiones, snapshot TMDB sanitizado, perfil/fingerprint del dataset Netflix, evidencia de licencia y smoke test de Meilisearch CE. |
| 2 | Consultas silver se enrutan y generan trazas conformes al contrato. | Core, router, trace schema, topología Compose y métricas. |
| 3 | Consulta trending devuelve solo títulos del payload TMDB simulado. | Cliente, caché, ranking, grounded response y fallbacks. |
| 4 | Consulta temática recupera y recomienda desde Meilisearch CE. | Ingesta, índice híbrido, filtros, retrieval, respuesta RAG y métricas comparativas. |
| 5 | Los cuatro contenedores sirven chat y trazas persistentes. | FastAPI, SSE, UI, PostgreSQL, Compose, exportación e integración. |
| 6 | Evaluador reproduce stack y evaluación holdout auditable. | README, ADR, informe, diagrama, trazas, resultados e imágenes/Compose. |

## 13. Criterio de finalización del proyecto

El proyecto está terminado cuando:

1. `docker compose up --build` levanta exactamente cuatro servicios saludables en un entorno limpio.
2. El dataset Netflix puede configurarse/cargarse en Meilisearch CE con un comando idempotente documentado.
3. El router alcanza el gate acordado y no activa APIs para aclaración o fuera de alcance.
4. El agente trending solo usa el endpoint autorizado y nunca recomienda fuera de su payload.
5. El agente Netflix recupera desde Meilisearch CE mediante hybrid search y nunca recomienda fuera de su contexto.
6. La API entrega contenido y errores de forma progresiva y segura.
7. Cada ejecución produce una traza persistente, sanitizada, consultable y asociable a métricas.
8. Las suites offline pasan sin claves ni red; integración/Compose usa servicios locales.
9. `silver_v1/holdout` se evalúa una vez al cierre y sus resultados quedan reportados sin maquillaje.
10. Meilisearch y PostgreSQL conservan datos tras restart y pueden reconstruirse/exportarse.
11. La edición de Meilisearch es Community/MIT y ninguna configuración, llamada o imagen depende de Enterprise/BUSL.
12. No hay secretos ni artefactos temporales o volúmenes en la entrega.
13. El informe explica enfoque, decisiones, dificultades, resultados, limitaciones y evolución a producción.

## 14. Preguntas no bloqueantes para una futura revisión

La información actual es suficiente para iniciar el desarrollo. Estas cuestiones pueden confirmarse durante Sprint 0 sin bloquear el plan:

1. URL exacta y compatibilidad del API Gateway con el cliente oficial de OpenAI.
2. Modelos habilitados para chat y embeddings, límites de tokens y rate limits.
3. Disponibilidad y condiciones de redistribución del dataset Netflix y de artefactos derivados.
4. Preferencia final entre entrega ZIP o repositorio privado.
5. Presupuesto máximo de horas y llamadas GPT; determina si se entrega P0 de 180 casos o la meta de 250–350.
6. Política deseada para conservar consultas reales en trazas; por defecto se almacenarán redactadas o hasheadas fuera de evaluación sintética.

Hasta recibir respuesta, se aplican abstracciones configurables, tests offline y las decisiones conservadoras descritas en este documento.

## 15. Referencias técnicas de la decisión

- [Docker Compose](https://docs.docker.com/compose/) y [modelo de servicios](https://docs.docker.com/compose/intro/compose-application-model/).
- [Meilisearch Community y Enterprise editions](https://www.meilisearch.com/docs/resources/self_hosting/enterprise_edition).
- [Meilisearch hybrid search](https://www.meilisearch.com/docs/capabilities/hybrid_search/advanced/semantic_vs_hybrid) y [filtros](https://www.meilisearch.com/docs/capabilities/filtering_sorting_faceting/overview).
- [Licencia MIT de Meilisearch CE](https://github.com/meilisearch/meilisearch/blob/main/LICENSE-MIT) y [frontera BUSL de Enterprise](https://github.com/meilisearch/meilisearch/blob/main/LICENSE-EE).
- [PostgreSQL JSON/JSONB e indexación](https://www.postgresql.org/docs/current/datatype-json.html).
- [OpenTelemetry Tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/) para el contrato conceptual de trace/span/event.
