# Guia UX Operativa Para Tenant

## Principio rector

El mejor diseño es aquel donde la herramienta desaparece y solo queda el beneficio.

Para este frontend tenant, eso significa que la interfaz no debe sentirse como un panel tecnico ni como un CRM. Debe sentirse como una mesa de control simple para operar el negocio en el dia a dia.

## Perfil de uso

El usuario principal no es tecnico. Normalmente necesita:

- revisar rapido si su negocio esta bien configurado
- actualizar catalogo
- ajustar horarios
- guardar respuestas frecuentes
- confirmar por donde llegan mensajes

No necesita comprender arquitectura, integraciones, flujos internos ni conceptos de sistema.

## Reglas de lenguaje

- Usar espanol neutral y formal.
- Evitar modismos, jerga operativa y anglicismos innecesarios.
- Reemplazar terminos tecnicos por terminos de tarea.
- Explicar consecuencia y utilidad, no implementacion.

Renombres aplicados:

- `Dashboard` -> `Resumen del dia`
- `Perfil` -> `Datos del negocio`
- `Categorias` -> `Grupos de productos`
- `Knowledge Base` -> `Informacion util`
- `Tenant ID` -> `identificador de su negocio`

## Reglas de interfaz

- Cada vista debe responder: que estoy viendo, que puedo hacer aqui y cual es el siguiente paso.
- Los botones principales deben ser visibles y accionables con mouse.
- Los estados vacios deben orientar.
- Las ayudas deben ser breves, formales y no tecnicas.
- La prioridad visual debe estar en tareas frecuentes, no en opciones avanzadas.

## Criterio de implantacion

Se reutiliza la estructura actual del tenant y sus endpoints existentes. El cambio se concentra en:

- copy operativo
- jerarquia visual
- accesos rapidos
- resumen de estado
- estados vacios y recomendaciones

No se introduce una arquitectura nueva ni una capa adicional de configuracion.
