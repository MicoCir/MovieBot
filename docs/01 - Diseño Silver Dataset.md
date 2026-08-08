# Fase 1 — Diseño del Silver Evaluation Dataset

## Movie Recommendation Chatbot — GenAI Engineer Take-Home Assessment

**Estado:** Diseño definido
**Propósito:** establecer cómo será construido el dataset de evaluación, qué información contendrá cada caso, cómo se determinarán sus respuestas esperadas y qué papel tendrá el LLM durante su generación.

---

# 1. Objetivo

El objetivo del Silver Evaluation Dataset es disponer de un conjunto reproducible de consultas que permita evaluar posteriormente el comportamiento del sistema de recomendación.

El dataset debe permitir evaluar de forma separada:

```text
User query
    ↓
Routing
    ↓
Query interpretation
    ↓
Retrieval / candidate selection
    ↓
Final grounded response
```

La evaluación no debe limitarse a comprobar si una respuesta final "parece razonable".

Debe ser posible determinar si:

* se seleccionó la fuente correcta;
* se interpretaron correctamente las restricciones del usuario;
* se recuperaron candidatos relevantes;
* se respetaron los filtros obligatorios;
* el sistema se abstuvo cuando no existían resultados válidos;
* las recomendaciones procedían realmente de las fuentes disponibles;
* las fuentes TMDB y Netflix permanecieron correctamente diferenciadas.

---

# 2. Principio fundamental del dataset

El dataset no intentará definir una única película como:

```text
"la mejor respuesta"
```

para cada consulta.

En un sistema de recomendación pueden existir múltiples respuestas igualmente válidas.

Por ejemplo:

```text
"I want an action movie about spies"
```

podría tener decenas de películas razonablemente relevantes.

Por tanto, el dataset distinguirá entre:

```text
seed item
eligible items
relevant items
irrelevant items
```

El `seed_item` servirá para construir el caso y garantizar que existe al menos una respuesta conocida cuando corresponda, pero no se considerará automáticamente la única ni la mejor respuesta posible.

---

# 3. Tipo de dataset: Silver Dataset

El conjunto de evaluación se considerará un **Silver Dataset**.

Esto significa que contiene una verdad de evaluación controlada y reproducible, pero no pretende representar una verdad absoluta sobre cuáles son objetivamente las mejores recomendaciones cinematográficas.

Parte de sus etiquetas podrán obtenerse de forma completamente determinista:

* route;
* datasource;
* tipo de contenido;
* año;
* género;
* actor, cuando exista metadata verificable;
* director, cuando exista metadata verificable;
* certificación;
* existencia o inexistencia de candidatos.

Otras etiquetas, especialmente las relacionadas con relevancia semántica, podrán obtenerse mediante procedimientos de evaluación asistidos.

Esta distinción debe quedar explícita para evitar presentar juicios subjetivos como ground truth absoluto.

---

# 4. Tamaño y distribución

La primera versión contendrá:

| Expected route |   Casos |
| -------------- | ------: |
| `TRENDING`     |      50 |
| `NETFLIX`      |      50 |
| `BOTH`         |      25 |
| `OUT_OF_SCOPE` |      25 |
| **Total**      | **150** |

Las cuatro categorías se corresponden directamente con las rutas operativas definidas para el sistema.

---

# 5. Un único dataset con distintas vistas

No se crearán datasets independientes para router, TMDB y Netflix.

Los 150 casos formarán un único dataset versionado.

Posteriormente podrán utilizarse como diferentes suites lógicas.

```text
Routing suite
→ 150 casos

TMDB suite
→ TRENDING
→ componente TMDB de BOTH

Netflix suite
→ NETFLIX
→ componente Netflix de BOTH
```

Esto evita duplicación y permite que una misma query evalúe diferentes capas del sistema.

Por ejemplo:

```text
"Recommend me a comedy"
```

puede comprobar simultáneamente:

```text
route = BOTH

TMDB interpretation
Netflix interpretation

TMDB candidates
Netflix candidates

source-aware final response
```

---

# 6. El dataset se generará desde datos hacia lenguaje

La decisión principal de generación es:

> **Primero se construye el caso estructurado y después se genera la consulta en lenguaje natural.**

No se generarán libremente 150 preguntas para intentar etiquetarlas posteriormente.

El flujo conceptual será:

```text
Datasource real / fixture
        ↓
Structured seed
        ↓
Known expected behaviour
        ↓
Natural-language generation
        ↓
Generated-query validation
        ↓
Evaluation case
```

Esto permite conocer el comportamiento esperado antes de que intervenga el LLM.

---

