# 1. Resumen

El proyecto consiste en desarrollar un prototipo de chatbot de recomendación de películas y series que utilice dos agentes especializados y seleccione automáticamente el agente apropiado según la intención de la consulta.

El sistema combinará:

* Información actual de películas en tendencia obtenida mediante TMDB.
* Recuperación semántica sobre un dataset estático de títulos de Netflix.
* Generación de respuestas mediante modelos de lenguaje.
* Streaming de respuestas.
* Manejo seguro de errores.
* Una arquitectura modular, comprobable y reproducible.

# 2. Objetivo

Construir un sistema conversacional que pueda proporcionar recomendaciones relevantes, explicables y fundamentadas en datos externos, demostrando capacidades de:

* Routing de consultas.
* Uso de herramientas.
* Retrieval-Augmented Generation.
* Generación grounded.
* Integración con APIs.
* Ingeniería de software aplicada a sistemas LLM.

# 3. Usuarios objetivo

El prototipo está dirigido a una persona que desea obtener recomendaciones audiovisuales mediante lenguaje natural.

Los principales casos de uso son:

1. Encontrar películas que sean tendencia actualmente.
2. Encontrar películas o series similares a una temática, género o preferencia dentro del dataset de Netflix.
3. Obtener varias alternativas acompañadas de una explicación breve.
4. Recibir una respuesta segura cuando no existan resultados o una fuente externa no esté disponible.

# 4. Alcance funcional

## 4.1 Router

El sistema analizará cada consulta y la clasificará en una de las siguientes rutas:

* `trending`
* `netflix`
* `clarification`
* `out_of_scope`

El router devolverá una clasificación estructurada que incluya:

* Ruta elegida.
* Confianza.
* Restricciones detectadas.
* Motivo resumido de la selección.

Las consultas sobre actualidad, tendencias o estrenos recientes se dirigirán al Trending Movie Agent.

Las consultas sobre géneros, temáticas, documentales, películas o series del catálogo se dirigirán al Netflix RAG Agent.

Cuando una consulta mezcle requisitos incompatibles o tenga una intención insuficientemente clara, el chatbot solicitará una aclaración breve.

## 4.2 Trending Movie Agent

El agente consultará exclusivamente el endpoint permitido de películas en tendencia de TMDB.

Responsabilidades:

* Seleccionar una ventana diaria o semanal.
* Interpretar géneros, temas y preferencias expresadas por el usuario.
* Filtrar y ordenar los resultados recibidos.
* Evitar recomendar títulos que no estén presentes en la respuesta de TMDB.
* Generar una recomendación explicando su relación con la consulta.
* Informar cuando no exista una coincidencia fiable.

El agente no consultará endpoints adicionales de TMDB.

## 4.3 Netflix RAG Agent

El agente utilizará el dataset de Netflix como fuente de conocimiento y Meilisearch Community Edition como motor de búsqueda híbrida.

Responsabilidades:

* Preprocesar e indexar los títulos como documentos de Meilisearch.
* Crear embeddings configurables a partir del título, descripción, géneros y metadatos relevantes.
* Combinar búsqueda léxica y vectorial mediante hybrid search.
* Aplicar filtros estructurados por tipo, género, año u otras restricciones.
* Aprovechar coincidencias exactas, proximidad, prefijos y tolerancia a errores de escritura.
* Recuperar los elementos más relevantes combinando señales léxicas y semánticas.
* Reordenar resultados utilizando señales de similitud y calidad.
* Generar una respuesta basada exclusivamente en los títulos recuperados.
* Indicar que el dataset representa un snapshot histórico y no garantiza disponibilidad actual.

## 4.4 Respuestas

Cada respuesta exitosa incluirá:

* Entre una y tres recomendaciones principales.
* Título.
* Año, cuando esté disponible.
* Tipo de contenido.
* Explicación breve de la recomendación.
* Señal de procedencia: TMDB Trending o Netflix Dataset.
* Aviso de limitación cuando sea aplicable.

Las respuestas evitarán afirmar información no presente en las fuentes recuperadas.

## 4.5 Streaming

El contenido generado se enviará progresivamente al usuario.

El streaming deberá funcionar tanto para respuestas correctas como para mensajes controlados de error.

