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

## Evals

Cada cambio a una skill se mide antes de entrar. El eval compara tres brazos, cada uno con candidatos que no saben que están siendo evaluados:
- A: la skill de `main`.
- B: la versión nueva.
- C: la de `main` con un modelo mejor.

Un juez de otra familia de modelos califica las respuestas sin saber de qué brazo viene cada una.

```bash
python3 evals/run.py vex-mode tax-rounding
python3 evals/run.py verdict <resultado.json> promote "<síntesis>"
```

- Los casos están en `evals/<skill>/cases/` y los resultados en `evals/<skill>/results/`.
- Los transcripts completos quedan solo en local, en `~/.cache/vex-mode/runs/`.
- Mientras corre un eval, el plugin instalado cambia en cada brazo. Al terminar se restaura el original, aunque el eval falle. No uses agy durante el eval. Si el proceso muere sin restaurar, el siguiente eval no arranca hasta que ejecutes `python3 evals/run.py restore`.

## Documentación

- Diseño: `docs/specs/2026-11-18-vex-mode-design.md`
- Planes: `docs/plans/`
- Decisiones: `docs/decisions/`
- Para agentes que mantienen este repo: `AGENTS.md`
