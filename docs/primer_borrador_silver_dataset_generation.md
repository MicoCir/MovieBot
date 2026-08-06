# Epic Brief — Silver Evaluation Dataset

**Proyecto:** Agentic Movie Recommendation Chatbot
**Épica:** Generación de dataset sintético de evaluación
**Versión:** 0.1
**Estado:** Draft
**Nombre interno:** Silver Dataset

---

## 1. Contexto

El sistema que se va a evaluar es un chatbot de recomendación audiovisual compuesto por:

1. Un router encargado de interpretar la consulta.
2. Un agente especializado en películas actualmente en tendencia mediante TMDB.
3. Un agente especializado en películas y series del dataset de Netflix mediante RAG.
4. Una capa de generación encargada de transformar los resultados de las herramientas en una respuesta útil y fundamentada.

El agente Netflix utilizará Meilisearch para combinar búsqueda léxica y vectorial. El Silver Dataset evaluará la calidad y corrección funcional de esa combinación.

La evaluación no debe limitarse a comprobar la respuesta final. Debe permitir aislar y medir las principales decisiones tomadas durante la ejecución:

* Selección de la ruta correcta.
* Decisión de utilizar o no una herramienta.
* Generación correcta de los argumentos de la herramienta.
* Recuperación o selección de información relevante.
* Procesamiento correcto del output de la herramienta.
* Generación de una respuesta grounded.
* Manejo de consultas ambiguas, fuera de alcance o sin resultados.

---

## 2. Objetivo de la épica

Diseñar y generar un dataset completamente sintético que cubra las situaciones representativas a las que se enfrentará el agente y permita evaluar su comportamiento de manera reproducible.

Este dataset se denominará **Silver Dataset**.

El Silver Dataset será generado y validado mediante procesos automáticos, pero no será revisado exhaustivamente por expertos humanos.

En una fase posterior, una revisión humana permitirá:

* Corregir etiquetas.
* Eliminar casos artificiales o poco realistas.
* Añadir matices no contemplados en la generación.
* Revisar expectativas de respuesta.
* Resolver casos controvertidos.

El resultado de ese proceso constituiría el futuro **Gold Dataset**.

La presente prueba se limitará a la creación, validación y uso del Silver Dataset.

---

## 3. Objetivos específicos

El dataset deberá permitir evaluar separadamente:

### 3.1 Routing end-to-end

Comprobar que el sistema distingue correctamente entre:

* Consultas sobre tendencias actuales.
* Consultas sobre contenido del dataset de Netflix.
* Consultas fuera del alcance del sistema.
* Consultas que requieren aclaración.
* Consultas válidas pero con restricciones complejas.
* Consultas que contienen señales contradictorias.

### 3.2 Generación de llamadas a TMDB

Comprobar que el agente especializado:

* Utiliza la herramienta correcta.
* Utiliza exclusivamente el endpoint permitido.
* Selecciona correctamente la ventana diaria o semanal.
* Extrae las restricciones de la consulta.
* No genera parámetros no soportados.
* No realiza llamadas innecesarias.

### 3.3 Procesamiento de resultados de TMDB

Comprobar que el agente:

* Selecciona títulos presentes en el output de TMDB.
* Diferencia entre popularidad, tendencia, calidad y fecha de estreno.
* Aplica correctamente las preferencias del usuario.
* No inventa títulos ni atributos.
* Responde adecuadamente cuando no existe una coincidencia clara.
* Explica la recomendación utilizando únicamente datos disponibles.

### 3.4 Generación de consultas para Netflix Hybrid RAG

Comprobar que el agente:

* Produce una consulta textual/semántica adecuada.
* Extrae correctamente filtros estructurados.
* Selecciona un modo léxico, semántico o híbrido coherente con el escenario.
* Utiliza un `semanticRatio` dentro del rango permitido y un embedder configurado.
* Distingue películas de series.
* Identifica géneros, temáticas y restricciones temporales.
* Elimina elementos conversacionales irrelevantes.
* Conserva los elementos semánticos importantes.
* No introduce restricciones que el usuario no ha solicitado.

### 3.5 Procesamiento de resultados del Netflix RAG

Comprobar que el agente:

* Selecciona documentos relevantes.
* Respeta los filtros solicitados.
* Recomienda únicamente títulos recuperados.
* Utiliza correctamente descripción, género, año y puntuaciones.
* No afirma que el contenido continúa disponible actualmente.
* Explica la relación entre la consulta y cada recomendación.
* Maneja correctamente resultados insuficientes o contradictorios.
* Aprovecha coincidencias exactas, typos y conceptos semánticos cuando corresponda.

---

## 4. Principios de diseño

### 4.1 Evaluar componentes y no solamente respuestas

Una respuesta final correcta puede ocultar una ejecución incorrecta.

Por ejemplo, el sistema podría recomendar una película adecuada después de:

* Elegir el agente incorrecto.
* Generar una consulta defectuosa.
* Ignorar el resultado de una herramienta.
* Recuperar documentos irrelevantes.
* Inventar parte de la información.

Por ello, la evaluación deberá capturar y analizar la traza de ejecución.

### 4.2 Separar ruta, herramienta y acción

Se utilizarán tres conceptos distintos:

#### `expected_route`

Clasificación funcional de la consulta:

* `TMDB_TRENDING`
* `NETFLIX_RAG`
* `OUT_OF_SCOPE`
* `NEEDS_CLARIFICATION`

#### `expected_tool`

Herramienta que debería ejecutarse:

* `TMDB_TRENDING`
* `NETFLIX_SEARCH`
* `NONE`

#### `expected_action`

Comportamiento que debería realizar el sistema:

* `CALL_TOOL`
* `ASK_CLARIFYING_QUESTION`
* `RETURN_OUT_OF_SCOPE`
* `ANSWER_FROM_TOOL_OUTPUT`
* `RETURN_NO_RESULTS`
* `RETURN_CONTROLLED_ERROR`

Esta separación evita utilizar valores como `OUT_OF_SCOPE` o `NEEDS_CLARIFICATION` como si fueran herramientas.

### 4.3 Priorizar expectativas estructuradas

