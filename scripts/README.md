# Scripts

Este directorio contiene utilidades puntuales de mantenimiento y automatización.

## Política

- Los scripts aquí viven para tareas de operación o generación de artefactos.
- No deben ser importados por el código de producción.
- Los cambios en este directorio deben revisarse como parte del mantenimiento del repositorio.

## Uso frecuente

- Exportación del contrato OpenAPI:

```bash
uv run python scripts/export_openapi.py
```
