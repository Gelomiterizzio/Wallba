# Cursor y orquestación

Fuentes oficiales consultadas el 31/10/2026: [subagentes](https://cursor.com/docs/subagents) y [reglas](https://cursor.com/docs/rules). Se usan solo campos documentados: name, description, model, readonly, is_background; reglas .mdc con description, globs y alwaysApply. Todos heredan modelo y se ejecutan foreground por defecto. No se inventan campos tools, owner, isolation o permisos de directorio. La disponibilidad real depende de la versión/plan de Cursor instalado; validar en su UI antes de iniciar.

## Inicio y validación de configuración

Abrir la raíz `Wallba` en Cursor, no la carpeta padre. Revisar Customize/Rules y reconocimiento de los nueve archivos de `.cursor/agents/`. Si no aparecen, comprobar versión con soporte de subagentes, ubicación y frontmatter; no afirmar que se activaron por escribir Markdown. Abrir el plan personal y copiar su prompt final. Leer AGENTS, contratos y propiedad. Guardar aprobación del plan y alcance humano en PR inicial antes de código funcional.

## Ciclo por tarea

1. Humano elige ID desbloqueado y revisa criterios, estimación y dependencia real.
2. Principal inspecciona estado Git y paths permitidos. Proporciona al subagente ID, objetivo, manual, contratos, ejemplos, archivos permitidos, salidas esperadas y comandos de prueba.
3. Delegar por nombre del subagente reconocido en Cursor; comprobar tarjeta de ejecución. Mencionar un archivo en texto no prueba que se haya invocado. No depender de comandos slash no documentados.
4. Subagente entrega informe estructurado; principal inspecciona diff y ejecuta pruebas pertinentes en entorno local aislado.
5. Revisión independiente readonly por auditor/verificador. Si un test escribe caches, BD o snapshots, el principal lo ejecuta y entrega logs; readonly no se deshabilita silenciosamente.
6. Humano revisa criterios y evidencia, prepara PR; cambiar estado en metadatos, regenerar matriz y manual afectado. No completar por una afirmación del modelo.

## Modos y ejemplos

| Persona | Secuencial | Paralelo independiente | Revisión |
|---|---|---|---|
| P1 | arquitecto fija ExecutorPort; engineer implementa adapter | investigar redes y fixtures en paths distintos | verifier inspecciona bloqueo de acceso directo |
| P2 | loader antes de evaluator integrado | auditor readonly amenaza mientras engineer desarrolla tests en su rama | auditor revisa precedencia, sin editar |
| P3 | identidad -> gateway -> consumo | UI approval y unit tests del gateway en paths aislados | verifier exige evidencia de carrera/replay |
| P4 | AuditSink -> read API -> timeline | diseño shell y mock UI playground con paths distintos | verifier revisa datos reales frente a expectativas |

No dos escritores en el mismo path. Para código paralelo usar worktrees locales revisados: `git worktree add ../wallba-p2-review -b review/p2-policy` después de comprobar que el path no existe y hay repo inicializado. Es un comando futuro, no se ejecutó aquí. No borrar worktrees con cambios sin revisar. El principal aplica cambios y resuelve merge de forma supervisada; un subagente no hace push/merge remoto.

Si falta contrato, detener esa tarea y avanzar con fixture acordado o tarea independiente. Si cambia alcance, registrar decisión y recalcular esfuerzo antes de repartir. Si hay outputs contradictorios, el principal resuelve contra contrato y solicita decisión humana cuando afecte alcance; no delegar el conflicto a otro escritor sin explicación.

Los archivos declaran límites organizativos; readonly ofrece restricción de escritura, pero el texto de paths no es una política de acceso real. No dar secretos al contexto. No se crean agentes adicionales genéricos.

[Índice](../README.md) · [Entrega GitHub](GITHUB_WORKFLOW.md)
