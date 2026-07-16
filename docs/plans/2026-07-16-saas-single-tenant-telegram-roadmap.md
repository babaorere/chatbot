# VoiceShop SaaS: hoja de ruta por etapas

## Decisión de producto

VoiceShop se desarrollará como un SaaS orientado inicialmente a negocios que
reciben consultas por Telegram.

La unidad de aislamiento será el tenant:

- cada tenant tendrá su propia instalación ejecutándose en Docker;
- cada instalación tendrá su propia base de datos PostgreSQL;
- cada instalación se desplegará separadamente en la nube;
- cada tenant podrá tener varios usuarios internos y clientes finales;
- Telegram será el primer canal de atención;
- Redis funcionará dentro del mismo stack Docker del tenant;
- PostgreSQL utilizará `postgres:18-alpine` como imagen objetivo.

## Decisiones confirmadas

- La primera ejecución será local mediante Docker Compose.
- La migración a VPS se realizará después de validar el flujo local.
- Cada tenant tendrá su propio bot y token de Telegram.
- El administrador configurará el bot desde el frontend administrativo del
  tenant; el token debe llegar y permanecer únicamente en el backend.
- Los clientes finales interactuarán solo por Telegram durante la primera
  etapa.
- El tenant tendrá un frontend administrativo propio.
- El administrador de la plataforma entregará una clave al tenant y podrá
  activar, suspender o mantener inactivo ese tenant.
- No se definirá por ahora un límite comercial visible de mensajes mensuales.
  Esto no elimina los límites técnicos internos de seguridad y costos.

La frase “Redis en el mismo Docker” se interpreta aquí como “en el mismo
stack Docker Compose”, pero en un contenedor separado de PostgreSQL y de la
API. No se recomienda poner API, PostgreSQL y Redis en un único contenedor.

## Alcance inicial

La primera versión debe demostrar únicamente este flujo:

```text
Cliente escribe por Telegram
    -> webhook recibe el mensaje
    -> se identifica el tenant
    -> se consulta información aprobada
    -> se responde por Telegram
    -> se deriva a una persona cuando corresponde
```

Quedan fuera de la primera etapa:

- WhatsApp;
- voz o Realtime;
- pagos;
- stock en tiempo real;
- carrito y pedidos;
- integraciones ERP/CRM;
- automatización de decisiones comerciales;
- despliegues multi-tenant dentro de una misma base de datos.

## Etapas de implementación

### Etapa 0: contrato técnico y entorno reproducible

Objetivo: ejecutar una instalación aislada de un tenant de forma repetible.

Incluye:

- Docker Compose;
- API FastAPI;
- PostgreSQL 18 Alpine;
- Redis en contenedor separado;
- variables de entorno y secretos fuera del código;
- healthchecks;
- migraciones;
- volúmenes persistentes;
- respaldo y restauración básica.

Criterio de avance: una instalación limpia inicia, verifica salud de API,
PostgreSQL y Redis, permite configurar un tenant y puede restaurarse desde un
respaldo de prueba.

### Etapa 1: Telegram y atención básica

Objetivo: completar un flujo de atención real para un tenant.

Incluye:

- un bot de Telegram por tenant, configurado desde el frontend administrativo;
- webhook seguro;
- recepción y envío de mensajes;
- identificación de conversación y usuario;
- configuración básica del negocio;
- respuesta de preguntas frecuentes;
- derivación a una persona;
- registro de mensajes y errores;
- fallback claro cuando no existe información suficiente.

Criterio de avance: un tenant activo puede configurar su bot, un cliente puede
preguntar por Telegram, recibir una respuesta basada en información aprobada y
ser derivado sin perder el contexto.

### Etapa 2: base de conocimiento y RAG controlado

Objetivo: mejorar la recuperación sin convertir el RAG en fuente de datos
transaccionales.

Incluye:

- carga, edición, activación y desactivación de información;
- categorías de conocimiento;
- búsqueda FTS en español;
- evaluación de recuperación con preguntas reales;
- decisión explícita sobre activar búsqueda híbrida FTS + pgvector;
- política que excluya stock, precios vivos, pedidos y pagos;
- pruebas contra respuestas inventadas o fuera de contexto.