# 7. Motivo para no generar queries primero

Se descarta el enfoque:

```text
LLM generates arbitrary query
        ↓
LLM decides expected route
        ↓
LLM decides expected answer
```

Este enfoque tendría varios problemas.

### Circularidad

El mismo modelo que crea el problema estaría definiendo cuál es la respuesta correcta.

### Gold poco fiable

Una query generada libremente podría contener ambigüedades no previstas.

### Contaminación de etiquetas

El LLM podría interpretar posteriormente una intención distinta de la utilizada para generar la consulta.

### Poca reproducibilidad

Sería difícil justificar por qué una etiqueta concreta debe considerarse correcta.

Por tanto, las etiquetas principales se decidirán antes de generar el texto.

---

# 8. Structured Seed

Cada query partirá de una representación estructurada.

Ejemplo conceptual:

```yaml
route: netflix

hard_constraints:
  type: movie
  genres:
    - action

semantic_concepts:
  - espionage
  - undercover agent

seed_item_ids:
  - movie_001
```

El LLM recibirá este objeto y podrá transformarlo, por ejemplo, en:

```text
"I'm looking for an action movie about spies working undercover."
```

La consulta debe preservar el significado del seed.

---

# 9. Separación entre hard constraints e intención semántica

Esta distinción será una propiedad fundamental de los casos Netflix.

## Hard constraints

Son condiciones que pueden verificarse directamente contra metadata.

Ejemplos:

```text
type
genre
release year
age certification
actor
director
```

cuando dichos campos estén disponibles y sean verificables en el datasource.

Ejemplo:

```text
movie
+
action
+
2010–2019
```

## Semantic intent

Son conceptos cuya correspondencia depende del contenido textual.

Ejemplos:

```text
espionage
undercover investigation
political intrigue
nature exploration
slow-burn romance
family conflict
```

Un caso puede contener ambos tipos simultáneamente.

---

# 10. Los filtros duros tienen prioridad sobre la relevancia

Una película que incumple una restricción explícita no debe considerarse una buena recomendación aunque semánticamente se parezca mucho a la consulta.

Ejemplo:

```text
"I want an action movie about spies"
```

Si un candidato es una serie:

```text
type = show
```

incumple la query aunque su descripción trate exactamente sobre espionaje.

Por tanto:

```text
hard constraint violation
>
semantic relevance
```

en términos de evaluación.

La relevancia semántica sólo se juzgará entre candidatos que no contradigan las restricciones obligatorias.

---

# 11. Eligible Set

Para cada caso se intentará obtener, cuando sea posible, el conjunto de elementos que cumplen objetivamente sus restricciones:

```text
eligible_set
```

Por ejemplo:

```text
type = movie
actor = Anthony Perkins
```

permitiría realizar una búsqueda exhaustiva sobre el dataset.

Si existen tres coincidencias:

```text
eligible_item_ids:
- movie_12
- movie_27
- movie_91
```

sabemos que esas películas son candidatas potencialmente válidas.

Esto no implica que todas sean igual de relevantes para una query más compleja.

El `eligible_set` determina elegibilidad, no ranking.

---

# 12. Casos `NO_RESULTS`

Se generarán deliberadamente casos donde no exista ningún candidato válido.

No se dependerá de que estos casos aparezcan por casualidad.

Ejemplo:

```text
"Do you have any Anthony Perkins movies?"
```

Si una comprobación exhaustiva sobre los datos confirma:

```text
actor = Anthony Perkins
→ 0 matches
```

el gold será:

```yaml
expected_status: NO_RESULTS
eligible_item_ids: []
```

El comportamiento correcto será:

```text
0 recommendations
```

El sistema fallará si:

* devuelve una película de otro actor;
* relaja silenciosamente la restricción;
* inventa un título;
* recomienda una película únicamente porque es semánticamente parecida.

Estos casos permitirán evaluar explícitamente la capacidad de abstención del sistema.

---

# 13. Regla para atributos como actor o director

Sólo se generarán restricciones estructuradas que puedan verificarse contra los datos reales utilizados por el sistema.

Por tanto:

> Una query por actor o director sólo podrá formar parte del Silver Dataset como caso soportado si el dataset Netflix utilizado dispone de esa información de forma verificable y puede relacionarse de manera fiable con los títulos.

Antes de generar este tipo de seeds deberá comprobarse el schema real del dataset y, si corresponde, de sus datos de créditos.

Si dicha información está disponible:

```text
actors
directors
```

se incorporarán al modelo de restricciones estructuradas y deberán ser filtrables.

Si no está disponible o no puede comprobarse de forma fiable, no se generarán casos cuyo gold dependa de ella.

