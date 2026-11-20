# Guía de uso de vex-mode

vex-mode es un plugin que cambia cómo trabaja tu agente. Funciona en Antigravity (agy) y en Claude Code. Le da playbooks para cada tipo de tarea, le exige pruebas antes de terminar y frena las acciones que no se pueden deshacer.

Lee la guía en este orden:

1. [Instalar vex-mode en agy o en Claude Code](instalar.md). Instalación, actualización y desinstalación en cada plataforma.
2. [Cómo se usa vex-mode en el día a día](flujo-de-trabajo.md). Un día común de trabajo y los casos de uso más frecuentes, paso a paso.
3. [Qué hace el agente en cada paso](pasos-en-detalle.md). Cada playbook, cada hook y cada skill explicados a fondo.

## Resumen en una tabla

| Quieres | En agy | En Claude Code |
| --- | --- | --- |
| Trabajar en modo completo | `/vex-mode <tarea>` | `/vex-mode:vex-mode <tarea>` |
| Diseñar la forma del código antes de escribirlo | `/architect` | `/vex-mode:architect` |
| Saber por qué algo es como es | `/why` | `/vex-mode:why` |
| Preparar un repo para agentes | `/agent-ready` | `/vex-mode:agent-ready` |
| Convertir errores repetidos en checks | `/correct` | `/vex-mode:correct` |
| Guardar lo aprendido en una sesión | `/reflect` | `/vex-mode:reflect` |
| Dejar un rastro de decisiones en trabajo largo | `/show-me-your-work` | `/vex-mode:show-me-your-work` |

Sin ningún comando, el núcleo siempre activo ya corre en cada sesión. La sección [Lo que está siempre activo](flujo-de-trabajo.md#lo-que-está-siempre-activo) explica qué incluye.

## Otros documentos

- El diseño completo está en [`docs/specs/2026-11-18-vex-mode-design.md`](../specs/2026-11-18-vex-mode-design.md).
- Las decisiones y sus pruebas están en [`docs/decisions/`](../decisions/).
- Las instrucciones para agentes que mantienen este repo están en [`AGENTS.md`](../../AGENTS.md).