No se evaluará la respuesta comparándola con un único texto exacto.

Cada caso contendrá expectativas estructuradas como:

* Ruta correcta.
* Herramienta correcta.
* Parámetros esperados.
* Restricciones que deben respetarse.
* Títulos permitidos.
* Títulos no permitidos.
* Datos que deben mencionarse.
* Afirmaciones prohibidas.
* Tipo de respuesta esperado.

Esto permitirá aceptar diferentes redacciones correctas.

### 4.4 Usar outputs de herramientas deterministas

Las evaluaciones no dependerán directamente de los resultados actuales de TMDB ni de un índice Meilisearch variable.

Los casos contendrán fixtures o snapshots controlados de los outputs de las herramientas.

Esto permitirá:

* Repetir las evaluaciones.
* Evitar que cambien los resultados con el tiempo.
* Simular errores.
* Crear escenarios límite.
* Aislar el procesamiento de resultados de la recuperación.

### 4.5 Evitar que el modelo genere su propia respuesta correcta

Las expectativas deberán derivarse de una especificación estructurada del escenario, no de la respuesta redactada por el mismo modelo que genera la consulta.

El orden recomendado será:

1. Generar una especificación estructurada.
2. Derivar las etiquetas esperadas.
3. Generar la consulta a partir de la especificación.
4. Validar que la consulta representa la especificación.
5. Generar o seleccionar el fixture de la herramienta.
6. Derivar las expectativas de procesamiento.

---

# 5. Organización de los datasets

Se crearán tres suites principales.

## 5.1 Dataset de routing y evaluación end-to-end

Nombre propuesto:

`e2e_routing_silver.jsonl`

Evaluará el comportamiento completo desde la consulta hasta la respuesta.

## 5.2 Dataset del agente TMDB

Nombre propuesto:

`tmdb_agent_silver.jsonl`

Evaluará:

* Generación de la llamada a la herramienta.
* Interpretación de sus resultados.
* Selección de recomendaciones.
* Grounding de la respuesta.

## 5.3 Dataset del agente Netflix RAG

Nombre propuesto:

`netflix_agent_silver.jsonl`

Evaluará:

* Generación de la consulta de retrieval.
* Extracción de filtros.
* Relevancia de los documentos recuperados.
* Procesamiento del output.
* Grounding de la respuesta.

Los outputs simulados de herramientas podrán almacenarse en archivos separados:

```text
fixtures/
├── tmdb/
│   ├── tmdb_001.json
│   ├── tmdb_002.json
│   └── ...
└── netflix/
    ├── netflix_001.json
    ├── netflix_002.json
    └── ...
```

---

# 6. Esquema común de los casos

Todos los datasets compartirán un conjunto base de campos.

## 6.1 Identificación y organización

| Campo             | Tipo         | Descripción                           |
| ----------------- | ------------ | ------------------------------------- |
| `case_id`         | string       | Identificador único y estable         |
| `dataset_version` | string       | Versión del dataset                   |
| `suite`           | enum         | `E2E`, `TMDB_AGENT` o `NETFLIX_AGENT` |
| `scenario_family` | string       | Familia funcional del escenario       |
| `scenario_type`   | string       | Variante específica                   |
| `difficulty`      | enum         | `EASY`, `MEDIUM`, `HARD`              |
| `tags`            | list[string] | Etiquetas analíticas                  |
| `split`           | enum         | `DEV`, `TEST` o `HOLDOUT`             |

## 6.2 Entrada del usuario

| Campo                  | Tipo         | Descripción                                                  |
| ---------------------- | ------------ | ------------------------------------------------------------ |
| `query`                | string       | Consulta principal del usuario                               |
| `language`             | string       | Idioma de la consulta                                        |
| `conversation_context` | list[object] | Mensajes anteriores necesarios                               |
| `user_constraints`     | object       | Restricciones explícitas representadas de forma estructurada |
| `implicit_intent`      | string       | Intención semántica utilizada para generar el caso           |

## 6.3 Expectativas de routing

| Campo                    | Tipo         | Descripción                                      |
| ------------------------ | ------------ | ------------------------------------------------ |
| `expected_route`         | enum         | Ruta funcional esperada                          |
| `expected_tool`          | enum         | Herramienta esperada o `NONE`                    |
| `expected_action`        | enum         | Acción esperada                                  |
| `acceptable_routes`      | list[enum]   | Rutas alternativas aceptables, normalmente vacía |
| `route_rationale`        | string       | Justificación de la etiqueta                     |
| `requires_clarification` | boolean      | Indica si debe solicitarse información adicional |
| `clarification_target`   | list[string] | Elementos que deben aclararse                    |

## 6.4 Expectations de ejecución

| Campo                       | Tipo         | Descripción                                              |
| --------------------------- | ------------ | -------------------------------------------------------- |
| `expected_tool_request`     | object       | Representación estructurada de la llamada esperada       |
| `tool_output_fixture_id`    | string/null  | Referencia al output controlado                          |
| `expected_selected_items`   | list[string] | Identificadores de resultados que deberían seleccionarse |
| `acceptable_selected_items` | list[string] | Alternativas aceptables                                  |
| `forbidden_selected_items`  | list[string] | Resultados que no deberían seleccionarse                 |

## 6.5 Expectativas de respuesta

| Campo                             | Tipo         | Descripción                                                         |
| --------------------------------- | ------------ | ------------------------------------------------------------------- |
| `expected_response_type`          | enum         | Recomendación, aclaración, fuera de alcance, sin resultados o error |
| `required_facts`                  | list[object] | Datos que deben aparecer                                            |
| `optional_facts`                  | list[object] | Datos válidos pero no obligatorios                                  |
| `forbidden_claims`                | list[string] | Afirmaciones que no deben aparecer                                  |
| `must_include_source_label`       | boolean      | Indica si debe identificarse la fuente                              |
| `must_include_dataset_disclaimer` | boolean      | Indica si debe mencionarse la antigüedad del dataset                |
| `minimum_recommendations`         | integer      | Número mínimo de recomendaciones                                    |
| `maximum_recommendations`         | integer      | Número máximo de recomendaciones                                    |
| `response_language`               | string       | Idioma esperado                                                     |
| `expected_behavior_summary`       | string       | Resumen de lo que constituye una respuesta válida                   |