Los procesos previos a la generación podrán emitir estados breves como:

* “Analizando tu consulta”.
* “Consultando tendencias”.
* “Buscando en el catálogo”.

Estos mensajes no expondrán razonamiento interno del modelo.

## 4.6 Gestión de errores

El sistema manejará al menos:

* Credenciales ausentes.
* Timeout de TMDB.
* Error del API Gateway.
* Dataset ausente o inválido.
* Índice de Meilisearch ausente, desactualizado o no disponible.
* Respuesta vacía.
* Consulta fuera de alcance.
* Fallo durante el streaming.

Los errores técnicos se registrarán internamente y se traducirán a mensajes seguros para el usuario.

# 5. Requisitos no funcionales

## 5.1 Mantenibilidad

* Arquitectura modular.
* Interfaces claras entre componentes.
* Tipado de funciones públicas.
* Modelos Pydantic para entradas y salidas.
* Configuración mediante variables de entorno.
* Ausencia de secretos dentro del repositorio.
* Bajo acoplamiento con el proveedor LLM.

## 5.2 Reproducibilidad

El proyecto deberá ejecutarse en un entorno limpio utilizando uno de estos mecanismos:

* Gestor de dependencias y comando de instalación documentado.
* Docker y Docker Compose.
* Script o comando idempotente para configurar e ingerir el índice de Meilisearch.

El repositorio incluirá un archivo `.env.example`.

## 5.3 Rendimiento

Objetivos iniciales:

* Routing inferior a 2 segundos en condiciones normales.
* Inicio del streaming de la respuesta en menos de 5 segundos, excluyendo indisponibilidad de terceros.
* Recuperación local inferior a 1 segundo para el corpus completo.
* Timeout explícito para todas las llamadas externas.
* Caché temporal de resultados de TMDB.

Estos objetivos son orientativos y se medirán durante la evaluación.

## 5.4 Observabilidad

Cada petición tendrá un identificador de correlación.

Se registrarán:

* Ruta seleccionada.
* Duración del routing.
* Duración de retrieval.
* Número de documentos recuperados.
* Agente utilizado.
* Errores de servicios externos.
* Latencia hasta el primer token.
* Duración total.

No se registrarán claves ni información sensible.

Las trazas estructuradas se persistirán en `trace-db` y permitirán reconstruir routing, llamada a herramienta, configuración de hybrid search, resultados recuperados, generación, streaming, errores, tokens, coste y latencias.

## 5.5 Arquitectura de servicios y licencias

El sistema se ejecutará mediante Docker Compose con cuatro servicios runtime:

1. `frontend`.
2. `backend`.
3. `netflix-db`, basado en Meilisearch Community Edition.
4. `trace-db`, basado en PostgreSQL.

Meilisearch se utilizará exclusivamente en su Community Edition, distribuida bajo licencia MIT. No se habilitarán ni dependerá el MVP de módulos Enterprise Edition sujetos a BUSL o licencia comercial.

Quedan expresamente excluidos del stack:

* Sharding o replicación Enterprise de Meilisearch.
* Búsqueda distribuida mediante network/remotes.
* Analytics, personalización, seguridad avanzada u observabilidad exclusivas de Enterprise o Cloud.
* Cualquier feature que requiera una clave/licencia Enterprise.

La versión e imagen Community Edition deberán fijarse y verificarse durante el build. Un cambio de versión exigirá revisar de nuevo licencia y funcionalidades habilitadas.

# 6. Requisitos técnicos

* Python 3.11 o superior.
* FastAPI como capa HTTP.
* Server-Sent Events para streaming.
* Cliente OpenAI compatible con el API Gateway proporcionado.
* HTTPX para TMDB.
* Pydantic para modelos y configuración.
* Pytest para tests.
* Meilisearch Community Edition self-hosted como motor local de búsqueda léxica, vectorial e híbrida.
* Embeddings configurables.
* Caché local sencilla para TMDB.
* PostgreSQL para trazas de ejecución y resultados de evaluación.
* Docker Compose con cuatro servicios runtime.

La aplicación deberá permitir configurar:

* `OPENAI_API_KEY`
* `OPENAI_BASE_URL`
* `OPENAI_MODEL`
* `OPENAI_EMBEDDING_MODEL`
* `TMDB_API_KEY`
* `NETFLIX_DATASET_PATH`
* `MEILISEARCH_URL`
* `MEILISEARCH_API_KEY`
* `MEILI_MASTER_KEY`
* `MEILISEARCH_INDEX_UID`
* `MEILISEARCH_EMBEDDER`
* `MEILISEARCH_SEMANTIC_RATIO`
* `TRACE_DATABASE_URL`
* `LOG_LEVEL`

# 7. Limitaciones

1. El Trending Movie Agent se limita a un único endpoint de TMDB.
2. Una película en tendencia no es necesariamente una película recientemente estrenada.
3. La métrica de “mejor película” debe definirse mediante una heurística documentada.
4. El dataset de Netflix representa un snapshot histórico y regional.
5. El prototipo no garantiza disponibilidad actual por país.
6. No se utilizan datos de comportamiento del usuario.
7. No existe personalización basada en historial.
8. La calidad semántica depende del modelo de embeddings.
9. Los resultados del LLM pueden variar entre ejecuciones.
10. La disponibilidad del sistema depende parcialmente de APIs externas.
11. El MVP depende de las capacidades disponibles en Meilisearch Community Edition; no se asumirá ninguna función Enterprise.
12. El equilibrio léxico/semántico deberá calibrarse con el Silver Dataset y puede variar por tipo de consulta.

# 8. Fuera de alcance

Quedan fuera del MVP:

* Inicio de sesión.
* Perfiles de usuario.
* Historial persistente de recomendaciones.
* Collaborative filtering.
* Fine-tuning.
* Búsqueda en otros servicios de streaming.
* Información de precios o disponibilidad regional en tiempo real.
* Compra o reproducción de contenido.
* Panel de administración.
* Aplicación móvil.
* Infraestructura distribuida y sharding/replicación de Meilisearch.
* Escalado horizontal.
* Despliegue productivo completo.

# 9. MVP

El MVP se considerará completado cuando:

1. La aplicación pueda instalarse siguiendo el README.
2. El dataset pueda configurarse e indexarse en Meilisearch Community Edition mediante un comando documentado.
3. El router seleccione correctamente entre los dos agentes.
4. El Trending Agent consulte el endpoint permitido.
5. El Netflix Agent recupere títulos mediante búsqueda híbrida léxica y semántica.
6. Las respuestas se transmitan en streaming.
7. Los errores externos produzcan mensajes seguros.
8. Existan tests automatizados de los componentes críticos.
9. Exista un conjunto mínimo de evaluación.
10. El repositorio incluya documentación técnica y funcional.
11. Los cuatro servicios Docker puedan levantarse mediante Compose.
12. El stack no incluya ni active funcionalidades Enterprise de Meilisearch.
13. Cada ejecución genere una traza persistente y correlacionada en PostgreSQL.

El MVP utilizará una interfaz web mínima y una API REST.

# 10. Caso ideal

La versión ideal añadirá:

* Routing híbrido con confianza y aclaraciones.
* Calibración avanzada y adaptativa del peso léxico/semántico.
* Filtros de metadatos avanzados.
* Re-ranking de candidatos.
* Métricas de retrieval.
* Evaluación de groundedness.
* Caché de TMDB.
* Dashboard visual, alertas y análisis avanzado de trazas.
* Test de fallos y timeouts.
* OpenTelemetry Collector y dashboard de observabilidad.
* CLI alternativa.
* Pequeña interfaz web usable.
* Evidencias de la fuente en las respuestas.
* Métricas de latencia y coste.
* Pipeline de integración continua.

# 11. Criterios de aceptación

## Routing

* Al menos el 90 % de las consultas del conjunto de evaluación se envían al agente esperado.
* Las consultas fuera de alcance no activan APIs innecesarias.
* Las consultas ambiguas reciben una aclaración.

## Trending Agent

* Utiliza solamente el endpoint autorizado.
* No genera títulos ausentes en los resultados obtenidos.
* Diferencia entre tendencia y fecha de estreno.
* Maneja respuestas vacías y errores.

