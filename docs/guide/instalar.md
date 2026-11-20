# Instalar vex-mode en agy o en Claude Code

vex-mode se instala distinto en cada plataforma. En agy lo construyes desde una copia local del repo. En Claude Code lo instalas desde el marketplace de GitHub.

## Requisitos

- `python3` 3.10 o más nuevo. Los hooks son scripts de Python.
- `git`.
- Para agy: `agy` instalado y en el `PATH`. Comprueba con `agy --version`.
- Para Claude Code: `claude` instalado y en el `PATH`. Comprueba con `claude --version`.

## Instalar en Antigravity (agy)

1. Clona el repo.

   ```bash
   git clone git@github.com:JaraEsequiel/vex-mode.git ~/Projects/vex-mode
   cd ~/Projects/vex-mode
   ```

2. Construye e instala el plugin desde `main`.

   ```bash
   python3 scripts/build_plugin.py --ref main --install ~/.cache/vex-mode/build
   ```

   Sin `--ref`, el script copia tu árbol de trabajo tal como está, con cambios sin commitear incluidos. Usa `--ref main` para instalar lo último que se mergeó, o un tag de versión como `--ref v0.2.0` para fijar una versión (los tags están en `git tag`).

3. Comprueba que el plugin quedó instalado.

   ```bash
   agy plugin list
   ```

   Debe aparecer `vex-mode`.

4. Abre una sesión nueva de agy y escribe `/vex-mode` seguido de una tarea.

No ejecutes `agy plugin install` sobre la carpeta del repo. Ese comando copia la carpeta entera, y el repo tiene docs, evals y `.git` que no deben llegar a tus sesiones. `build_plugin.py` exporta solo las partes del plugin: `skills/`, `agents/`, `rules/`, `hooks/`, `hooks.json`, `adapters/` y `plugin.json`.

### Actualizar en agy

```bash
cd ~/Projects/vex-mode
git pull
python3 scripts/build_plugin.py --ref main --install ~/.cache/vex-mode/build
```

El script desinstala la versión anterior antes de instalar la nueva. Abre una sesión nueva para que cargue.

### Desinstalar en agy

```bash
agy plugin uninstall vex-mode
```

### Qué se activa en agy

| Pieza | Cuándo actúa |
| --- | --- |
| `rules/AGENTS.md` (núcleo) | Siempre, como regla `always_on` del plugin. |
| `hooks/irreversible.py` | Antes de cada `run_command`. |
| `hooks/activate.py` | Antes de cada mensaje, para detectar `/vex-mode` y los demás comandos. |
| `hooks/stop_gate.py` | Cuando el agente quiere terminar en una conversación con modo completo. |

## Instalar en Claude Code

1. Agrega el marketplace.

   ```bash
   claude plugin marketplace add JaraEsequiel/vex-mode
   ```

   Si usas un fork, cambia `JaraEsequiel/vex-mode` por `<usuario>/<repo>` del fork.

2. Instala el plugin.

   ```bash
   claude plugin install vex-mode@vex
   ```

   `vex` es el nombre del marketplace y `vex-mode` el del plugin.

3. Comprueba que quedó instalado.

   ```bash
   claude plugin list
   ```

4. Abre una sesión nueva de Claude Code. Escribe `/vex-mode:vex-mode` seguido de una tarea.

Claude Code agrupa las skills de un plugin bajo su nombre. Por eso cada comando lleva el prefijo `vex-mode:`. Por ejemplo, `/architect` en agy es `/vex-mode:architect` en Claude Code.

### Actualizar en Claude Code

```bash
claude plugin marketplace update vex
claude plugin update vex-mode@vex
```

Reinicia Claude Code para que cargue la versión nueva.

### Desinstalar en Claude Code

```bash
claude plugin uninstall vex-mode@vex
claude plugin marketplace remove vex
```

### Qué se activa en Claude Code

Claude Code no tiene reglas de plugin, así que el núcleo llega por un hook.

| Pieza | Cuándo actúa |
| --- | --- |
| `hooks/session_start.py` | Al iniciar, reanudar, limpiar o compactar la sesión. Carga `rules/AGENTS.md` como contexto. |
| `hooks/irreversible.py` | Antes de cada `Bash`. Pide confirmación, nunca aprueba por su cuenta. |
| `hooks/activate.py` | Antes de cada mensaje, para detectar `/vex-mode:vex-mode`. |
| `hooks/stop_gate.py` | Cuando el agente quiere terminar en una conversación con modo completo. Bloquea una vez por mensaje, salvo que la última herramienta del turno haya sido un comando. |

Las skills usan nombres de agy. El agente los traduce con `adapters/claude-code.md`, que el hook de inicio le indica leer. Un paso que solo existe en agy aparece en la respuesta como `Skipped in Claude Code: <paso>. <razón>.` y el agente sigue con el siguiente.

El árbol que instala Claude Code está en `harness/claude-code/`. Lo genera `python3 scripts/build_plugin.py --harness claude-code`. No lo edites a mano.

## Comprobar que funciona

Haz esta prueba en una sesión nueva, en un repo de práctica.

1. Pide al agente que ejecute `git push --force origin main`.
2. El agente debe pausar y pedirte confirmación. El motivo dice `git push --force`.
3. Rechaza la acción.

Si el comando corre sin pausa, el hook no cargó. Revisa que `python3` esté en el `PATH` y que abriste una sesión nueva después de instalar.

Para probar el modo completo, escribe `/vex-mode di qué archivos leíste primero` en agy o `/vex-mode:vex-mode di qué archivos leíste primero` en Claude Code. El agente debe nombrar `worker.md` y `opening-a-pr.md`. Los demás playbooks y las skills de principios los lee cuando la tarea los necesita.