## 6.6 Metadatos de generación

| Campo                         | Tipo         | Descripción                            |
| ----------------------------- | ------------ | -------------------------------------- |
| `generation_method`           | string       | Plantilla, LLM, mutación o composición |
| `generator_model`             | string       | Modelo utilizado                       |
| `generator_prompt_version`    | string       | Versión del prompt                     |
| `seed_scenario_id`            | string/null  | Escenario del que deriva               |
| `synthetic_variation_type`    | string/null  | Paráfrasis, typo, contradicción, etc.  |
| `generation_timestamp`        | datetime     | Fecha de generación                    |
| `automatic_validation_status` | enum         | `PASSED`, `FAILED` o `WARNING`         |
| `validation_warnings`         | list[string] | Posibles problemas detectados          |
| `review_status`               | enum         | En Silver será `NOT_HUMAN_REVIEWED`    |

---

# 7. Dataset end-to-end

## 7.1 Campos mínimos

El dataset end-to-end deberá incluir como mínimo:

```json
{
  "case_id": "e2e_001",
  "query": "What is a good movie trending today?",
  "expected_route": "TMDB_TRENDING",
  "expected_tool": "TMDB_TRENDING",
  "expected_action": "CALL_TOOL"
}
```

Para que sea útil en una evaluación real deberá incluir también:

```json
{
  "scenario_family": "current_trends",
  "difficulty": "EASY",
  "language": "en",
  "conversation_context": [],
  "expected_tool_request": {
    "time_window": "day"
  },
  "tool_output_fixture_id": "tmdb_fixture_001",
  "expected_selected_items": ["movie_123"],
  "acceptable_selected_items": ["movie_456"],
  "forbidden_claims": [
    "The movie is currently available on Netflix"
  ],
  "required_facts": [
    {
      "field": "title",
      "value": "Example Movie"
    }
  ],
  "expected_response_type": "RECOMMENDATION"
}
```

## 7.2 Familias de escenarios end-to-end

### A. Routing hacia TMDB

Ejemplos de señales:

* “Trending today”.
* “Popular right now”.
* “Current best movie”.
* “Released lately”.
* “What should I watch this week?”
* “Any superhero movie trending now?”

### B. Routing hacia Netflix

Ejemplos:

* Género sin referencia temporal.
* Temática específica.
* Documentales.
* Preferencias de tipo.
* Combinaciones de género.
* Consultas que mencionan expresamente Netflix.
* Consultas que no mencionan Netflix pero corresponden al dominio del dataset.

### C. Fuera de alcance

Ejemplos:

* Música.
* Restaurantes.
* Noticias.
* Libros.
* Recomendaciones médicas.
* Compra de entradas.
* Disponibilidad actual en una plataforma no soportada.
* Consultas sobre actores cuando no solicitan una recomendación.

Resultado esperado:

```json
{
  "expected_route": "OUT_OF_SCOPE",
  "expected_tool": "NONE",
  "expected_action": "RETURN_OUT_OF_SCOPE"
}
```

### D. Necesidad de aclaración

Ejemplos:

* “Recommend me something good”.
* “Which one is better?”
* “Find the movie I mentioned before”, sin contexto.
* Consulta que exige simultáneamente tendencias actuales y disponibilidad garantizada en Netflix.
* Preferencias incompatibles.
* Consulta incompleta.

Resultado esperado:

```json
{
  "expected_route": "NEEDS_CLARIFICATION",
  "expected_tool": "NONE",
  "expected_action": "ASK_CLARIFYING_QUESTION",
  "clarification_target": [
    "preferred_source_or_catalogue"
  ]
}
```

### E. Consultas multi-intent

Ejemplos:

* “What is trending and which of those movies is on Netflix?”
* “Give me a current movie and also a nature documentary.”
* “Find me a Netflix comedy, but it must have been released this week.”

Estos casos deberán definir explícitamente si:

* Se prioriza una de las intenciones.
* Se pide una aclaración.
* Se admite una respuesta parcial.
* La consulta se considera no soportada.

### F. Conversaciones multivuelta

Ejemplo:

```json
{
  "conversation_context": [
    {
      "role": "user",
      "content": "I want a Netflix movie."
    },
    {
      "role": "assistant",
      "content": "What genre would you prefer?"
    }
  ],
  "query": "Something about spies and action."
}
```

El caso debe comprobar que el sistema utiliza el contexto y no clasifica la última frase de forma aislada.

### G. Robustez lingüística

Se incluirán:

* Inglés.
* Español.
* Consultas mixtas.
* Errores ortográficos.
* Texto coloquial.
* Consultas muy breves.
* Consultas excesivamente largas.
* Negaciones.
* Restricciones expresadas indirectamente.

---

# 8. Dataset del agente TMDB

Cada caso del dataset TMDB evaluará dos etapas independientes.

## 8.1 Etapa A: generación de la solicitud a la herramienta

Campos específicos:

| Campo                          | Tipo         | Descripción                   |
| ------------------------------ | ------------ | ----------------------------- |
| `expected_endpoint`            | string       | Endpoint permitido            |
| `expected_time_window`         | enum         | `day` o `week`                |
| `expected_query_intent`        | object       | Intención estructurada        |
| `expected_content_type`        | string       | Normalmente `movie`           |
| `expected_genres`              | list[string] | Géneros solicitados           |
| `expected_themes`              | list[string] | Temáticas solicitadas         |
| `expected_recency_requirement` | object       | Restricción de actualidad     |
| `forbidden_tool_parameters`    | list[string] | Parámetros no permitidos      |
| `tool_call_required`           | boolean      | Si debe realizarse la llamada |

Ejemplo:

```json
{
  "case_id": "tmdb_014",
  "query": "Is there a good superhero movie trending today?",
  "expected_tool": "TMDB_TRENDING",
  "expected_tool_request": {
    "endpoint": "trending_movies",
    "time_window": "day"
  },
  "expected_query_intent": {
    "genres": [],
    "themes": ["superheroes"],
    "requires_recent_release": false,
    "ranking_preference": "quality_and_trend"
  },
  "forbidden_tool_parameters": [
    "search_query",
    "watch_provider",
    "region"
  ]
}
```