No se inferirá esa información utilizando conocimiento propio del LLM.

---

# 14. Generación de casos positivos mediante seed items

Para consultas que deben tener resultados, los casos partirán preferentemente de títulos reales.

Flujo:

```text
Real title
    ↓
Inspect verified metadata / description
    ↓
Select properties
    ↓
Structured seed
    ↓
Generate natural-language query
```

Ejemplo:

```text
Movie A

type:
movie

genre:
action

description:
An intelligence officer infiltrates a criminal organization...
```

Seed:

```yaml
hard_constraints:
  type: movie
  genres:
    - action

semantic_concepts:
  - espionage
  - undercover agent

seed_item_ids:
  - movie_A
```

Query generada:

```text
"I'd like an action movie about a spy working undercover."
```

Sabemos que `movie_A` constituye al menos una respuesta válida.

---

# 15. El seed item no será el gold completo

No se utilizará esta regla:

```text
retrieved_item != seed_item
→ failure
```

Sería incorrecta porque podrían existir otros títulos igualmente adecuados o incluso mejores.

El seed se interpreta únicamente como:

> evidencia conocida de que existe al menos un elemento relevante.

Por tanto, se almacenará separado del conjunto posterior de juicios de relevancia.

```yaml
seed_item_ids:
  - movie_A

relevance_judgments:
  movie_A: 3
  movie_B: 3
  movie_C: 2
```

---

# 16. Generación de casos Netflix

Los casos Netflix se construirán utilizando títulos reales del dataset.

No se permitirá al LLM inventar películas para crear las queries.

Pipeline conceptual:

```text
Netflix dataset
       ↓
sample real title(s)
       ↓
derive verified constraints
       ↓
derive semantic concepts
       ↓
create structured seed
       ↓
LLM Query Writer
       ↓
natural-language query
       ↓
validation
```

Los campos estructurados deben derivarse de metadata real.

Los conceptos semánticos deben estar suficientemente respaldados por la descripción disponible.

---

# 17. Generación de casos TMDB

TMDB presenta un problema diferente porque el contenido trending cambia con el tiempo.

No se generará el Silver Dataset contra la respuesta live utilizada el día de la evaluación.

Los casos TMDB estarán asociados a **fixtures versionados del endpoint Trending Movies**.

Pipeline:

```text
Versioned TMDB fixture
        ↓
select real candidate
        ↓
derive supported properties
        ↓
structured seed
        ↓
LLM Query Writer
        ↓
natural-language query
```

Cada caso debe conservar información suficiente para identificar:

```text
fixture_id
seed_candidate_ids
```

De esta forma:

```text
same evaluation case
+
same TMDB fixture
=
reproducible evaluation
```

Las respuestas live de TMDB continuarán utilizándose para demo/producción, pero no como ground truth cambiante del dataset.

---

# 18. Limitación de los casos TMDB

Los seeds TMDB sólo podrán utilizar condiciones comprobables mediante el endpoint permitido.

No se generarán casos cuyo gold dependa de información procedente de endpoints TMDB adicionales.

Por ejemplo, si el fixture no permite verificar de forma fiable una determinada preferencia, ésta no podrá convertirse en hard constraint.

Esto evita generar casos que posteriormente el agente no pueda resolver dentro de las restricciones del assessment.

---

# 19. Casos `BOTH`

Los casos `BOTH` representarán consultas que puedan satisfacerse razonablemente desde ambas fuentes sin expresar preferencia por Netflix ni por actualidad.

Ejemplos:

```text
"Recommend me a comedy"

"I want something about superheroes"

"Any good romantic movie?"
```

El gold de routing será:

```yaml
expected_route: both

expected_sources:
  - tmdb
  - netflix
```

Cada fuente tendrá su evaluación independiente.

No se creará un único conjunto de películas que mezcle resultados TMDB y Netflix.

---

# 20. No habrá ranking global TMDB vs Netflix

Incluso dentro del Silver Dataset, no se definirá algo como:

```text
1. Netflix movie
2. TMDB movie
3. Netflix movie
```

Las señales de ambas fuentes tienen significados distintos.

TMDB indica:

```text
candidate from current trending set
```

Netflix indica:

```text
candidate relevant within Netflix catalog
```

No existe un score común que permita afirmar justificadamente que uno de esos resultados es globalmente "mejor".

Por ello, los resultados y sus juicios permanecerán separados por fuente.

---

# 21. Casos `OUT_OF_SCOPE`

Los casos `OUT_OF_SCOPE` no necesitan películas gold.

Su verdad principal será estructural:

```yaml
expected_route: out_of_scope
expected_sources: []
```

Ejemplos pueden incluir:

* preguntas completamente fuera del dominio cinematográfico;
* peticiones que requieran fuentes no soportadas;
* operaciones que el chatbot no debe realizar.

El comportamiento esperado es no ejecutar TMDB ni Netflix.

---

# 22. Pooling para consultas semánticas

En consultas semánticas no es viable evaluar manualmente cada título de un catálogo grande.

Por ejemplo:

```text
"I want a movie about an undercover agent who starts questioning his loyalties."
```

No existe necesariamente un campo estructurado:

```text
undercover_agent_with_conflicted_loyalty = true
```

Para estos casos se utilizará **candidate pooling**.

Pipeline conceptual:

```text
Evaluation query
       ↓
Lexical retrieval
       +
Semantic retrieval
       +
Seed items
       ↓
Union / deduplication
       ↓
Candidate pool
       ↓
Relevance judging
```

El objetivo no es juzgar todo el catálogo.

Se juzga un conjunto razonable de candidatos que distintos métodos consideran plausibles.

Esto reduce drásticamente el coste de generación del Silver Dataset sin convertir el output de un único retriever en ground truth.

---

# 23. El gold no dependerá exclusivamente del retriever evaluado

No se utilizará:

```text
Meilisearch Top-K
→ ground truth
```

porque eso produciría una evaluación circular.

Si posteriormente se modifica Meilisearch, sus propios resultados anteriores no deben definir qué era correcto.

Por eso el candidate pool podrá incluir:

```text
lexical candidates
semantic candidates
seed candidates
```

y cualquier otra fuente de candidatos claramente definida durante la generación.

El conjunto resultante será juzgado independientemente.

---

# 24. Relevance Judgments

Los candidatos semánticos podrán recibir relevancia graduada:

```text
3 = excellent match
2 = good match
1 = weak but plausible match
0 = irrelevant
```

Ejemplo:

```yaml
relevance_judgments:
  movie_12: 3
  movie_28: 3
  movie_51: 2
  movie_73: 1
  movie_95: 0
```

Esto permite distinguir entre:

```text
valid candidate
```

y:

```text
particularly strong recommendation
```

sin exigir que exista una única película correcta.

---

# 25. Prioridad de reglas durante el relevance judging

El judging seguirá conceptualmente este orden:

```text
1. Hard constraints
        ↓
2. Eligibility
        ↓
3. Semantic relevance
        ↓
4. Ranking quality
```

Si un candidato viola un hard constraint:

```text
relevance = 0
```

sin importar lo buena que parezca su descripción.

El LLM judge no tendrá autoridad para ignorar restricciones verificables.

---

# 26. Responsabilidad del LLM durante la generación

El LLM podrá utilizarse para:

### Query verbalization

Transformar un seed estructurado en una consulta natural.

### Query diversification

Introducir diferentes formas de expresión:

```text
formal
casual
indirect
short
verbose
```

sin cambiar la intención.

### Semantic relevance judging

Evaluar correspondencia entre una query y la metadata/descripción de candidatos cuando ésta no pueda determinarse mediante reglas exactas.

### Query validation

Comprobar que una query generada mantiene la intención del seed.

---

# 27. Decisiones que el LLM no tomará

El LLM no decidirá:

```text
expected_route
expected_sources
hard constraints
fixture selection
source provenance
whether a structured candidate exists
eligible_item_ids when deterministically computable
```

Tampoco podrá inventar metadata para justificar un caso.

Principio:

> El LLM puede verbalizar o evaluar semántica; los hechos del dataset determinan el gold verificable.

---

# 28. Query Writer

Se definirá un prompt cuya única responsabilidad será convertir un seed estructurado en lenguaje natural.

Entrada:

```yaml
route: netflix

hard_constraints:
  type: movie
  genres:
    - action

semantic_concepts:
  - spies
  - undercover missions
```

Salida posible:

```text
"Can you recommend an action movie involving spies or undercover agents?"
```

El Query Writer deberá:

* preservar todas las restricciones;
* no añadir nuevas restricciones;
* no modificar el datasource esperado;
* no mencionar etiquetas internas;
* producir lenguaje natural;
* variar razonablemente la forma lingüística.

---

# 29. Query Critic

Después del Query Writer se utilizará un paso separado de validación.

El critic comparará:

```text
structured seed
vs
generated query
```

y comprobará al menos:

```text
constraints_preserved
constraints_added
semantic_drift
route_leakage
```

Una query fallará la validación si cambia el problema que se pretendía evaluar.

Por ejemplo, para un seed `BOTH`:

```text
"Recommend me a comedy"
```

sería apropiado.

Pero:

```text
"Search both TMDB and Netflix for a comedy"
```

no sería apropiado porque revela artificialmente al router cuál debe ser su salida.

---

# 30. Queries naturales, no queries diseñadas para pasar el test

El Silver Dataset debe parecerse razonablemente a consultas reales.

Se evitarán preguntas que expongan directamente las decisiones internas del sistema.

No:

```text
"Use the Netflix agent to retrieve..."
```

No:

```text
"This is a BOTH routing query..."
```

Sí:

```text
"Any good romantic movie?"
```

Sí:

```text
"What are some good Netflix nature documentaries?"
```

El objetivo es evaluar comprensión de intención, no reconocimiento de palabras artificiales del benchmark.

---

# 31. Diversidad de casos

Los casos no diferirán únicamente por género o título.

La matriz deberá contener variación en dificultad y formulación.

Tags orientativos:

```text
explicit
implicit
single_constraint
multi_constraint
hard_filter
semantic
mixed
noisy
boundary
no_results
```

Esto permitirá posteriormente analizar errores por grupos y no sólo mediante una métrica global.

---

# 32. Distribución conceptual por dificultad

Dentro de cada route se buscará una combinación de:

```text
easy
medium
hard
```

Ejemplos:

### Easy

```text
"Show me a Netflix comedy."
```

### Medium

```text
"I want an action movie involving spies."
```

### Hard

```text
"I'd like something about someone living undercover and beginning to question where their loyalties lie."
```

Los casos difíciles no deben introducir requisitos imposibles de comprobar.

---

# 33. Representación conceptual de un EvalCase

El schema definitivo se implementará posteriormente, pero conceptualmente un caso deberá contener información similar a:

```python
class EvalCase:
    id: str

    # Input
    query: str

    # Routing gold
    expected_route: str
    expected_sources: list[str]

    # Expected interpretation
    expected_trending_query: dict | None
    expected_netflix_query: dict | None

    # Candidate truth
    seed_item_ids: list[str]
    eligible_item_ids: list[str] | None
    relevance_judgments: dict[str, int]

    # Expected behaviour
    expected_status: str
    expected_source_separation: bool

    # Reproducibility
    source_fixture_id: str | None

    # Analysis
    difficulty: str
    tags: list[str]

    # Generation provenance
    generation_model: str
    generation_prompt_version: str
```

No todos los campos aplicarán a todas las routes.

---

# 34. Ejemplo de caso positivo Netflix

```yaml
id: netflix_017

query: >
  I'm looking for an action movie involving spies
  working undercover.

expected_route: netflix

expected_sources:
  - netflix

expected_netflix_query:
  type: movie
  genres:
    - action
  semantic_concepts:
    - espionage
    - undercover agents

seed_item_ids:
  - movie_0012

eligible_item_ids:
  - movie_0012
  - movie_0087
  - movie_0231

relevance_judgments:
  movie_0012: 3
  movie_0087: 3
  movie_0231: 2
  movie_0435: 1

expected_status: SUCCESS

difficulty: medium

tags:
  - hard_filter
  - semantic
  - multi_constraint
```

---

# 35. Ejemplo de caso `NO_RESULTS`

```yaml
id: netflix_041

query: >
  Do you have any movies starring Anthony Perkins?

expected_route: netflix

expected_sources:
  - netflix

expected_netflix_query:
  type: movie
  actors:
    - Anthony Perkins

seed_item_ids: []

eligible_item_ids: []

relevance_judgments: {}

expected_status: NO_RESULTS

difficulty: medium

tags:
  - hard_filter
  - person
  - no_results
```

Este caso sólo podrá incorporarse si el datasource permite verificar exhaustivamente el cast.

---

# 36. Ejemplo de caso `BOTH`

```yaml
id: both_008

query: >
  Can you recommend a good comedy?

expected_route: both

expected_sources:
  - tmdb
  - netflix

expected_source_separation: true

tmdb:
  fixture_id: tmdb_trending_v1
  seed_item_ids:
    - tmdb_123

netflix:
  seed_item_ids:
    - netflix_456

expected_status: SUCCESS

difficulty: easy

tags:
  - ambiguous_source
  - both
```

Los juicios de relevancia TMDB y Netflix permanecerán independientes.

---

# 37. Top-K de evaluación

La evaluación de retrieval utilizará inicialmente:

```text
K = 5
```

por fuente.

Esto permite comprobar si candidatos relevantes aparecen suficientemente arriba sin exigir que el primer resultado coincida con un único gold.

En `BOTH`:

```text
TMDB Top-5
```

y:

```text
Netflix Top-5
```

se medirán por separado.

No existe un `Top-10` combinado.

---

# 38. Relación con Hit@5

Una métrica especialmente adecuada para este diseño será:

```text
Hit@5
```

que responde:

> ¿Aparece al menos uno de los candidatos conocidos como relevantes entre los primeros cinco resultados?

Es útil porque no presupone que exista una única recomendación correcta.

---

# 39. Relación con nDCG@5

Si se dispone de juicios graduados suficientes:

```text
0 / 1 / 2 / 3
```

podrá calcularse:

```text
nDCG@5
```

para analizar la calidad del orden.

No obstante, nDCG sólo se utilizará si el Silver Dataset contiene suficientes juicios de relevancia para que la métrica resulte defendible.

No se generarán etiquetas artificiales únicamente para poder calcularla.

Por tanto:

```text
Hit@5
→ métrica sencilla y principal de recuperación

nDCG@5
→ métrica adicional si el gold graduado es suficientemente sólido
```

---

# 40. No se necesita identificar la mejor película de todo el catálogo

Esta es una decisión importante del diseño.

No se intentará realizar:

```text
Query
↓
inspect every movie
↓
choose objectively best movie
```

Eso sería:

* costoso;
* subjetivo;
* difícil de mantener;
* poco realista para un sistema de recomendación.

En su lugar:

```text
Hard constraints
        ↓
Eligible set

Semantic query
        ↓
Candidate pool
        ↓
Relevance judgments
```

La evaluación pregunta:

> ¿El sistema devuelve candidatos válidos y altamente relevantes?

No:

> ¿El sistema devuelve exactamente la película que nosotros elegimos?

---

# 41. Casos sin resultado como parte del comportamiento funcional

`NO_RESULTS` no será tratado como un error del sistema.

Es un posible resultado correcto.

Estados conceptuales:

```text
SUCCESS
NO_RESULTS
OUT_OF_SCOPE
...
```

Esto es especialmente importante para impedir que el modelo rellene huecos inventando recomendaciones.

El dataset debe contener ejemplos suficientes para comprobar esta propiedad.

---

# 42. Grounding del dataset

Todo título usado para generar un caso debe proceder de:

```text
TMDB fixture
```

o:

```text
Netflix dataset
```

No se aceptarán películas generadas desde el conocimiento interno del LLM.

De forma análoga, las restricciones estructuradas deben estar respaldadas por metadata real.

El LLM no constituye datasource.

---

# 43. Provenance

Cada caso debe guardar suficiente información para reconstruir cómo fue generado.

Como mínimo:

```text
case_id
generation_model
generation_prompt_version
source
fixture/version
seed_item_ids
```

Esto permitirá:

* reproducir generación;
* detectar cambios de prompt;
* comparar versiones del Silver Dataset;
* auditar casos dudosos.

---

# 44. Versionado

El dataset deberá versionarse.

Ejemplo conceptual:

```text
silver_v1
silver_v2
```

Una versión publicada no debería modificarse silenciosamente.

Si se corrige un caso o cambia su gold de forma significativa, deberá registrarse el cambio o producirse una nueva versión.

Esto es especialmente importante si se utilizan sus resultados para comparar diferentes implementaciones del sistema.

---

# 45. Qué no forma parte de esta fase

Esta fase define el diseño.

Queda explícitamente fuera:

```text
implementar el pipeline de generación
generar físicamente los 150 casos
ejecutar los agentes
calcular métricas reales
hacer tuning
realizar pruebas
```

La implementación del generador y la producción efectiva del dataset pertenecen a fases posteriores.

---

# 46. Decisiones cerradas

Quedan adoptadas las siguientes decisiones:

### D-01 — Silver Dataset único

Se utilizará un único conjunto versionado de 150 casos.

**Motivo:** evitar duplicación y permitir evaluación transversal de componentes.

---

### D-02 — Distribución por routes

```text
50 TRENDING
50 NETFLIX
25 BOTH
25 OUT_OF_SCOPE
```

**Motivo:** dar mayor cobertura a los dos agentes principales manteniendo suficientes casos para routing ambiguo y fuera de alcance.

---

### D-03 — Structured seed first

El caso estructurado se crea antes que la query.

**Motivo:** evitar que el LLM defina su propio ground truth.

---

### D-04 — Query generation asistida por LLM

El LLM verbaliza seeds ya definidos.

**Motivo:** obtener consultas naturales y variadas manteniendo control sobre la verdad esperada.

---

### D-05 — Query Critic separado

Las queries generadas se validan contra el seed.

