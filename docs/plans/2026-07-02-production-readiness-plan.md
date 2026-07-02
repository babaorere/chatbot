# Plan: Production Readiness del Sistema

**Fecha:** 2026-07-02  
**Estado:** En preparación

## Objetivo

Dejar el sistema listo para operar en producción con criterios verificables de estabilidad, observabilidad, recuperación, seguridad y despliegue repetible.

## Alcance

Este plan cubre:

- backend Python
- flujo Telegram
- workers ARQ
- PostgreSQL
- Redis
- Docker / despliegue
- pruebas automáticas
- observabilidad y operación

No introduce una nueva arquitectura. Solo endurece lo existente hasta un nivel apto para producción real.

## Criterio de "listo para producción"

El sistema se considera apto cuando cumple todo lo siguiente:

- responde de forma estable bajo tráfico normal
- falla de forma explícita, no silenciosa
- registra eventos suficientes para diagnosticar incidentes
- recupera estado después de reinicios
- mantiene integridad de datos
- puede desplegarse y revertirse sin intervención manual compleja
- tiene cobertura de pruebas sobre caminos felices y fallas críticas

## Checklist general

### 1. Código y arquitectura

- [ ] Confirmar que no existan imports lazy innecesarios.
- [ ] Confirmar que las dependencias se inyectan de forma explícita.
- [ ] Verificar que no haya fallas silenciosas ni `except: pass`.
- [ ] Verificar que los payloads a workers sean serializables.
- [ ] Verificar que los jobs sean idempotentes o seguros ante reintentos.
- [ ] Verificar que cada worker abra su propia sesión de base de datos.
- [ ] Confirmar que los errores de infraestructura se propaguen con excepción explícita.
- [ ] Revisar que no quede código obsoleto de la migración anterior.

### 2. Flujo Telegram

- [ ] Confirmar que `/start` sea directo y de baja latencia.
- [ ] Confirmar que la validación de webhook rechace payloads inválidos sin romper el proceso.
- [ ] Confirmar que los callbacks manejen estados inconsistentes sin corrupción.
- [ ] Confirmar que la FSM persista contexto válido y rechace estados corruptos.
- [ ] Confirmar que los mensajes de error al usuario sean formales y comprensibles.

### 3. LLM y alertas

- [ ] Confirmar que la falla del LLM dispare alerta asincrónica.
- [ ] Confirmar que la latencia alta dispare alerta asincrónica.
- [ ] Confirmar que la ausencia de ARQ no se oculte.
- [ ] Confirmar que el pipeline falle rápido si la cola crítica no está disponible.
- [ ] Confirmar que el código de alertas no bloquee la respuesta principal.

### 4. Datos y persistencia

- [ ] Confirmar que PostgreSQL esté configurado con variables reales de producción.
- [ ] Confirmar que Redis esté disponible para sesión, locks y cola.
- [ ] Confirmar que las sesiones se recuperen tras reinicio.
- [ ] Confirmar que no exista dependencia de memoria local para estado conversacional.
- [ ] Confirmar que las migraciones estén aplicadas y sin drift.
- [ ] Confirmar que los secretos no vivan dentro del repositorio.

### 5. Docker y runtime

- [ ] Confirmar que `core/Dockerfile` use una base mínima compatible.
- [ ] Confirmar que `docker-compose` no use campos obsoletos.
- [ ] Confirmar que los servicios arranquen en el orden correcto.
- [ ] Confirmar que los healthchecks reflejen estado real.
- [ ] Confirmar que los contenedores se reinicien correctamente ante fallo.
- [ ] Confirmar que las variables de entorno de producción estén documentadas.

### 6. Observabilidad

- [ ] Confirmar timestamps útiles en logs.
- [ ] Confirmar correlación por sesión / usuario / request.
- [ ] Confirmar logs de error con contexto suficiente.
- [ ] Confirmar que healthcheck diferencie Redis caído, heartbeat corrupto y worker ausente.
- [ ] Confirmar que existan métricas o trazas mínimas para diagnóstico.
- [ ] Confirmar que el nivel de log en producción no oculte incidentes.

### 7. Seguridad

- [ ] Confirmar validación estricta del token de Telegram.
- [ ] Confirmar que no se expongan secretos en respuestas o logs.
- [ ] Confirmar que la configuración sensible venga de entorno seguro.
- [ ] Confirmar que las rutas administrativas estén protegidas.
- [ ] Confirmar que no haya endpoints de debug activos en producción.

### 8. Pruebas

- [ ] Mantener la suite verde con warnings tratados como error cuando aplique.
- [ ] Cubrir happy path principal del bot.
- [ ] Cubrir fallas de Redis.
- [ ] Cubrir fallas de ARQ.
- [ ] Cubrir fallas de LLM.
- [ ] Cubrir inconsistencias de FSM.
- [ ] Cubrir invalidaciones de webhook.
- [ ] Cubrir healthcheck corrupto y ausente.
- [ ] Cubrir transporte Telegram roto.
- [ ] Cubrir regresiones por imports o wiring.

### 9. Despliegue

- [ ] Ejecutar deploy reproducible desde cero.
- [ ] Verificar arranque limpio del backend.
- [ ] Verificar arranque limpio del worker.
- [ ] Verificar que el webhook de Telegram responda correctamente.
- [ ] Verificar que la aplicación soporte restart sin pérdida crítica.
- [ ] Verificar rollback funcional.
- [ ] Verificar que el entorno elegido sea adecuado para producción.

## Orden de ejecución recomendado

### Fase 1: Congelar la base operativa

- revisar cambios pendientes
- eliminar residuos obvios de desarrollo
- validar dependencias y Docker
- confirmar que el entorno local y CI usan la misma base

### Fase 2: Endurecer caminos críticos

- webhook Telegram
- `/start`
- procesamiento de mensaje
- encolado de alertas
- healthcheck

### Fase 3: Observabilidad y operación

- logs con timestamp y contexto
- health snapshots claros
- trazabilidad por sesión
- errores explícitos

### Fase 4: Pruebas de resistencia

- fallas de Redis
- fallas de ARQ
- fallas del LLM
- payloads corruptos
- estados inconsistentes

### Fase 5: Despliegue controlado

- levantar ambiente de staging o preproducción
- validar deploy limpio
- validar restart limpio
- validar rollback
- validar comportamiento bajo carga normal

## Riesgos abiertos

- persistencia del entorno si se usa una capa gratuita con límites de plataforma
- latencia externa del proveedor LLM
- fallas transitorias de red entre Telegram, Redis y el backend
- rotación o expiración de secretos de terceros

## Evidencia mínima antes de declarar producción

- suite completa verde
- pruebas de fallas críticas verdes
- despliegue reproducible probado
- logs útiles confirmados
- healthcheck confiable
- configuración sensible fuera del código
- workers y backend operando juntos sin errores silenciosos

## Definición de terminado

El sistema se considera listo para producción cuando cada ítem de esta checklist esté verificado y documentado, y no queden dudas sobre:

- arranque
- recuperación
- observabilidad
- seguridad
- despliegue
- rollback
- resiliencia ante fallos críticos