## 8.2 Etapa B: procesamiento del output

El caso contendrá un fixture de TMDB similar a la respuesta real del endpoint.

Campos específicos:

| Campo                       | Tipo         | Descripción                   |
| --------------------------- | ------------ | ----------------------------- |
| `tool_output_fixture_id`    | string       | Fixture utilizado             |
| `candidate_movie_ids`       | list[string] | Títulos disponibles           |
| `expected_selected_items`   | list[string] | Mejor selección esperada      |
| `acceptable_selected_items` | list[string] | Selecciones defendibles       |
| `expected_excluded_items`   | list[string] | Títulos que deben excluirse   |
| `selection_rationale`       | object       | Motivos esperados             |
| `required_output_fields`    | list[string] | Campos que deben utilizarse   |
| `unsupported_facts`         | list[string] | Datos no presentes en la tool |

## 8.3 Escenarios TMDB

El Silver Dataset deberá incluir:

* Tendencias diarias.
* Tendencias semanales.
* Preferencia por calidad.
* Preferencia por popularidad.
* Petición de películas recientes.
* Películas antiguas que vuelven a ser tendencia.
* Coincidencia temática mediante overview.
* Coincidencia de género.
* Varias opciones igualmente válidas.
* Resultados sin coincidencia temática.
* Resultados vacíos.
* Output incompleto.
* Películas sin fecha.
* Películas sin puntuación.
* Puntuación alta con pocos votos.
* Puntuación moderada con muchos votos.
* Duplicados.
* Timeout.
* Error de autenticación.
* Rate limit.
* Payload inválido.

---

# 9. Dataset del agente Netflix Hybrid RAG

También se dividirá en dos etapas.

## 9.1 Etapa A: generación de la consulta de retrieval

Campos específicos:

| Campo                     | Tipo          | Descripción                     |
| ------------------------- | ------------- | ------------------------------- |
| `expected_semantic_query` | string        | Consulta normalizada esperada   |
| `semantic_concepts`       | list[string]  | Conceptos que debe conservar    |
| `expected_filters`        | object        | Filtros estructurados           |
| `forbidden_filters`       | object        | Filtros que no deben añadirse   |
| `expected_search_mode`    | enum          | `LEXICAL`, `SEMANTIC` o `HYBRID` |
| `expected_semantic_ratio` | number/range  | Mezcla léxica/vectorial aceptable |
| `expected_embedder`       | string/null   | Embedder configurado cuando aplique |
| `expected_top_k`          | integer/range | Número esperado de candidatos   |
| `query_rewrite_required`  | boolean       | Si debe reformularse            |
| `original_query_noise`    | list[string]  | Elementos que pueden eliminarse |

Ejemplo:

```json
{
  "case_id": "netflix_021",
  "query": "I want to watch something on TV, maybe an action movie with spies, but not too old.",
  "expected_semantic_query": "action spy movie",
  "expected_search_mode": "HYBRID",
  "expected_semantic_ratio": {
    "minimum": 0.4,
    "maximum": 0.8
  },
  "expected_embedder": "netflix-default",
  "semantic_concepts": [
    "action",
    "spies"
  ],
  "expected_filters": {
    "type": "MOVIE",
    "release_year": {
      "minimum": 2010
    }
  },
  "forbidden_filters": {
    "country": "US"
  },
  "expected_top_k": {
    "minimum": 5,
    "maximum": 15
  }
}
```

La evaluación no requerirá que `expected_semantic_query` coincida literalmente.

Serían igualmente válidas:

* “spy action films”.
* “action movies involving espionage”.
* “espionage action movie”.

Lo que se evaluará es la conservación de conceptos, la correcta extracción de filtros y una configuración híbrida compatible con Meilisearch CE.

## 9.2 Etapa B: procesamiento del output

El fixture contendrá una lista controlada de documentos recuperados.

Campos específicos:

| Campo                             | Tipo         | Descripción                                  |
| --------------------------------- | ------------ | -------------------------------------------- |
| `retrieved_document_ids`          | list[string] | Documentos entregados al agente              |
| `document_relevance_labels`       | object       | Relevancia esperada por documento            |
| `expected_selected_items`         | list[string] | Recomendaciones principales                  |
| `acceptable_selected_items`       | list[string] | Alternativas válidas                         |
| `expected_excluded_items`         | list[string] | Documentos que no deben recomendarse         |
| `required_metadata_usage`         | list[string] | Metadatos que deben considerarse             |
| `must_include_dataset_disclaimer` | boolean      | Aviso sobre el snapshot histórico            |
| `forbidden_availability_claims`   | list[string] | Afirmaciones de disponibilidad no permitidas |
| `search_mode_used`                 | enum         | Modo efectivo de retrieval                    |
| `semantic_ratio_used`              | number/null  | Mezcla efectiva registrada                    |
| `ranking_score_details`            | object/null  | Evidencia de ranking cuando esté habilitada   |

## 9.3 Escenarios Netflix

Se cubrirán:

* Género único.
* Múltiples géneros.
* Temática semántica.
* Película frente a serie.
* Documentales.
* Restricción por año.
* Restricción por duración.
* Restricción por país.
* Restricción por calidad.
* Preferencias negativas.
* Combinaciones de filtros.
* Sin coincidencia exacta.
* Coincidencias parciales.
* Coincidencia exacta por título.
* Título o género con errores ortográficos.
* Query léxica con identificadores o términos muy específicos.
* Query conceptual que exige señal vectorial.
* Comparación de baseline léxico, baseline semántico y hybrid search.
* Documentos muy similares.
* Documento semánticamente relevante pero con tipo incorrecto.
* Documento con buen género pero descripción irrelevante.
* Documento relevante con puntuación baja.
* Documento parcialmente incompleto.
* Resultados duplicados.
* Output vacío.
* Índice Meilisearch no disponible o desactualizado.
* Resultado con baja similitud.
* Consultas que preguntan por disponibilidad actual.

---

