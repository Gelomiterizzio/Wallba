# Seguridad y protección de archivos

Este documento describe lo que el código de `backend/wallba/guard` hace en la rama local. No describe una garantía contra cualquier programa del equipo.

## Modelo de amenazas

El activo es un árbol de proyecto elegido por un operador. El adversario considerado es el agente de prueba `wallba-test-agent`, que solo existe cuando la operación entra por el hook o el shim. Un programa con el mismo usuario queda fuera de ese control preventivo.

El firewall de herramientas sintéticas (`file.read`, `email.send`, `record.delete`, `db.query`) sigue siendo otro plano: deniega por defecto si no hay una política activa válida. En el recorrido de S04, sin política activa, el lado protegido respondió `POLICY_MISSING` y no hubo recibo de ejecución.

## Clasificación

El escáner usa nombre, extensión y carpeta. No abre el archivo para clasificarlo. Una coincidencia es un indicador, no una prueba de que el contenido sea secreto.

| Nivel | Ejemplo de regla |
|---|---|
| CRITICAL | `.env`, `id_rsa`, extensión `.pem` o `.key`, carpetas `.ssh`, `.aws`, `secrets` |
| HIGH | volcados `.sql`, `.sqlite`, `.tfvars`, carpetas `infra` o `k8s` |
| MEDIUM | código o texto cuyo nombre contiene «token» o «secret» |
| LOW | sin esos indicadores |

## Políticas

| Postura | Lectura | Escritura | ¿Preventiva? |
|---|---|---|---|
| `monitor` | se permite y se registra | se permite y se registra | no |
| `alert` | se permite y se registra con más severidad | igual | no |
| `block_read` | se deniega antes de abrir | no la cubre | solo la lectura |
| `block_write` | no la cubre | se deniega antes de modificar | solo la escritura |
| `block_all` | se deniega antes | se deniega antes | sí |
| postura desconocida | se deniega | se deniega | sí, por defecto |
| sin regla | no se bloquea | no se bloquea | no está cubierta |

## Tres capas

1. **Preventiva.** El hook de `PreToolUse` y el shim consultan la política y, si la decisión es `DENY`, no abren ni modifican el archivo. El proceso que no llama a ese hook no queda detenido.
2. **Monitor.** Compara tamaño y fecha de los archivos. Un cambio o una ausencia se registra como `detected`. El origen es `ORIGEN NO DETERMINADO`. No demuestra que alguien haya leído el archivo.
3. **Integridad.** El almacén del guardia vive fuera del proyecto (`WALLBA_DATA_DIR/guard`). El monitor no restaura archivos.

## Hook

`python -m wallba.guard.hook` lee JSON por la entrada estándar. Si la herramienta es de archivo y no hay ruta, sale con código 2. Si la ruta tiene una política de bloqueo aplicable, sale con código 2. En otro caso sale con 0. La función `snippet()` devuelve el JSON de configuración y no escribe en el directorio del usuario.

Ejemplo de instalación, para copiar a mano:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Write|Edit|NotebookEdit",
        "hooks": [
          { "type": "command", "command": "python -m wallba.guard.hook" }
        ]
      }
    ]
  }
}
```

Hace falta `WALLBA_GUARD_DB` apuntando a la base del guardia. Sin esa variable, el hook no encuentra políticas y no bloquea por una regla.

## Persistencia

Las reglas quedan en SQLite, ligadas a la ruta canónica del proyecto. Abrir otra carpeta no reutiliza esas reglas. No se guardan contraseñas ni el contenido del archivo en los eventos.

## Desactivar

Quitar la regla en el centro de protección deja de aplicar esa postura. El monitor no se presenta como un bloqueo: dejar de pulsar «Revisar cambios ahora» deja de generar eventos de observación. Las reglas ya guardadas siguen en la base hasta que se eliminan.

## Pruebas

`tests/guard` cubre confinamiento, clasificación sin abrir archivos, denegación previa, escritura observada bajo `monitor`, cambio externo detectado sin restauración y el snippet que no crea `~/.claude`. 19 pruebas pasaron. La de enlace simbólico se saltó porque Windows no permitió crear el enlace.

## Riesgos que permanecen

Quien comparte el usuario del proceso puede ignorar el hook, escribir el archivo o modificar la base. El monitor puede perder un cambio entre dos lecturas y no nombra al proceso. Una política `alert` o `monitor` no impide la operación. El recorrido web de S04 no tenía política activa, así que el resultado protegido fue `POLICY_MISSING`.
