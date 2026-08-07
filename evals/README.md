# Evaluación — MovieBot

Este directorio contiene la infraestructura de evaluación del proyecto MovieBot.

## Estructura planificada

### `datasets/`

Matrices de evaluación del router y agentes. Contiene datasets estructurados para medir la calidad de las decisiones de enrutamiento y las recomendaciones generadas por cada agente especializado (TMDB, Netflix).

Se creará en fases posteriores cuando exista lógica de negocio que evaluar.

### `fixtures/tmdb/`

Respuestas versionadas del endpoint trending de TMDB para tests deterministas. Permite ejecutar evaluaciones reproducibles sin depender de la disponibilidad o el estado actual de la API externa.

Se creará en fases posteriores cuando se implemente el agente TMDB.

---

> **Nota:** Los subdirectorios no se crean vacíos porque Git no los rastrea. Se crearán cuando se agregue contenido real en fases posteriores.