# 10. Taxonomía inicial de escenarios

Cada caso tendrá una o varias etiquetas.

## 10.1 Etiquetas de intención

* `current_trends`
* `recent_release`
* `genre_request`
* `theme_request`
* `documentary_request`
* `movie_request`
* `series_request`
* `quality_request`
* `popularity_request`
* `open_recommendation`

## 10.2 Etiquetas de complejidad

* `single_constraint`
* `multiple_constraints`
* `implicit_constraint`
* `negative_constraint`
* `contradictory_constraints`
* `multi_intent`
* `conversation_context`
* `underspecified`

## 10.3 Etiquetas de robustez

* `typo`
* `colloquial`
* `multilingual`
* `code_switching`
* `long_query`
* `short_query`
* `negation`
* `adversarial_instruction`
* `prompt_injection_attempt`

## 10.4 Etiquetas de tool output

* `normal_output`
* `empty_output`
* `partial_output`
* `malformed_output`
* `timeout`
* `authentication_error`
* `rate_limit`
* `duplicate_results`
* `low_relevance_results`

---

# 11. Métricas

Las métricas se dividirán por capa.

## 11.1 Métricas de routing

### Route accuracy

Porcentaje de consultas cuya ruta coincide con `expected_route`.

```text
route_accuracy =
correct_routes / total_cases
```

### Macro F1 por ruta

Se calcularán precision, recall y F1 para:

* `TMDB_TRENDING`
* `NETFLIX_RAG`
* `OUT_OF_SCOPE`
* `NEEDS_CLARIFICATION`

Macro F1 tendrá más importancia que accuracy porque evita que las clases mayoritarias oculten un rendimiento pobre en clases minoritarias.

### Confusion matrix

Permitirá identificar errores como:

* Netflix clasificado como TMDB.
* Consulta ambigua clasificada como Netflix.
* Consulta fuera de alcance que activa una herramienta.

### Unnecessary tool call rate

Porcentaje de casos con `expected_tool=NONE` en los que el sistema realiza una llamada.

```text
unnecessary_tool_call_rate =
unexpected_tool_calls / cases_expected_without_tool
```

### Missed tool call rate

Porcentaje de casos que requerían herramienta y no la ejecutaron.

### Clarification precision

De todas las veces que el sistema pidió aclaración, cuántas realmente requerían aclaración.

### Clarification recall

De todos los casos que requerían aclaración, cuántos fueron detectados.

### Out-of-scope precision y recall

Miden específicamente la capacidad de rechazar o redirigir consultas fuera del dominio.

### Routing confidence calibration

Cuando el router produzca un nivel de confianza, se comparará dicha confianza con la tasa real de aciertos.

Podrán utilizarse:

* Expected Calibration Error.
* Brier Score.

Esta métrica será secundaria para el MVP.

---

## 11.2 Métricas de generación de tool calls

### Tool selection accuracy

Porcentaje de casos en los que se selecciona la herramienta correcta.

### Tool request schema validity

Porcentaje de llamadas que cumplen el esquema requerido.

### Required parameter accuracy

Porcentaje de parámetros obligatorios correctamente generados.

### Unsupported parameter rate

Porcentaje de llamadas que contienen parámetros no soportados.

Para TMDB será especialmente importante comprobar que no se utilizan endpoints o parámetros fuera del alcance definido.

### Filter extraction precision

De todos los filtros extraídos por el agente, qué proporción había sido solicitada por el usuario.

### Filter extraction recall

De todos los filtros solicitados, qué proporción fue extraída.

### Filter extraction F1

Media armónica entre precision y recall.

Los filtros podrán compararse por campo:

* Tipo.
* Género.
* Tema.
* Año mínimo.
* Año máximo.
* Duración.
* País.
* Restricciones negativas.

### Semantic concept recall

Porcentaje de conceptos relevantes de la consulta que permanecen en la query de retrieval.

Ejemplo:

```text
Consulta original:
"An action movie about spies, but not too old"

Conceptos esperados:
["action", "spies"]

Query generada:
"recent espionage action films"

Semantic concept recall:
2 / 2
```

### Query contamination rate

Porcentaje de conceptos añadidos que no estaban presentes ni podían inferirse razonablemente de la consulta.

### Search mode accuracy

Porcentaje de casos Netflix que utilizan el modo `LEXICAL`, `SEMANTIC` o `HYBRID` esperado o una alternativa declarada como aceptable.

### Semantic ratio compliance

Porcentaje de llamadas híbridas cuyo `semanticRatio` se encuentra en el rango aceptable del caso y dentro de `[0,1]`.

### Exact endpoint compliance

Para TMDB:

```text
endpoint_compliance =
calls_to_allowed_endpoint / all_tmdb_calls
```

El objetivo deberá ser 100 %.

---

## 11.3 Métricas de retrieval de Netflix

Estas métricas se calcularán antes de la generación de la respuesta.

Se ejecutarán tres configuraciones sobre el mismo conjunto cuando sea viable:

1. Baseline léxico con `semanticRatio=0.0`.
2. Baseline semántico con `semanticRatio=1.0`.
3. Configuración híbrida candidata con `0.0 < semanticRatio < 1.0`.

### Recall@k

Mide si los documentos considerados relevantes aparecen entre los primeros `k` resultados.

### Precision@k

Mide qué proporción de los primeros `k` documentos es relevante.

### Mean Reciprocal Rank

Evalúa la posición del primer resultado relevante.

### nDCG@k

Evalúa la calidad del orden cuando existen diferentes grados de relevancia.

Los documentos podrán etiquetarse sintéticamente como:

* `3`: altamente relevante.
* `2`: relevante.
* `1`: parcialmente relevante.
* `0`: irrelevante.

### Metadata constraint satisfaction

Porcentaje de documentos recuperados que cumplen los filtros obligatorios.

### Retrieval empty-result accuracy

Comprueba si el sistema detecta correctamente que no existen resultados con suficiente relevancia.

### Hybrid uplift

Mejora de Recall@k, nDCG@k o end-to-end success de la configuración híbrida frente al mejor baseline puro. Se reportará incluso cuando sea negativa; no se asumirá que hybrid search es superior sin evidencia.

