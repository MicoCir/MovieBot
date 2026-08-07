# Borrador de Fases - MovieBot (Clarity.ai)

## Fase 0 - Diseño y Planificación
- Pensar cada pieza
- RAG: 
    - Pensar un reranker para cada uno
    - Pensar filtrado con IA
    - TMDB: definir schema de filtros
    - Netflix: definir schema "query + filtros"
- Pensar cómo se van a comunicar (contrato de datos)
- Pensar arquitectura del Agente
  - ¿Qué se descarta y por qué?
    - ¿LangChain?
    - ¿Planificador?
- Descargar Mirror TMDB (3 meses)
- Descargar Dataset Kaggle Netflix

## Fase 1 - Pipeline de Evaluación
- Definir schema del dataset
- Definir métricas
- Definir matriz de casos
- Definir pipeline de generación
- Definir objetivo de cada Prompt
- Montar pipeline
- Hacer algunas pruebas

## Fase 2 - Generar Dataset
- 50 TMDB (endpoint tool)
- 50 Netflix
- 25 Desambiguar / enrutador
- 25 Out of scope / enrutador

## Fase 3 - Netflix
- Descargar dataset
- Descargar preprocesador Kaggle
- Ingestar a Meili
- Crear función para probar dataset
  - Asistente as tool
  - Probar traducción query

## Fase 4 - TMDB
- Descargar Mirror
- Setear como "Mock"
- Crear función para probar dataset
  - Asistente as tool
  - Probar traducción query

## Fase 5 - Enrutador
- Montar clasificador de intenciones
- Probar enrutador

## Fase 6 - Integración
- Conectar enrutador a asistentes como tool
- Probar
