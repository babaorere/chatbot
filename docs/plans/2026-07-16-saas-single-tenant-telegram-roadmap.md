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

## Decisiones operativas confirmadas

- La clave inicial funcionará como medida de seguridad y credencial de entrada
  al frontend del tenant.
- Telegram se conectará durante desarrollo mediante un túnel público HTTPS.
- La activación de cada tenant será una acción del administrador de la
  plataforma.
- El administrador de la plataforma tendrá control global.
- El administrador del tenant tendrá control completo sobre la configuración y
  operación de su propio negocio, sin acceso a otros tenants ni a la
  plataforma global.
- Cada tenant tendrá su propio archivo `docker-compose.yml`.
- El tenant podrá modificar la información y configuración autorizada de su
  negocio desde su frontend.
- La suspensión podrá aplicar una o más acciones: bloquear acceso, desactivar
  Telegram, detener contenedores y conservar o restringir datos, según la
  decisión del administrador.
- Se aceptan límites técnicos internos para prevenir abuso, bucles de mensajes
  y costos inesperados, aunque no se anuncie un límite comercial al cliente.

## Confirmaciones adicionales

- Cloudflare Tunnel es el túnel previsto para el desarrollo local y ya está
  definido en el Compose de referencia.
- El frontend central del administrador será una aplicación independiente,
  ejecutada en otro Docker Compose y con su propia base de datos.
- Cada instalación de tenant tendrá su propio Compose, frontend administrativo,
  API, PostgreSQL, Redis y configuración de Telegram.
- Cada instalación tendrá nombres de proyecto, puertos y volúmenes aislados
  para permitir varios tenants locales simultáneos.
- El ciclo de vida inicial del tenant usará estados explícitos como
  `pending`, `active`, `suspended` y `decommissioned`. `decommissioned`
  conserva los datos y representa una instalación retirada o inactiva, no una
  eliminación irreversible.

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

## Revisión del `chatbot` existente

El proyecto actual ya contiene piezas reutilizables, pero no deben trasladarse
sin revisión:

- `docker-compose.yml` local con API, worker, PostgreSQL, Redis, Nginx y
  Cloudflare Tunnel;
- `Dockerfile.postgres` basado en `postgres:18-alpine` y con pgvector;
- frontend administrativo en `/admin/`;
- frontend de tenant en `/tenant/`;
- autenticación de tenant mediante invitaciones, hash de tokens, contraseñas,
  sesiones y cookies HttpOnly;
- endpoints administrativos protegidos por una clave global;
- límites de frecuencia configurados en Nginx.

La configuración de producción actual usa Redis externo en algunos servicios,
por lo que no debe copiarse directamente al objetivo inicial. Para esta etapa
se mantiene Redis dentro del Compose de cada tenant.

## Revisión del `.env` de referencia

El `.env` actual contiene variables mezcladas de varias responsabilidades:

### Por tenant

- nombre y slug del negocio;
- configuración comercial básica;
- token del bot de Telegram;
- `DATABASE_URL`, usuario, contraseña y nombre de base;
- `REDIS_URL` y namespace;
- `ALLOWED_ORIGINS`;
- estado y configuración del tenant.

### Por instalación o seguridad del tenant

- `JWT_SECRET`;
- clave de activación o administración local;
- secretos Docker;
- credenciales de base de datos;
- credenciales del túnel si cada Compose posee su propio túnel.

### De plataforma o proveedor

- claves de modelos y embeddings;
- modelo principal y modelos de fallback;
- políticas de costo y uso;
- observabilidad central, si se agrega posteriormente.

### Variables que requieren revisión

`DEFAULT_TENANT_*`, `TENANT_PORTAL_*`, `ADMIN_PORTAL_*`, `REDIS_UPSTASH_*` y
claves de proveedores aparecen en el entorno de referencia, pero no todas están
consumidas por el código actual. No deben formar parte del contrato final hasta
confirmar su uso o eliminarlas.

La configuración final debe tener un `.env.example` sin secretos, secretos
Docker separados y un inventario que indique si cada variable pertenece a la
plataforma, a la instalación o al tenant.