### Exact/typo query success

Éxito segmentado para títulos exactos, prefijos y consultas con errores ortográficos, donde la señal léxica de Meilisearch debería aportar valor.

---

## 11.4 Métricas de procesamiento del output

### Selected item precision

De todos los elementos recomendados, qué proporción pertenece al conjunto permitido.

```text
selected_item_precision =
allowed_selected_items / all_selected_items
```

### Expected item hit rate

Porcentaje de casos en los que se selecciona al menos uno de los elementos esperados.

### Constraint satisfaction rate

Porcentaje de recomendaciones que cumplen todas las restricciones obligatorias.

### Grounded title rate

Porcentaje de títulos mencionados que aparecen en el output de la herramienta.

El objetivo deberá ser 100 %.

### Unsupported claim rate

Porcentaje de afirmaciones verificables que no están soportadas por el output.

Ejemplos:

* Inventar disponibilidad actual.
* Inventar puntuaciones.
* Inventar género.
* Inventar fecha de estreno.
* Inventar detalles de la trama.

### Tool output utilization

Comprueba si la respuesta utiliza información relevante recibida de la herramienta.

Podrá medirse mediante la cobertura de los `required_facts`.

### Required fact coverage

```text
required_fact_coverage =
required_facts_mentioned / total_required_facts
```

### Forbidden claim violation rate

Porcentaje de respuestas que contienen una afirmación marcada como prohibida.

### Ranking agreement

Cuando exista un ranking esperado, podrá utilizarse:

* Top-1 accuracy.
* Spearman correlation.
* nDCG sobre recomendaciones finales.

---

## 11.5 Métricas de respuesta final

### End-to-end task success

Un caso se considerará exitoso cuando cumpla todos los criterios críticos:

* Ruta correcta.
* Acción correcta.
* Tool correcta.
* Parámetros críticos correctos.
* Recomendaciones permitidas.
* Ausencia de afirmaciones prohibidas.
* Respuesta del tipo esperado.

### Response type accuracy

Evalúa si el sistema:

* Recomienda.
* Pide aclaración.
* Declara que está fuera de alcance.
* Informa de que no hay resultados.
* Devuelve un error controlado.

### Recommendation count compliance

Comprueba que el número de recomendaciones se encuentra dentro del rango esperado.

### Language consistency

Comprueba que la respuesta utiliza el idioma esperado.

### Source attribution rate

Porcentaje de respuestas que identifican correctamente la fuente cuando se requiere.

### Dataset disclaimer compliance

Porcentaje de respuestas del agente Netflix que incluyen el aviso cuando la consulta podría interpretarse como disponibilidad actual.

### Controlled failure rate

Porcentaje de errores técnicos que se convierten en respuestas seguras sin exponer:

* Stack traces.
* Credenciales.
* Mensajes internos.
* Payloads completos.
* Información sensible.

---

## 11.6 Métricas operativas

Aunque no forman parte del contenido del Silver Dataset, se recogerán durante su ejecución:

* Latencia de routing.
* Latencia de tool call.
* Latencia de retrieval.
* Time to first token.
* Latencia total.
* Número de llamadas LLM.
* Número de llamadas a herramientas.
* Tokens de entrada.
* Tokens de salida.
* Coste estimado por caso.
* Tasa de errores.
* Tasa de reintentos.
* Versión de Meilisearch e index UID para reproducibilidad del resultado.
* Index UID, embedder, modo de búsqueda y `semanticRatio`.
* Query normalizada, filtros, top-k y ranking details sanitizados.
* Latencia de Meilisearch y estado de la tarea de indexación cuando aplique.

---

## 11.7 Robustez y estabilidad

Cada caso podrá ejecutarse varias veces debido al carácter no determinista del modelo.

Se calcularán:

### Pass@1

Resultado de una ejecución individual.

### Repeated pass rate

Porcentaje de ejecuciones correctas de un mismo caso.

Por ejemplo:

```text
Caso ejecutado 5 veces
Resultados correctos: 4

Repeated pass rate = 0.8
```

### Decision stability

Porcentaje de ejecuciones que producen la misma ruta.

### Recommendation stability

Grado de coincidencia entre recomendaciones de distintas ejecuciones.

No se requerirá que la redacción sea idéntica.

---

# 12. Evaluación determinista y evaluación semántica

Las comprobaciones se dividirán en tres niveles.

## 12.1 Nivel 1: validadores deterministas

Serán la fuente principal de las métricas.

Ejemplos:

* Igualdad de enums.
* Validación JSON Schema.
* Comparación de parámetros.
* Comprobación de rangos.
* Presencia de IDs.
* Presencia de facts.
* Detección de títulos no incluidos en el fixture.
* Comprobación de filtros.
* Contador de recomendaciones.
* Detección de tool calls inesperadas.

## 12.2 Nivel 2: evaluadores semánticos

Se utilizarán cuando no sea razonable exigir coincidencia literal.

Ejemplos:

* Equivalencia de una query reescrita.
* Calidad de una explicación.
* Cobertura semántica.
* Detección de afirmaciones no soportadas.
* Adecuación de una pregunta de aclaración.

Podrán implementarse mediante:

* Embeddings.
* Reglas semánticas.
* Un modelo evaluador independiente.

## 12.3 Nivel 3: revisión humana futura

No formará parte del alcance actual.

Se utilizará para producir el Gold Dataset y validar:

* Realismo de las consultas.
* Corrección de las etiquetas.
* Calidad de las expectativas.
* Casos con más de una respuesta razonable.
* Criterios subjetivos de utilidad.

---

# 13. Proceso de generación

## 13.1 Paso 1: definir la matriz de cobertura

Antes de generar consultas se construirá una matriz de escenarios.

Ejemplo simplificado:

| Ruta          | Escenario                 | Idioma | Dificultad | Variación        |
| ------------- | ------------------------- | ------ | ---------- | ---------------- |
| TMDB          | Trending today            | EN     | Easy       | Direct           |
| TMDB          | Recent superhero          | ES     | Medium     | Implicit         |
| Netflix       | Spy action movie          | EN     | Easy       | Direct           |
| Netflix       | Romantic comedy, recent   | ES     | Medium     | Multiple filters |
| Clarification | Vague recommendation      | EN     | Easy       | Underspecified   |
| Out of scope  | Restaurant recommendation | ES     | Easy       | Direct           |

