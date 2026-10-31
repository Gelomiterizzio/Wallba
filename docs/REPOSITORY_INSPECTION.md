# Inspección y supuestos

Fecha de planificación: 31 de octubre de 2026, America/La_Paz.

El directorio padre `C:/Users/hp/Desktop/rodrigo` contiene documentos personales y no tiene `.git`. No se modificaron esos materiales. Se creó `Wallba/` como paquete documental independiente; no se clonó ni inicializó un repositorio.

Se leyó íntegramente la solicitud adjunta, incluidas sus 30 secciones. El apartado de material visual contiene un marcador para pegar referencias, sin capturas o especificaciones adicionales. La identidad visual de [PRODUCT_DESIGN.md](PRODUCT_DESIGN.md) es una propuesta pendiente de revisión humana.

Repositorio indicado: [Gelomiterizzio/Wallba](https://github.com/Gelomiterizzio/Wallba), rama objetivo `main`. La lectura web devolvió `Cache miss` y `git ls-remote` falló con `getaddrinfo() thread failed to start`. Por tanto, contenido, commits, ramas, licencia y permisos remotos NO VERIFICADOS. Esto no demuestra que esté vacío o que sea privado. Antes de implementar, P1 debe comparar este paquete con un checkout accesible y proponer adaptación en lugar de sobrescribir archivos.

No se implementó la aplicación ni se realizaron commits, pushes o merges. Los paths de código en estos documentos son rutas propuestas, no archivos ejecutables existentes.

## Supuestos explícitos

- MVP local para un equipo y un entorno de demostración; sin multitenancy ni exposición pública.
- Cuatro personas con experiencia básica en Python/TypeScript y Git; disponibilidad horaria no informada.
- Sin proveedor LLM elegido: simulación determinista obligatoria y adaptador live sustituible opcional posterior.
- Correo siempre simulado; base de datos y archivos exclusivamente sintéticos.
- Administrador del host, root y compromiso del ejecutor quedan fuera de la garantía del MVP; se documentan como riesgos residuales.
- Los 100 puntos representan esfuerzo relativo incluyendo investigación, pruebas, integración y documentación, no horas garantizadas.

## Decisiones antes de desarrollar

Revisar el plan, asignar nombres a P1–P4, facilitar acceso al repositorio, confirmar diseño y disponibilidad. El usuario debe aprobar el inicio de implementación. No hacen falta credenciales de servicios reales para la demo reproducible.

Volver al [índice](../README.md).

## Actualización para publicación autorizada

Después de completar la planificación, el usuario solicitó explícitamente subirla a su GitHub. Se reintentó la conexión fuera del entorno de red restringido: `git ls-remote` terminó con exit code 0 y sin refs; el clone confirmó `You appear to have cloned an empty repository`. Se preparó este paquete como primer commit documental sobre `main`. Los límites de acceso descritos arriba corresponden a la inspección inicial y ya no bloquean esta publicación. La autorización de subida no implica aprobación para implementar la aplicación.