## Netflix RAG Agent

* Recupera títulos relevantes para género, temática y tipo de contenido.
* Combina recuperación léxica y semántica mediante Meilisearch Community Edition.
* Respeta el `semanticRatio`, embedder, filtros y límite configurados.
* No recomienda elementos ajenos a los documentos recuperados.
* Indica la antigüedad del dataset.
* Proporciona un fallback cuando la similitud es baja.

## Experiencia de usuario

* La respuesta se muestra progresivamente.
* No aparecen stack traces.
* La aplicación requiere pocos pasos de configuración.
* Los mensajes de error indican una acción razonable.

## Ingeniería

* Los tests pueden ejecutarse sin consumir APIs reales.
* El código está organizado por responsabilidades.
* La configuración no está acoplada al código.
* El repositorio puede ejecutarse en un entorno limpio.
* La imagen de `netflix-db` corresponde a Meilisearch Community Edition/MIT y no activa módulos Enterprise.
* Unit tests de los builders y schemas de Meilisearch impiden serializar parámetros Enterprise; esta comprobación no pertenece al Silver Dataset.

# 12. Estrategia de evaluación

Se preparará un dataset de evaluación con cuatro grupos:

1. Consultas de tendencias.
2. Consultas de Netflix.
3. Consultas ambiguas.
4. Consultas fuera de alcance.

Métricas propuestas:

* Exactitud de routing.
* Recall@k del retrieval.
* Precision@k del retrieval.
* nDCG@k del retrieval.
* Uplift de hybrid search frente a baselines léxico y semántico.
* Coincidencia de filtros.
* Groundedness de la respuesta.
* Tasa de títulos inventados.
* Latencia hasta el primer token.
* Latencia total.
* Tasa de errores controlados.

Se incluirán pruebas manuales para evaluar utilidad, claridad y diversidad de recomendaciones.

# 13. Entregables

* Código fuente.
* README principal.
* `.env.example`.
* Archivo de dependencias.
* Script de ingestión e indexación.
* `compose.yaml` y definición de los cuatro servicios.
* Evidencia de versión/licencia MIT de Meilisearch Community Edition.
* Aplicación ejecutable.
* Tests.
* Dataset de evaluación.
* Resultados de evaluación.
* Informe de decisiones, dificultades y resultados.
* Diagrama de arquitectura.
* Sección de limitaciones y evolución a producción.

# 14. Riesgos

| Riesgo                       | Mitigación                                  |
| ---------------------------- | ------------------------------------------- |
| Clasificación incorrecta     | Routing híbrido y conjunto de evaluación    |
| Recomendaciones alucinadas   | Respuesta limitada a candidatos recuperados |
| Dataset desactualizado       | Disclaimer visible                          |
| Fallos de TMDB               | Timeout, retry, caché y mensaje alternativo |
| Incompatibilidad del gateway | Cliente configurable y prueba inicial       |
| Índice difícil de reproducir | Configuración e ingesta idempotente en Meilisearch CE |
| Exceso de complejidad        | Congelar alcance del MVP                    |
| Baja relevancia semántica    | Metadata filtering y reranking              |
| Tests dependientes de red    | Mocks y fixtures                            |
| Uso accidental de Enterprise | Versión fijada, checklist de licencia y tests que prohíben features EE |
| Hybrid search mal calibrado  | Baselines léxico/vectorial y ajuste con Silver Dataset |

# 15. Supuestos

1. La frase relativa a los dos agentes se interpreta como selección de un agente por consulta.
2. El API Gateway es compatible con el cliente oficial o proporciona una interfaz equivalente.
3. Se dispone de las credenciales necesarias.
4. El dataset puede distribuirse o descargarse siguiendo sus condiciones.
5. Se permite crear artefactos derivados, como embeddings e índices.
6. El chatbot puede responder en el idioma de la consulta.
7. No se requiere despliegue público.
8. La prioridad es demostrar ingeniería y criterio, no construir una interfaz avanzada.
9. Meilisearch Community Edition cubre full-text, AI-powered/hybrid search y filtros necesarios sin módulos Enterprise.
10. Toda actualización de Meilisearch mantendrá licencia MIT y se someterá a revisión de licencia.