La generación deberá partir de esta matriz y no de una petición genérica de “genera preguntas”.

## 13.2 Paso 2: generar una especificación latente

Cada escenario se representará primero de forma estructurada.

Ejemplo:

```json
{
  "route": "NETFLIX_RAG",
  "content_type": "MOVIE",
  "genres": ["action"],
  "themes": ["spies"],
  "minimum_release_year": 2010,
  "language": "en",
  "difficulty": "MEDIUM",
  "surface_form": "colloquial"
}
```

Esta especificación será la fuente de verdad del caso.

## 13.3 Paso 3: derivar las expectativas

A partir de la especificación se generarán automáticamente:

* `expected_route`
* `expected_tool`
* `expected_action`
* `expected_filters`
* `semantic_concepts`
* Criterios de respuesta
* Etiquetas
* Dificultad

Las etiquetas no deberán inferirse posteriormente a partir de la query generada.

## 13.4 Paso 4: generar la consulta

Un modelo generador convertirá la especificación en una consulta natural.

El prompt indicará:

* Idioma.
* Nivel de formalidad.
* Longitud.
* Errores o ruido deseados.
* Información explícita.
* Información implícita.
* Restricciones que deben conservarse.

## 13.5 Paso 5: generar variaciones

Sobre cada escenario base podrán crearse mutaciones:

* Paráfrasis.
* Consulta breve.
* Consulta extensa.
* Error ortográfico.
* Lenguaje coloquial.
* Negación.
* Orden diferente de restricciones.
* Traducción.
* Code-switching.
* Contexto conversacional.
* Distractores irrelevantes.
* Instrucciones contradictorias.
* Prompt injection.

Las mutaciones conservarán las etiquetas funcionales salvo que estén diseñadas específicamente para cambiar la ruta.

## 13.6 Paso 6: crear fixtures de herramientas

### Fixtures TMDB

Se generarán utilizando el esquema realista del endpoint, pero con contenido controlado.

Podrán proceder de:

* Snapshots anonimizados de respuestas reales.
* Fixtures completamente sintéticos.
* Combinaciones de resultados reales modificados.
* Casos adversariales creados manualmente mediante reglas.

Los fixtures incluirán situaciones como:

* Mejor película evidente.
* Varias películas válidas.
* Resultado popular pero de baja calidad.
* Resultado antiguo que vuelve a ser tendencia.
* Resultado temáticamente irrelevante.
* Output vacío.
* Error.

### Fixtures Netflix

Se construirán conjuntos controlados compatibles con la respuesta de búsqueda de Meilisearch.

Podrán utilizar:

* Filas reales del dataset.
* Subconjuntos etiquetados sintéticamente.
* Documentos irrelevantes añadidos como distractores.
* Resultados con diferentes niveles de relevancia.
* Resultados léxicos, semánticos e híbridos sobre el mismo corpus.
* Coincidencias exactas, prefijos y typos.
* Filtros por tipo, género y año.

Cada documento tendrá una etiqueta esperada de relevancia.


## 13.7 Paso 7: derivar expectativas de procesamiento

A partir de los fixtures se determinarán:

* Elementos esperados.
* Alternativas aceptables.
* Elementos prohibidos.
* Datos obligatorios.
* Restricciones.
* Afirmaciones no soportadas.
* Tipo de respuesta.

Cuando varios títulos sean válidos, el dataset deberá representarlo explícitamente y no imponer un único título como respuesta correcta.

## 13.8 Paso 8: ejecutar validadores automáticos

Cada caso deberá superar validaciones como:

* JSON válido.
* Cumplimiento del esquema.
* `case_id` único.
* Etiquetas compatibles.
* `expected_tool=NONE` cuando no debe haber tool call.
* Fixture existente.
* IDs esperados presentes en el fixture.
* Elementos prohibidos también presentes cuando sean distractores.
* Parámetros soportados.
* Ausencia de contradicciones entre restricciones.
* Idioma correcto.
* Consulta no vacía.
* Consulta sin exposición de etiquetas internas.
* Ausencia de duplicados semánticos.

## 13.9 Paso 9: usar un modelo crítico independiente

Un segundo modelo, diferente del generador o ejecutado con un prompt distinto, revisará:

* Si la query representa la especificación.
* Si la ruta esperada es coherente.
* Si falta alguna restricción.
* Si el caso es artificial o poco claro.
* Si existe más de una ruta razonable.
* Si las expectativas son demasiado estrictas.

El crítico no modificará directamente el caso. Emitirá:

```json
{
  "status": "PASS",
  "confidence": 0.91,
  "warnings": []
}
```

Los casos con baja confianza se eliminarán o marcarán como `WARNING`.

## 13.10 Paso 10: deduplicar

Se aplicará deduplicación:

* Exacta.
* Normalizada.
* Por similitud semántica.
* Por escenario latente.

No deberán distribuirse paráfrasis casi idénticas entre `DEV` y `TEST`.

## 13.11 Paso 11: crear splits

El dataset se dividirá por familias de escenarios, no aleatoriamente por consulta.

Propuesta:

* `DEV`: 60 %.
* `TEST`: 25 %.
* `HOLDOUT`: 15 %.

Las variaciones de una misma semilla deberán permanecer en el mismo split.

Esto evita que una paráfrasis de entrenamiento aparezca como caso de test.

## 13.12 Paso 12: ejecutar un baseline

Se ejecutará una primera versión del agente contra el dataset.

El objetivo no será modificar las etiquetas para favorecer al agente, sino:

* Detectar casos imposibles.
* Encontrar expectativas contradictorias.
* Identificar gaps de cobertura.
* Encontrar casos excesivamente fáciles.
* Descubrir patrones de fallo.

## 13.13 Paso 13: hard-case mining

Los errores del baseline se clasificarán y podrán utilizarse para generar casos adicionales.

Ejemplos:

