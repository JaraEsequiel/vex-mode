# vex-mode

Mi modo de trabajo para agentes en [Antigravity](https://antigravity.google): playbooks rigurosos, trabajo verificado y reglas que se hacen cumplir por estructura (hooks y checks), no solo por texto.

Está construido sobre [pstack](https://github.com/cursor/plugins/tree/main/pstack), de Lauren Tan (poteto). Las skills de pstack se copian tal cual y se adaptan lo mínimo. La procedencia de cada archivo está en `vendor.lock` y la licencia MIT original en `LICENSES/pstack-MIT.txt`.

## Instalar

```bash
cd ~/Projects/VexOs/Code/Repos/vex-mode
python3 scripts/build_plugin.py --install ~/.cache/vex-mode/build
agy plugin list
```

Se instala desde una copia limpia: `agy plugin install` copia la carpeta entera, y el repo tiene archivos (docs, evals, `.git`) que no deben llegar a tus sesiones.

## Usar

- Siempre activo: un núcleo mínimo (`rules/AGENTS.md`) y la pausa ante acciones irreversibles.
- Modo completo: escribe `/vex-mode <tarea>`.

## Documentación

- Diseño: `docs/specs/2026-11-18-vex-mode-design.md`
- Plan de M1: `docs/plans/2026-11-18-vex-mode-m1-plan.md`
- Decisiones: `docs/decisions/`
- Para agentes que mantienen este repo: `AGENTS.md`
