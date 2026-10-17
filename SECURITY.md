# Política de seguridad

## Versiones con soporte

Es un proyecto de demostración: solo se mantiene la última versión de la rama `main`.

## Cómo reportar una vulnerabilidad

**No abras una incidencia pública con los detalles de una vulnerabilidad.**

Usa el informe privado de GitHub: pestaña **Security** de este repositorio → **Report a vulnerability**
(también en https://github.com/APCarlosIA/mcp-groq-agent/security/advisories/new).

Si puedes, incluye qué herramienta o módulo afecta, los pasos para reproducirlo y el impacto que crees que tiene.

## Qué interesa especialmente

- Formas de saltarse las validaciones de `calcular`, `hora_actual`, `guardar_nota` o `listar_notas`.
- Lectura o escritura fuera de la carpeta de notas.
- Que la API key de Groq llegue al servidor MCP.

Es un proyecto personal y sin garantías: respondo en cuanto puedo, sin plazos fijos.