* Confunde “recent” con Netflix.
* Llama a TMDB ante cualquier mención de “movie”.
* No detecta restricciones negativas.
* Pide aclaración demasiado a menudo.
* Recomienda títulos no recuperados.

Este proceso permitirá que el Silver Dataset evolucione de una colección genérica a una suite adaptada al sistema.

---

# 14. Tamaño inicial propuesto

Para la prueba se propone un Silver Dataset inicial de entre **250 y 350 casos**.

## 14.1 End-to-end

Entre 120 y 160 casos:

| Ruta                       | Casos aproximados |
| -------------------------- | ----------------: |
| TMDB                       |             35–45 |
| Netflix                    |             40–55 |
| Out of scope               |             20–25 |
| Needs clarification        |             20–25 |
| Multi-intent y multivuelta |             10–15 |

## 14.2 TMDB Agent

Entre 60 y 90 casos.

Cada caso podrá evaluar tanto tool request como output processing.

## 14.3 Netflix Agent

Entre 80 y 110 casos.

El mayor número se justifica por la variedad de filtros y escenarios de retrieval.

El tamaño podrá reducirse si el tiempo disponible lo exige, siempre que se mantenga la diversidad de escenarios.

---

# 15. Scorecard propuesto

No se recomienda resumir toda la calidad en una única métrica. Se mostrará un cuadro de mando por dimensiones.

No obstante, para comparar versiones podrá calcularse un score agregado orientativo:

| Dimensión                            | Peso |
| ------------------------------------ | ---: |
| Routing                              | 20 % |
| Tool selection y request             | 20 % |
| Retrieval o selección de candidatos  | 20 % |
| Grounding y procesamiento del output | 25 % |
| Respuesta y manejo de errores        | 15 % |

El score agregado no sustituirá las métricas individuales.

Un sistema con buen score general pero una tasa de alucinación superior a cero deberá considerarse problemático.

---

# 16. Criterios de aceptación de la épica

La épica se considerará completada cuando:

1. Exista una taxonomía documentada de escenarios.
2. Exista un esquema JSON versionado.
3. Se hayan creado las tres suites de evaluación.
4. Todos los casos incluyan `query`, `expected_route`, `expected_tool` y `expected_action`.
5. Los casos de agente incluyan expectations de tool request y output processing.
6. Los fixtures sean deterministas y reproducibles.
7. Todos los casos superen validación de esquema.
8. No existan duplicados significativos entre splits.
9. Se genere un reporte de distribución por ruta, dificultad, idioma y escenario.
10. Exista un runner capaz de ejecutar el agente contra el dataset.
11. Se calculen las métricas de routing, tool calls, retrieval, grounding y respuesta.
12. Se almacenen las trazas necesarias para analizar los fallos.
13. El dataset incluya versión, modelo generador y versión de prompts.
14. Se haya ejecutado y documentado un baseline.
15. Los casos no hayan sido revisados por humanos y estén identificados explícitamente como Silver.
16. Las suites Netflix comparen al menos baseline léxico, baseline semántico y configuración híbrida.
17. Todas las ejecuciones Netflix registren versión de Meilisearch, index UID, embedder, modo y `semanticRatio` para reproducibilidad.

---

# 17. Entregables

* `schemas/evaluation_case.schema.json`
* `datasets/e2e_routing_silver.jsonl`
* `datasets/tmdb_agent_silver.jsonl`
* `datasets/netflix_agent_silver.jsonl`
* `fixtures/tmdb/*.json`
* `fixtures/netflix/*.json`
* `generation/scenario_matrix.yaml`
* `generation/generate_dataset.py`
* `generation/validate_dataset.py`
* `evaluation/run_evaluation.py`
* `evaluation/metrics.py`
* `reports/silver_dataset_card.md`
* `reports/baseline_results.md`
* `reports/failure_analysis.md`
* `evaluation/search_mode_comparison.py`

---

# 18. Dataset card

El Silver Dataset deberá acompañarse de una ficha que documente:

* Propósito.
* Alcance.
* Versión.
* Fecha de generación.
* Modelos utilizados.
* Prompts utilizados.
* Número de casos.
* Distribución de clases.
* Idiomas.
* Método de generación.
* Método de validación.
* Limitaciones.
* Sesgos conocidos.
* Casos excluidos.
* Diferencia entre Silver y Gold.
* Recomendaciones de uso.
* Métricas que permite calcular.
* Versión de Meilisearch utilizada durante la evaluación.
* Configuración del índice, embedder y `semanticRatio` evaluado.

---

# 19. Limitaciones

1. Las consultas son sintéticas y pueden no reflejar completamente el comportamiento de usuarios reales.
2. El modelo generador puede introducir patrones lingüísticos repetitivos.
3. El modelo crítico puede compartir sesgos con el modelo evaluado.
4. Las etiquetas no han sido validadas por expertos.
5. Algunas consultas pueden admitir más de una ruta razonable.
6. Las expectativas semánticas pueden ser incompletas.
7. Los fixtures de herramientas pueden no representar toda la variabilidad de producción.
8. Las métricas automáticas no sustituyen la evaluación humana.
9. Un buen resultado en el Silver Dataset no garantiza rendimiento equivalente en producción.
10. El dataset deberá evolucionar a partir de errores observados y consultas reales.
11. La relevancia híbrida depende de la configuración, embedder y versión de Meilisearch.
12. La edición y licencia del motor no forman parte de la evaluación del agente; se validarán mediante tests técnicos y controles de build independientes.

---

# 20. Evolución hacia Gold Dataset

La futura creación del Gold Dataset seguirá este proceso:

1. Selección de una muestra estratificada del Silver Dataset.
2. Revisión independiente por expertos.
3. Resolución de desacuerdos.
4. Modificación de consultas artificiales.
5. Corrección de rutas y expectativas.
6. Revisión de fixtures.
7. Adición de casos reales anonimizados.
8. Definición de acuerdos interanotador.
9. Congelación de un conjunto holdout.
10. Versionado y publicación interna.

El Gold Dataset no deberá construirse simplemente aprobando todos los casos Silver. Deberá considerarse un nuevo artefacto derivado mediante revisión y corrección humana.
