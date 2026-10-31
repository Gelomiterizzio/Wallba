# GitHub y entrega

Repositorio objetivo: [Gelomiterizzio/Wallba](https://github.com/Gelomiterizzio/Wallba), rama principal `main`. Estado remoto desconocido; ver [inspección](REPOSITORY_INSPECTION.md). Este paquete no hizo init/clone/commit/push/merge.

## Incorporar la planificación

Cuando se disponga de acceso, P1 inspecciona un checkout separado con `git status --short`, `git remote -v`, `git branch -a` y `git log -5 --oneline`. Comparar código/documentos antes de copiar. No ejecutar `git init` dentro de un repo existente ni sobrescribir README/AGENTS ajenos. Si no hay commits, crear main local y commit documental revisado; si existen, partir de main actual. Crear rama `docs/wallba-master-plan`. Revisar diff y archivos staged explícitos para no incluir documentos personales, secrets o DB. Un commit local puede prepararse cuando el humano lo autorice; push y merge requieren autorización explícita independiente.

## Ramas de trabajo

`feature/person-1-foundation`, `feature/person-2-policies`, `feature/person-3-proxy`, `feature/person-4-dashboard`. Preferir subramas/PR pequeños por ID si el trabajo se alarga. Sin commits directos a main. Actualizar desde main con merge/rebase acordado; no reescribir ramas usadas por otras personas. Worktrees opcionales para agentes editores, con paths verificados y revisión del propietario.

## Commits y PR

Convención: `docs(plan): define approval contract [WAL-P3-004]`, `feat(policy): enforce deny precedence [WAL-P2-003]`, `fix(gateway): reject stale approval`. Un commit describe una unidad coherente. PR indica problema/comportamiento, IDs, contratos, pruebas realmente ejecutadas, evidencia y riesgos; usar [plantilla](../.github/pull_request_template.md). Bug: [plantilla](../.github/ISSUE_TEMPLATE/bug_report.md).

El dueño revisa cambios de su path; otro humano revisa seguridad. P2 revisa autorización/P3, P3 revisa aislamiento/P1, P4 revisa integración visual de P2/P3. Contratos compartidos requieren revisión de consumidores. P1 integra CI pero no reemplaza revisión de cada área.

## Protección y CI (a configurar después)

Si permisos y plan GitHub lo permiten, proteger main: PR requerido, al menos una aprobación, checks obligatorios, resolución de conversaciones y sin force push. CODEOWNERS puede añadirse cuando se conozcan los cuatro usuarios; no inventar handles. Configurar Actions según TEST_STRATEGY, permissions mínimos, acciones fijadas por SHA, sin secretos reales en forks ni artifacts. Escaneo de dependencias y secretos revisado en PR. No afirmar que branch protection existe antes de verificarlo.

## Conflictos y recuperación

Detener edición del archivo en conflicto; comunicar dueño y commits. Resolver contra contrato vigente, regenerar cliente y ejecutar suites afectadas; no elegir ours/theirs sin inspección. Si falla integración, revertir commit por PR preservando historial, no reset remoto. Backup de DB antes de migración. Si una migración se publicó, crear corrección nueva. Hallazgo de credencial: revocar y rotar antes de eliminar referencia; no copiar el secreto a reportes.

## Entrega de cada persona

Validar tarea -> revisar diff/estado -> pruebas propias y consumidores -> actualizar metadatos/manual/evidencia -> regenerar tablas -> PR -> revisión humana -> push/merge solo con autorización. Si no hay acceso remoto, entregar patch/local files y registrar bloqueo; no simular URL de PR.

[Índice](../README.md)
