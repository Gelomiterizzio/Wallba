# Ejemplos contractuales

Fixtures saneados para que P2, P3 y P4 trabajen contra el contrato. **Son ejemplos, no ejecuciones.**

| Archivo | Uso |
|---|---|
| `tool_call_file_read_allow.json`, `tool_call_record_delete_deny.json`, `tool_call_email_pending.json` | Llamadas válidas; el nombre indica la decisión esperada por escenario |
| `tool_call_invalid_extra_field.json` | Debe rechazarse por esquema |
| `decision_*.json`, `request_view_pending.json` | Respuestas del motor y del gateway |
| `error_401.json` … `error_503.json` | Formato común de error |
| `canonical_vectors.json` | Bytes canónicos, digest y firma HMAC. Generado por `scripts/export_contracts.py`; su secreto solo sirve para pruebas |