No se debe copiar el `.env` real al repositorio ni a un nuevo tenant. Los
secretos que hayan sido expuestos durante pruebas deben rotarse antes de usar
la instalación fuera del entorno local.

## Primera etapa prioritaria

La primera implementación debe ser el **vertical slice de activación y
aislamiento de un tenant**, no RAG ni voz.

Debe probar:

1. levantar un Compose local limpio;
2. activar un tenant mediante una clave inicial;
3. obligar al tenant a crear su credencial propia;
4. acceder al frontend administrativo del tenant;
5. configurar un bot Telegram propio;
6. registrar el webhook mediante Cloudflare Tunnel;
7. recibir un mensaje y asociarlo a esa instalación;
8. suspender el tenant y verificar que acceso, bot y servicios respeten el
   estado elegido;
9. conservar datos y poder reactivar desde un respaldo.

Si este flujo no es sólido, cualquier reutilización de Telegram, RAG o voz
trasladaría la arquitectura fragmentada del proyecto existente al nuevo
producto.

## Decisiones pendientes

1. ¿La clave inicial será de un solo uso y obligará a crear una contraseña
   propia? Recomendación: sí; la clave no debería quedar como contraseña
   permanente ni almacenarse en texto plano.
2. ¿El túnel local será Cloudflare Tunnel u otra herramienta equivalente?
3. ¿Existirá un frontend central del administrador de la plataforma, separado
   del frontend administrativo de cada tenant?
4. ¿La creación del `docker-compose.yml`, volúmenes, credenciales y túnel será
   manual en la primera etapa o se automatizará desde el panel central?
5. ¿La suspensión debe conservar los datos para reactivación y respaldos, o
   también podrá ordenar una eliminación irreversible con confirmación?
6. ¿Qué límites técnicos iniciales aceptamos para mensajes, tamaño, frecuencia
   y consumo del modelo?
7. ¿Qué proveedor de túnel y dominio usaremos para que cada tenant tenga una
   URL estable de webhook?
8. ¿Qué partes concretas del proyecto `chatbot` deseas evaluar primero como
   referencia: Telegram, autenticación, RAG, frontend tenant o despliegue?

## Separación de aplicaciones

La aplicación central debe crearse como un proyecto hermano independiente:

```text
/home/manager/Sync/python_proyects/voiceshop-control-plane/
```

Su responsabilidad será administrar la plataforma:

- registro de tenants;
- claves de activación;
- estados `pending`, `active`, `suspended` y `decommissioned`;
- usuarios administradores de la plataforma;
- metadatos de cada instalación;
- referencias a Compose, puertos, dominios, túneles y respaldos;
- auditoría de activaciones y suspensiones.

Su propio stack tendrá frontend central, API y PostgreSQL independiente.

`chatbot` conservará el runtime que se ejecuta dentro de cada tenant:

- frontend administrativo del negocio;
- API de atención;
- PostgreSQL propio;
- Redis propio;
- worker;
- bot Telegram;
- base de conocimiento y RAG.

`web_promotion` seguirá siendo únicamente la página comercial.

En la primera etapa el control plane no debe recibir acceso directo al socket
Docker para crear contenedores automáticamente. La creación de los Compose de
tenant será manual y el control plane registrará el estado y los metadatos. La
automatización de Docker se evaluará después de definir sus límites de
seguridad.

## Regla para reutilizar el proyecto existente

El proyecto `chatbot` se considera una fuente de ideas y código candidato, no
una base que deba copiarse completa. Antes de incorporar cualquier módulo se
debe revisar:

- responsabilidad del módulo;
- dependencias;
- límites entre dominio, aplicación e infraestructura;
- aislamiento por tenant;
- compatibilidad con el contrato de esta hoja de ruta;
- pruebas existentes;
- deuda técnica que se estaría trasladando.

Ninguna pieza se incorpora sin una decisión explícita y una prueba que demuestre
que queda acoplada correctamente.

## Regla de avance

No se inicia una etapa nueva mientras la anterior no tenga:

- implementación ejecutable;
- pruebas automatizadas;
- prueba manual documentada;
- criterios de aceptación cumplidos;
- riesgos conocidos;
- costo operativo estimado;
- procedimiento de rollback o recuperación cuando corresponda.
