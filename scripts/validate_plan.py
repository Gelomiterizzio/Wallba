"""Audita únicamente el paquete documental; biblioteca estándar, sin dependencias."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate():
    errors = []
    checks = []
    paths = sorted((ROOT / 'docs/planning').glob('person-*-tasks.json'))
    tasks = []
    for path in paths:
        try:
            tasks.extend(json.loads(path.read_text(encoding='utf-8-sig')))
        except (ValueError, OSError) as exc:
            errors.append(f'{path.name}: {exc}')
    owners = {t.get('owner') for t in tasks}
    if owners != {1, 2, 3, 4} or len(paths) != 4:
        errors.append('Deben existir cuatro fuentes y cuatro responsables 1..4.')
    totals = {p: sum(t.get('effort', 0) for t in tasks if t.get('owner') == p) for p in range(1, 5)}
    if any(v != 25 for v in totals.values()) or sum(totals.values()) != 100:
        errors.append(f'Presupuesto inválido: {totals}')
    ids = [t.get('id') for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append('IDs duplicados.')
    required = {'id', 'owner', 'module', 'story', 'title', 'steps', 'priority', 'effort',
                'dependencies', 'files', 'subagent', 'acceptance', 'test', 'estimate_reason', 'state'}
    by_id = {t.get('id'): t for t in tasks}
    for t in tasks:
        label = t.get('id', '<sin ID>')
        if required - t.keys():
            errors.append(f'{label}: campos faltantes {required - t.keys()}')
        for field in required - {'dependencies'}:
            if not t.get(field):
                errors.append(f'{label}: vacío {field}')
        if not re.fullmatch(rf"WAL-P{t.get('owner')}-\d{{3}}", str(label)):
            errors.append(f'{label}: ID incompatible con owner')
        if not isinstance(t.get('effort'), (int, float)) or t.get('effort', 0) <= 0:
            errors.append(f'{label}: esfuerzo inválido')
        for dep in t.get('dependencies', []):
            if dep not in by_id:
                errors.append(f'{label}: dependencia inexistente {dep}')
        if not (ROOT / '.cursor/agents' / (t.get('subagent', '') + '.md')).exists():
            errors.append(f'{label}: subagente no definido')
    visiting, visited = set(), set()

    def visit(task_id):
        if task_id in visiting:
            errors.append(f'Ciclo de dependencias en {task_id}')
            return
        if task_id in visited or task_id not in by_id:
            return
        visiting.add(task_id)
        for dep in by_id[task_id].get('dependencies', []):
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)
    manuals = sorted((ROOT / 'docs/team').glob('PERSON_*_MASTER_PLAN.md'))
    if len(manuals) != 4:
        errors.append('Se requieren exactamente cuatro manuales.')
    matrix_path = ROOT / 'docs/TASK_MATRIX.md'
    matrix = matrix_path.read_text(encoding='utf-8') if matrix_path.exists() else ''
    for p in range(1, 5):
        path = ROOT / f'docs/team/PERSON_{p}_MASTER_PLAN.md'
        if not path.exists():
            errors.append(f'Falta manual P{p}')
            continue
        content = path.read_text(encoding='utf-8-sig')
        sections = {int(n) for n in re.findall(r'^## (\d+)\.', content, re.M)}
        if sections != set(range(1, 24)):
            errors.append(f'P{p}: secciones personales distintas de 1..23: {sections}')
        for t in tasks:
            if t['owner'] == p and (t['id'] not in content or t['id'] not in matrix):
                errors.append(f"{t['id']}: falta en manual o matriz")
    agents = list((ROOT / '.cursor/agents').glob('*.md'))
    if len(agents) != 9:
        errors.append('Se esperan nueve subagentes.')
    agent_names = []
    for path in agents:
        content = path.read_text(encoding='utf-8')
        match = re.match(r'^---\n(.*?)\n---\n', content, re.S)
        if not match:
            errors.append(f'{path.name}: frontmatter ausente')
            continue
        fields = dict(re.findall(r'^([a-z_]+):\s*(.*?)$', match[1], re.M))
        if set(fields) != {'name', 'description', 'model', 'readonly', 'is_background'}:
            errors.append(f'{path.name}: campos de subagente no previstos')
        if fields.get('name') != path.stem or fields.get('model') != 'inherit':
            errors.append(f'{path.name}: nombre/modelo inválido')
        if fields.get('readonly') not in {'true', 'false'} or fields.get('is_background') != 'false':
            errors.append(f'{path.name}: booleanos inválidos')
        agent_names.append(fields.get('name'))
    if any(n > 1 for n in Counter(agent_names).values()):
        errors.append('Nombres de subagente duplicados.')
    for name in ('p2-security-auditor', 'wallba-verifier'):
        if f'readonly: true' not in (ROOT / f'.cursor/agents/{name}.md').read_text(encoding='utf-8'):
            errors.append(f'{name}: requiere readonly')
    rules = list((ROOT / '.cursor/rules').glob('*.mdc'))
    for path in rules:
        content = path.read_text(encoding='utf-8')
        match = re.match(r'^---\n(.*?)\n---\n', content, re.S)
        if not match:
            errors.append(f'{path.name}: regla sin frontmatter')
            continue
        fields = dict(re.findall(r'^([a-zA-Z_]+):\s*(.*?)$', match[1], re.M))
        if set(fields) - {'description', 'globs', 'alwaysApply'} or fields.get('alwaysApply') not in {'true', 'false'}:
            errors.append(f'{path.name}: frontmatter MDC inválido')
    broken = []
    documents = list(ROOT.rglob('*.md')) + rules
    for path in documents:
        content = path.read_text(encoding='utf-8-sig')
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', content):
            target = target.strip('<>')
            if re.match(r'^[a-z]+:', target) or target.startswith('#'):
                continue
            target = target.split('#', 1)[0]
            if target and not (path.parent / target).resolve().exists():
                broken.append(f'{path.relative_to(ROOT)} -> {target}')
    errors += ['Enlace roto: ' + link for link in broken]
    checks = [f'Tareas: {len(tasks)}; IDs únicos: {len(set(ids))}',
              f'Presupuestos: {totals}; total: {sum(totals.values())}',
              f'Manuales: {len(manuals)}; subagentes: {len(agents)}; reglas: {len(rules)}',
              f'Enlaces locales revisados en {len(documents)} documentos; rotos: {len(broken)}',
              'Dependencias existentes y DAG; criterios, pruebas y justificaciones presentes.']
    print('\n'.join(checks))
    if errors:
        print('\n'.join('ERROR: ' + error for error in errors))
        return 1
    print('PASS: estructura y metadatos del plan. No valida ejecución de producto ni reconocimiento por Cursor.')
    return 0


if __name__ == '__main__':
    sys.exit(validate())
