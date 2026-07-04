# Tenant Auth Migration Plan

Fecha: 2026-07-03

## Objetivo

Endurecer el acceso al panel tenant sin romper el panel actual durante el despliegue:

- invitacion temporal de 6 horas
- activacion inicial con contrasena fuerte
- sesion con access token JWT corto y refresh token rotatorio en cookies `HttpOnly`
- proteccion real de `/business/me/*`
- administracion de accesos desde `/admin`

## Estado implementado

Backend:

- Nuevas tablas:
  - `tenant_portal_users`
  - `tenant_portal_invites`
  - `tenant_portal_sessions`
- Nuevas rutas:
  - `POST /tenant-auth/invites/claim`
  - `POST /tenant-auth/login`
  - `POST /tenant-auth/refresh`
  - `POST /tenant-auth/logout`
  - `GET /tenant-auth/me`
  - `POST /tenant-auth/password/change`
  - `GET /admin/tenant-access/users`
  - `GET /admin/tenant-access/invites`
  - `POST /admin/tenant-access/invites`
  - `POST /admin/tenant-access/invites/{invite_id}/revoke`
  - `POST /admin/tenant-access/users/{user_id}/disable`
- Rutas protegidas:
  - `/business/me/*` requiere sesion tenant valida
  - `/categories/*` requiere sesion tenant o `X-Admin-API-Key`

Frontend:

- Admin:
  - nueva seccion `Acceso Tenant`
  - emision y revocacion de invitaciones
  - listado de usuarios tenant
- Tenant:
  - overlay de login
  - overlay de claim por invitacion
  - refresh automatico de sesion
  - logout
  - requests con `credentials: 'include'`

## Esquema SQL

### `tenant_portal_users`

- `id` integer PK
- `email` unique, indexed
- `full_name`
- `role` (`owner|manager|staff`)
- `status`
- `password_hash`
- `auth_version`
- `mfa_enabled`
- `created_at`, `updated_at`
- `password_set_at`, `last_login_at`, `disabled_at`

### `tenant_portal_invites`

- `id` uuid string PK
- `email`
- `full_name`
- `role`
- `token_hash` unique, indexed
- `expires_at`
- `max_attempts`, `attempt_count`
- `created_by_admin_id`
- `created_at`, `used_at`, `revoked_at`

### `tenant_portal_sessions`

- `id` uuid string PK
- `user_id` FK -> `tenant_portal_users.id`
- `refresh_token_hash` unique, indexed
- `user_agent`, `ip_address`
- `issued_at`, `expires_at`, `last_seen_at`
- `rotated_from_session_id`
- `revoked_at`

## Secuencia exacta de migracion

1. Desplegar backend con las nuevas tablas y rutas.
2. Verificar que `Base.metadata.create_all()` cree `tenant_portal_*`.
3. Confirmar que `JWT_SECRET` y `ADMIN_API_KEY` esten configurados.
4. Desplegar frontend admin con la seccion `Acceso Tenant`.
5. Desplegar frontend tenant con overlay de login y claim.
6. Crear la primera invitacion desde admin.
7. Canjear invitacion en `/tenant/?invite=<token>`.
8. Confirmar que:
   - se crea `tenant_portal_user`
   - se consume la invitacion
   - se crea `tenant_portal_session`
   - `/business/me/profile` responde con sesion valida
9. Solo despues de esta validacion considerar obligatorio el nuevo flujo en operacion.

## Por que no rompe el panel durante el rollout

- Las tablas nuevas son aditivas.
- No se modifica el esquema de tablas existentes.
- El panel admin sigue entrando con `X-Admin-API-Key`.
- El panel tenant nuevo se apoya en cookies; no toca el flujo del bot ni las APIs de chat.
- `categories` ahora acepta tenant o admin para no cerrar accesos operativos.

## Riesgos operativos

- Si `JWT_SECRET` no esta configurado, el claim/login fallara.
- Si el frontend tenant se despliega antes que el backend, el overlay quedara sin endpoints validos.
- Si el backend se despliega antes que el frontend tenant, `/business/me/*` quedara protegido y el panel viejo ya no podra abrir. Por eso el despliegue debe ser coordinado.

## Orden recomendado de despliegue

1. Backend
2. Admin frontend
3. Tenant frontend
4. Smoke test manual completo

## Smoke test manual

1. Entrar a `/admin/`
2. Abrir `Acceso Tenant`
3. Emitir invitacion para un correo real o de prueba
4. Copiar link generado
5. Abrir `/tenant/?invite=...`
6. Definir nombre y contrasena fuerte
7. Verificar acceso al dashboard
8. Recargar pagina y validar restauracion de sesion
9. Cerrar sesion
10. Entrar con email + contrasena
11. Revocar o desactivar usuario desde admin
12. Confirmar que el usuario ya no puede renovar sesion

## Rollback

Si hay problema de frontend:

- restaurar `frontend/tenant` y `frontend/admin`
- mantener backend desplegado, porque las tablas nuevas no interfieren con el resto del producto

Si hay problema de backend:

- revertir deploy del backend
- las tablas `tenant_portal_*` pueden quedar creadas sin afectar el dominio existente

## Fase siguiente

Passkeys y MFA real quedan como fase 2:

- WebAuthn passkeys para acceso permanente
- TOTP para admins y acciones sensibles
- backup codes
- politicas de step-up auth por rol