Criterio de avance: las consultas permitidas recuperan información relevante y
las consultas transaccionales se derivan a funciones o a una persona.

### Etapa 3: usuarios internos y operación del tenant

Objetivo: permitir que varias personas administren el mismo tenant sin perder
aislamiento.

Roles iniciales sugeridos:

- administrador del tenant;
- operador de atención;
- usuario de solo lectura;
- cliente final de Telegram, sin acceso administrativo.

Incluye:

- autenticación;
- autorización por tenant;
- revisión de conversaciones;
- handoff humano;
- auditoría;
- configuración de horarios, mensajes y categorías;
- límites de uso por tenant.

Criterio de avance: dos usuarios internos pueden operar el mismo tenant con
permisos diferentes y sin acceder a datos de otro tenant.

### Etapa 4: piloto controlado

Objetivo: probar el servicio con un tenant real antes de ampliar funciones.

Medir:

- número de consultas recibidas;
- consultas respondidas con información aprobada;
- derivaciones a persona;
- consultas sin respuesta suficiente;
- errores técnicos;
- tiempo de respuesta;
- cambios solicitados por el negocio.

Criterio de avance: existe evidencia de funcionamiento y una lista priorizada
de fallos, sin presentar el piloto como caso de éxito antes de validarlo.

### Etapa 5: canales y funciones superiores

Solo después del piloto:

1. WhatsApp.
2. Atención por voz desde la web.
3. Catálogo y precios con fuentes autorizadas.
4. Stock y pedidos mediante herramientas del backend.
5. Pagos e integraciones externas.

Cada función debe tener su propio contrato, permisos, pruebas e impacto de
costos. No se incorpora por defecto al plan inicial.

## Arquitectura de despliegue objetivo

```text
Tenant A
  Docker Compose A
  ├── API FastAPI
  ├── Worker
  ├── PostgreSQL 18 Alpine
  ├── Redis
  └── Nginx / HTTPS / webhook Telegram

Tenant B
  Docker Compose B
  ├── API FastAPI
  ├── Worker
  ├── PostgreSQL 18 Alpine
  ├── Redis
  └── Nginx / HTTPS / webhook Telegram
```

Cada tenant debe poseer credenciales, volúmenes, backups, logs y dominio o
ruta de webhook aislados. El despliegue separado reduce el riesgo de fuga de
datos, pero aumenta el costo operativo y la complejidad de actualizaciones.

## Decisiones pendientes

1. ¿La clave entregada al tenant será de un solo uso y obligará a crear una
   credencial propia?
2. ¿El bot se conectará mediante webhook público o polling durante el trabajo
   local? Un webhook requiere una URL HTTPS accesible desde Telegram.
3. ¿La activación del tenant será manual por el administrador o existirá un
   flujo de aprobación desde el panel principal?
4. ¿Qué roles administrativos tendrá inicialmente el tenant: administrador,
   operador y solo lectura?
5. ¿Cada tenant tendrá un `docker-compose.yml` y un volumen PostgreSQL propios,
   o se usará un único Compose local para levantar varias instalaciones?
6. ¿Qué información debe poder cambiar el tenant sin intervención del
   administrador: preguntas frecuentes, horarios, mensajes, usuarios y bot?
7. ¿Qué acción se ejecutará cuando un tenant sea suspendido: detener Docker,
   desactivar el bot, bloquear el acceso o las tres?
8. Aunque no exista un límite comercial visible, ¿aceptamos límites técnicos
   internos para proteger el servicio ante abuso, bucles o costos inesperados?

## Regla de avance

No se inicia una etapa nueva mientras la anterior no tenga:

- implementación ejecutable;
- pruebas automatizadas;
- prueba manual documentada;
- criterios de aceptación cumplidos;
- riesgos conocidos;
- costo operativo estimado;
- procedimiento de rollback o recuperación cuando corresponda.
