"""Genera documentación desde metadatos del plan; no contiene lógica del producto."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tasks():
    return [task for path in sorted((ROOT / 'docs/planning').glob('person-*-tasks.json'))
            for task in json.loads(path.read_text(encoding='utf-8-sig'))]


def cell(value):
    if isinstance(value, list):
        value = '; '.join(map(str, value))
    return str(value).replace('|', '\\|').replace('\n', ' ')


def main():
    tasks = load_tasks()
    lines = ['# Matriz maestra de tareas', '',
             'Fuente: `docs/planning/person-*-tasks.json`. Todas pendientes de implementación. Cada estimación incluye investigación, implementación, pruebas, integración y documentación. Detalle paso a paso en el manual del dueño.', '',
             '| ID | Responsable | Módulo / historia | Tarea / subtareas | Prioridad | Unidades | Dependencias de construcción | Archivos | Subagente | Aceptación / validación | Estado |',
             '|---|---|---|---|---|---:|---|---|---|---|---|']
    for t in tasks:
        values = [t['id'], f"Persona {t['owner']}", t['module'] + ': ' + t['story'],
                  t['title'] + ': ' + '; '.join(t['steps']), t['priority'], t['effort'],
                  t['dependencies'] or 'Contrato + mock inicial', t['files'], t['subagent'],
                  t['acceptance'] + ' Prueba: ' + t['test'], t['state']]
        lines.append('| ' + ' | '.join(map(cell, values)) + ' |')
    lines += ['', '## Estimaciones razonadas por tarea', '']
    lines += [f"- **{t['id']} ({t['effort']} u):** {t['estimate_reason']}" for t in tasks]
    lines += ['', 'Las dependencias de la tabla son requisitos de construcción dentro de cada módulo. Las dependencias reales entre módulos se verifican en los gates de [INTEGRATION_CONTRACTS.md](INTEGRATION_CONTRACTS.md) y los manuales; los mocks permiten avanzar sin esperar la implementación completa del proveedor.', '', '[Equilibrio](WORKLOAD_BALANCE.md) · [Índice](../README.md)', '']
    (ROOT / 'docs/TASK_MATRIX.md').write_text('\n'.join(lines), encoding='utf-8')

    totals = {p: sum(t['effort'] for t in tasks if t['owner'] == p) for p in range(1, 5)}
    balance = ['# Equilibrio del esfuerzo', '',
               'Presupuesto normalizado: 100 unidades. Una unidad no equivale a una hora. Las estimaciones se formularon por dificultad/incertidumbre y luego se redistribuyeron paquetes coherentes para equilibrar capacidad, no cantidad de tareas.', '',
               '| Responsable | Tareas | Unidades | Porcentaje |', '|---|---:|---:|---:|']
    balance += [f"| Persona {p} | {sum(t['owner'] == p for t in tasks)} | {totals[p]} | {totals[p]} % |" for p in totals]
    balance += [f"| **TOTAL** | **{len(tasks)}** | **{sum(totals.values())}** | **100 %** |", '',
                '## Por qué se redistribuyó', '',
                'La hipótesis original concentraba toda la interfaz y auditoría en P4. P2 recibe editor de políticas completo y P3 centro de aprobaciones completo. P1 asume runner, matriz de resultados y evidencia del backend; P4 consume esos contratos. P4 conserva auditoría transaccional, diseño y E2E coordinado. Así cada módulo tiene una frontera coherente y una entrega demostrable.', '',
                '## Método y sensibilidad', '',
                'Cada tarea tiene desglose estimado en TASK_MATRIX y metadatos; considerar investigación, incertidumbre, implementación, pruebas, documentación e integración. Los valores son juicio de planificación y deben contrastarse con trabajo real. No se afirma haber medido productividad de personas desconocidas. Complejidad de CAS/parser/aislamiento pesa más que páginas sencillas.', '',
                'Rango de sensibilidad inicial: ±30 % por persona, hasta +50 % en parser/ejecutor/carreras si surgen requisitos nuevos. Estos rangos expresan incertidumbre, no puntos extra autorizados. Revisar tras contratos y al finalizar cada ciclo: esfuerzo real, tareas faltantes, riesgos, bloqueos y capacidad disponible.', '',
                'Si un módulo excede previsión, dividir una tarea por frontera clara o transferir paquete con su UI/pruebas/docs al dueño adecuado; registrar estimación previa y motivo. Mantener 25/25/25/25 mediante un nuevo baseline aprobado, sin ocultar desviaciones con renumeración cosmética. Si el alcance ya no cabe, presentar recorte del MVP o ampliación de calendario.', '',
                'No hay quinta parte ni fondo de integración fuera de las 100 unidades. Cada persona integra, prueba y documenta su entrega.', '',
                '[Matriz y justificaciones](TASK_MATRIX.md) · [Roadmap](ROADMAP.md) · [Índice](../README.md)', '']
    (ROOT / 'docs/WORKLOAD_BALANCE.md').write_text('\n'.join(balance), encoding='utf-8')


if __name__ == '__main__':
    main()