**Motivo:** detectar pérdida de restricciones, restricciones inventadas, semantic drift o leakage de route.

---

### D-06 — Hard constraints separados de semantic intent

Los casos representarán explícitamente ambos tipos.

**Motivo:** permitir comprobaciones deterministas siempre que sea posible y reservar evaluación semántica para lo que realmente la necesita.

---

### D-07 — Hard constraints prioritarios

Una violación de filtro invalida un candidato.

**Motivo:** una alta similitud semántica no debe justificar incumplir una petición explícita.

---

### D-08 — Seed items como anclas, no como única respuesta

Los títulos utilizados para crear la query no constituyen necesariamente la única ni la mejor respuesta.

**Motivo:** un recomendador admite múltiples respuestas correctas.

---

### D-09 — Eligible sets deterministas

Cuando una restricción sea verificable, su conjunto de candidatos se calculará directamente desde los datos.

**Motivo:** utilizar ground truth objetivo siempre que esté disponible.

---

### D-10 — Candidate pooling para semántica

No se juzgará todo el catálogo.

Se construirá un pool de candidatos plausibles procedentes de diferentes estrategias y de los seeds conocidos.

**Motivo:** hacer viable el relevance judging sin convertir un único retriever en ground truth.

---

### D-11 — Relevancia graduada

Cuando sea necesario se utilizará:

```text
0 = irrelevant
1 = weak
2 = relevant
3 = highly relevant
```

**Motivo:** permitir evaluar no sólo presencia sino calidad del ranking.

---

### D-12 — Casos `NO_RESULTS` generados deliberadamente

Se incluirán queries cuyo conjunto de candidatos válidos sea vacío y esté verificado.

**Motivo:** evaluar abstención y detectar recomendaciones inventadas o relajaciones silenciosas.

---

### D-13 — Metadata verificable únicamente

No se generarán hard constraints que el datasource no permita comprobar.

**Motivo:** el benchmark no debe exigir al sistema información que sus fuentes no contienen.

---

### D-14 — Actors/directors condicionados al datasource

Se utilizarán como filtros únicamente si el dataset real proporciona metadata fiable para ellos.

**Motivo:** permitir casos como `Anthony Perkins → NO_RESULTS` sin utilizar conocimiento externo del LLM.

---

### D-15 — TMDB mediante fixtures

Los casos `TRENDING` se anclarán a fixtures versionados del endpoint permitido.

**Motivo:** hacer reproducible una fuente cuya información live cambia continuamente.

---

### D-16 — Netflix mediante registros reales

Los seeds Netflix procederán del catálogo real utilizado por el agente.

**Motivo:** impedir títulos o propiedades inventadas.

---

### D-17 — BOTH mantiene dos gold independientes

TMDB y Netflix se evaluarán por separado incluso cuando ambas fuentes se ejecuten.

**Motivo:** sus señales de relevancia no son directamente comparables.

---

### D-18 — Sin ranking global de fuentes

No habrá una verdad tipo:

```text
TMDB movie > Netflix movie
```

**Motivo:** no existe un score común que justifique esa comparación.

---

### D-19 — Top-K inicial igual a 5

La recuperación se evaluará inicialmente sobre los cinco primeros candidatos de cada fuente.

**Motivo:** equilibrar utilidad práctica y capacidad de medir resultados relevantes sin depender del Top-1.

---

### D-20 — Hit@5 como métrica sencilla de recuperación

Se utilizará para comprobar si aparece al menos un resultado conocido como relevante.

**Motivo:** funciona bien cuando existen múltiples respuestas válidas.

---

### D-21 — nDCG@5 sólo con gold suficiente

Se utilizará únicamente cuando existan juicios graduados sólidos.

**Motivo:** evitar introducir una métrica sofisticada apoyada en etiquetas débiles o artificiales.

---

### D-22 — Provenance obligatoria

Cada caso conservará información sobre seed, fixture, modelo y versión del prompt.

**Motivo:** reproducibilidad y auditoría.

---

### D-23 — Dataset versionado

Las versiones utilizadas para comparar sistemas permanecerán congeladas.

**Motivo:** hacer comparables los resultados entre iteraciones.

---

# 47. Decisiones que permanecen por concretar durante la implementación del generador

El diseño conceptual está cerrado, pero algunos parámetros sólo podrán fijarse correctamente después de inspeccionar los datos reales.

En particular:

### Metadata Netflix disponible

Debe verificarse definitivamente qué atributos pueden utilizarse como hard filters, especialmente:

```text
actors
directors
```

### Tamaño exacto del candidate pool

