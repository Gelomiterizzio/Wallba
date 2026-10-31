# Equilibrio del esfuerzo

Presupuesto normalizado: 100 unidades. Una unidad no equivale a una hora. Las estimaciones se formularon por dificultad/incertidumbre y luego se redistribuyeron paquetes coherentes para equilibrar capacidad, no cantidad de tareas.

| Responsable | Tareas | Unidades | Porcentaje |
|---|---:|---:|---:|
| Persona 1 | 10 | 25 | 25 % |
| Persona 2 | 10 | 25 | 25 % |
| Persona 3 | 10 | 25 | 25 % |
| Persona 4 | 9 | 25 | 25 % |
| **TOTAL** | **39** | **100** | **100 %** |

## Por qué se redistribuyó

La hipótesis original concentraba toda la interfaz y auditoría en P4. P2 recibe editor de políticas completo y P3 centro de aprobaciones completo. P1 asume runner, matriz de resultados y evidencia del backend; P4 consume esos contratos. P4 conserva auditoría transaccional, diseño y E2E coordinado. Así cada módulo tiene una frontera coherente y una entrega demostrable.

## Método y sensibilidad

Cada tarea tiene desglose estimado en TASK_MATRIX y metadatos; considerar investigación, incertidumbre, implementación, pruebas, documentación e integración. Los valores son juicio de planificación y deben contrastarse con trabajo real. No se afirma haber medido productividad de personas desconocidas. Complejidad de CAS/parser/aislamiento pesa más que páginas sencillas.

Rango de sensibilidad inicial: ±30 % por persona, hasta +50 % en parser/ejecutor/carreras si surgen requisitos nuevos. Estos rangos expresan incertidumbre, no puntos extra autorizados. Revisar tras contratos y al finalizar cada ciclo: esfuerzo real, tareas faltantes, riesgos, bloqueos y capacidad disponible.

Si un módulo excede previsión, dividir una tarea por frontera clara o transferir paquete con su UI/pruebas/docs al dueño adecuado; registrar estimación previa y motivo. Mantener 25/25/25/25 mediante un nuevo baseline aprobado, sin ocultar desviaciones con renumeración cosmética. Si el alcance ya no cabe, presentar recorte del MVP o ampliación de calendario.

No hay quinta parte ni fondo de integración fuera de las 100 unidades. Cada persona integra, prueba y documenta su entrega.

[Matriz y justificaciones](TASK_MATRIX.md) · [Roadmap](ROADMAP.md) · [Índice](../README.md)
