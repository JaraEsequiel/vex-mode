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

## Auto-mejora programada

Cada domingo a las 03:00 un timer de systemd de usuario ejecuta `/correct` sobre los commits y PRs de los últimos 7 días. Lo hace desatendido, en un worktree propio y en una rama `correct/<fecha>`. Si encuentra errores que se repiten, el agente los commitea con su rastro de decisiones y, si toca una skill, un hook o una regla, también con el resultado del eval. Después el script pushea la rama y abre el PR. **Ningún PR se mergea solo:** el agente no pushea, el hook de pausa bloquea `gh pr merge` y los push a `main`, y el merge lo haces tú.

Antes de empezar, el script se niega (y te avisa) si el plugin instalado no tiene `correct` o el guardián de merge, o si hay un eval en curso. Así un domingo sin M3 mergeado no corre nada.

```bash
python3 scripts/scheduled_correct.py install     # instala y activa el timer
python3 scripts/scheduled_correct.py run --no-pr # ensayo a mano: commitea, no pushea
python3 scripts/scheduled_correct.py uninstall
systemctl --user list-timers vex-correct.timer   # próxima ejecución
```

- Los transcripts quedan en `~/.cache/vex-mode/correct/<fecha>.ndjson`. Si la ejecución falla, el worktree se conserva ahí mismo y recibes una notificación.
- `Persistent=true`: si el equipo estaba apagado el domingo, corre al iniciar sesión.
- **Costo conocido:** el eval reemplaza el plugin instalado mientras corre (~70 min). Si abres agy en ese rato, ves la variante; el arnés restaura tu plugin al terminar.
- El modelo se cambia con `VEX_CORRECT_MODEL` (por defecto `gemini-4-neon-high`).

## Preparar otro repo para agentes

Dentro del repo destino, en una sesión de agy, ejecuta `/agent-ready`. Genera:

- `AGENTS.md` con la tabla regla → qué la hace cumplir.
- `scripts/check`: un solo comando que corre igual en local, en el hook y en CI.
- `.agents/hooks.json` + `.agents/check_on_stop.py`: antes de terminar con cambios, el agente corre el `check` y, si falla, recibe el error y lo arregla. Máximo 3 intentos por conversación.
- `.agents/skills/verify-<app>/`: una skill que maneja la app como un usuario, con un mapa de features y, por cada recorrido, una rotura registrada que demuestra que puede fallar (`/maintain-verification-skill` la mantiene).
- `.github/workflows/check.yml`, si el repo tiene remoto de GitHub.

Antes de entregar, rompe algo a propósito y muestra que el `check` y el hook lo detectan.

## Documentación

- Diseño: `docs/specs/2026-11-18-vex-mode-design.md`
- Planes: `docs/plans/`
- Decisiones: `docs/decisions/`
- Para agentes que mantienen este repo: `AGENTS.md`