Se ha definido la estrategia de pooling, pero el número exacto de candidatos que se juzgarán podrá ajustarse en función del catálogo y del coste de generación.

### Cuota exacta de `NO_RESULTS`

Se ha decidido que deben existir deliberadamente, pero todavía no se ha fijado cuántos de los 150 casos pertenecerán a este comportamiento.

### Uso definitivo de nDCG

Dependerá de la calidad y cobertura de los relevance judgments obtenidos.

Estas decisiones no modifican la arquitectura del dataset y pueden cerrarse de forma empírica durante su construcción.

---

# 48. Flujo final de generación

El proceso completo queda conceptualmente definido como:

```text
                SOURCE DATA
             ↙              ↘
      TMDB fixtures      Netflix dataset
             ↓              ↓
       select seed       select seed
             ↘              ↙
            STRUCTURED INTENT
                   ↓
       determine hard constraints
                   ↓
      compute eligible set if possible
                   ↓
         define semantic concepts
                   ↓
              QUERY WRITER
                   ↓
           natural user query
                   ↓
              QUERY CRITIC
                   ↓
            accepted query
                   ↓
       candidate pool when needed
                   ↓
        relevance judgments
                   ↓
             FINAL EVAL CASE
                   ↓
          versioned Silver Dataset
```

---

# 49. Infraestructura de datos para generación del Silver Dataset

El flujo de generación descrito en la sección 48 se apoya en una infraestructura concreta de datos implementada en el proyecto:

**Pipeline ETL (`src/moviebot/etl/`):**
El módulo ETL transforma los CSVs crudos de Netflix (`titles.csv`, `credits.csv`) en un dataset canónico versionado (`data/processed/netflix/{version}/titles.jsonl` + `metadata.json`). Este proceso normaliza tipos, géneros, nombres de actores/directores, realiza joins de créditos, deduplica y valida registros. El resultado es un artefacto determinista y reproducible.

**`CanonicalNetflixAdapter` (`src/moviebot/evals/silver/adapters.py`):**
Reemplaza al adaptador basado en CSV para la generación de seeds. Lee desde el dataset canónico producido por el ETL y provee filtrado exhaustivo para computar ground truth (`eligible_item_ids`). Soporta filtros por type, genres, year range, actors y directors. Toda la normalización ya fue resuelta por el ETL — el adapter simplemente consume el JSONL canónico.

**`MeilisearchIndexer` (`src/moviebot/indexer/meilisearch_indexer.py`):**
Ingesta el mismo dataset canónico en un índice Meilisearch versionado (`netflix_{version}`) para el retrieval runtime del agente Netflix. Configura actors y directors como filtrables y searchables.

**`MeilisearchNetflixRepository` (`src/moviebot/repositories/netflix_meilisearch.py`):**
Implementación concreta de `NetflixRepository` que traduce `NetflixQuery` a búsquedas Meilisearch. Soporta filtros de genres (AND semántica), actors (OR), directors (OR). Es el componente que el agente Netflix usa en runtime.

**`BatchGenerator` (`src/moviebot/evals/silver/batch_generator.py`):**
Orquesta la generación determinista de los 150 seeds. Lee un catálogo declarativo (`config/evals/silver_v1/case_catalog.json`), valida distribución (50/50/25/25), cuotas de NO_RESULTS, y existencia de todos los IDs referenciados. Delega la construcción individual a `SeedBuilder` y la persistencia a `SeedPersistence`.

**Relación con la separación Ground Truth vs Retrieval (sección 23):**
- Ground truth → `CanonicalNetflixAdapter.filter()` (iteración exhaustiva sobre JSONL)
- Retrieval → `MeilisearchNetflixRepository.search()` (consulta al motor de búsqueda)

Ambos operan sobre el mismo dataset canónico pero con propósitos distintos, manteniendo la independencia entre evaluación y runtime definida en las decisiones D-09 y D-23.

---

# 50. Resultado final

El Silver Evaluation Dataset se diseñará alrededor de una idea central:

> **No necesitamos conocer una única "mejor película" para cada consulta. Necesitamos conocer qué restricciones deben cumplirse, qué candidatos son válidos, cuáles son relevantes y cuándo la respuesta correcta es no recomendar nada.**

Esto permite construir una evaluación defendible incluso sobre catálogos grandes.

El dataset combina:

```text
deterministic gold
+
controlled synthetic queries
+
real datasource items
+
semantic relevance judgments
+
explicit NO_RESULTS cases
+
source-aware evaluation
```

El resultado será un benchmark diseñado para medir el comportamiento real del sistema sin convertir las preferencias subjetivas de un generador LLM en una falsa verdad absoluta.
