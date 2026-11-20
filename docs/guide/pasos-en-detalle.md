# Qué hace el agente en cada paso

Esta página explica a fondo cada pieza de vex-mode: los playbooks paso a paso, los hooks, los subagentes y las skills. Sirve para entender por qué el agente hace lo que hace y para saber qué esperar de él.

La fuente de cada playbook está en `skills/vex-mode/playbooks/`. Si esta página y un playbook no coinciden, manda el playbook.

## Cómo arranca el modo completo

Cuando escribes `/vex-mode <tarea>`:

1. `hooks/activate.py` crea un marcador para la conversación en el directorio de estado del plugin. Ese marcador es lo que hace que `stop_gate.py` actúe después.
2. El hook inyecta la lista de lectura una sola vez. El agente lee `worker.md`, los playbooks y las skills de principios antes de hacer nada.
3. El agente aplica las reglas fijas del router `skills/vex-mode/SKILL.md`:
   - Repite el objetivo y el cambio mínimo en el primer mensaje.
   - Si una duda se resuelve corriendo algo, hace un prototipo en vez de preguntar.
   - Antes de escribir código, nombra la forma de los datos. Si el cambio cruza una función, usa `architect`.
   - Pasa todo texto por `unslop`, y la documentación, los PRs y los commits también por `technical-writing`.
   - Juzga cada comentario de un bot de revisión por su contenido, sin aceptarlo de forma automática.
4. Elige el playbook que corresponde y copia sus pasos a la lista de tareas.

Si el agente lanza un subagente, la primera línea de su encargo es `Read <ruta>/worker.md before anything else.` Así las reglas llegan también a los subagentes, que no cargan las skills por su cuenta.

## Playbook de bug fix

El agente es dueño de la tarea. Delega la investigación y el fix a subagentes, pero planea, revisa y verifica él. Cada línea que se envía tiene que apoyarse en evidencia de ejecución. Un cambio que "quizás ayude" es una hipótesis y no se envía.

1. **Reproducir.** El agente reproduce el bug en el mismo lugar donde ocurre: la app, la CLI o el servicio. Te pide que lo reproduzcas solo si no puede llegar al sistema, y te da la razón concreta. Si el bug no aparece, fuerza las condiciones o agrega instrumentación hasta que aparezca.
2. **Buscar la causa por división.** Arma las hipótesis posibles. Usa una traza del subsistema y la skill `why` para ver si es una regresión. En cada vuelta elige la prueba que más reduce el espacio de búsqueda, obtiene evidencia y descarta. Si el estado del programa no está claro, agrega logs y los lee mientras corre. No adivina. Confirma el mecanismo antes de pasar al paso 3.
3. **Planear el fix.** Si el fix cruza una función, corre `architect`. El contrato público se mantiene: el test de regresión llama al código como lo llaman sus callers actuales. La interfaz cambia solo si tu pedido lo dice. La implementación va a un subagente con alcance concreto.
4. **Verificar en el mismo lugar.** La reproducción del paso 1 ahora pasa. Un resultado "inconcluso" o en otro lugar no cuenta como pase, y el agente lo marca así. Los tests unitarios muestran ramas del código, no la ausencia del bug.
5. **Ordenar los commits.** El test que falla va en un commit antes del fix. Si el bug tiene un test local barato, sigue la skill `tdd`.
6. **Abrir el PR.** Corre el playbook de abrir un PR.

La respuesta final dice qué estaba roto, la causa raíz, el fix y cómo se verificó, con la salida de la reproducción antes y después.

## Playbook de feature

El agente es dueño del diseño y delega la implementación.

1. **Estudiar el subsistema.** Lee el código que el cambio toca y lo que depende de él.
2. **Diseñar con `architect`.** Propone dos formas distintas de tipos, firmas y módulos. Elige la que da un solo dueño a cada estado y una sola forma de hacer cada cosa.
3. **Escribir el plan de paralelismo** como cuatro tareas. Si una no aplica, queda con `n/a: <razón>`:
   - Pasos que bloquean y corren antes de repartir trabajo.
   - Trabajos independientes, en archivos o capas que no se pisan.
   - Estado compartido. Por defecto se divide el objetivo para que nadie comparta; se serializa solo si hay una invariante real.
   - La división más chica que es segura. Si un solo trabajador es lo mejor, dice por qué.
4. **Delegar el código.** El subagente recibe rutas de archivos, la forma de los datos ya elegida y los criterios de éxito. Por ejemplo, una máquina de estados en lugar de booleanos sueltos, o una tabla en lugar de muchos `if`.
5. **Verificar en el lugar real.** Igual que en bug fix, "inconcluso" no es un pase.
6. **Ordenar en commits chicos.** Cada unidad se construye, se verifica y se commitea antes de la siguiente.
7. **Abrir el PR.**

Un trabajo acoplado, como una feature o una migración, va a un solo dueño. Ese dueño reparte trabajo por dentro después de los pasos que bloquean. Repartir desde arriba sirve para trabajos que producen resultados independientes, como auditorías o experimentos.

La respuesta final dice qué se construyó, qué se eligió y por qué, el plan de paralelismo y las decisiones abiertas.

## Playbook de refactoring

El agente es dueño del contrato. La estructura cambia y el comportamiento no. Si aparece un bug o una feature que falta, la separa y envía primero el cambio de estructura.

1. **Fijar el comportamiento.** Escribe un test de caracterización, un snapshot o una comparación antes de mover nada. El type check y el lint no cuentan como fijación.
2. **Nombrar la estructura que falta.** Por ejemplo, una máquina de estados, un modelo tipado o una tabla. El cambio tiene que borrar ramas o estados inválidos, no agregar capas. El código simple y claro se queda como está.
3. **Nombrar la forma final.** Describe cómo serían los módulos, los tipos y las llamadas si el código se escribiera hoy. Si cruza una función, corre `architect`.
4. **Restar antes de sumar.** Borra código muerto, wrappers con un solo caller, validaciones repetidas y referencias huérfanas. Después construye la forma nueva.
5. **Mover en pasos chicos.** Cada paso mantiene el test del paso 1 en verde. Si cambia una API interna, migra todos los callers y borra la vieja en la misma ola, sin capas de compatibilidad. Revisa cada renombre en los archivos, porque se escapan usos en strings y en texto.
6. **Probar que nada cambió.** Para cambios grandes, compara salidas viejas contra nuevas con un script o con una corrida grabada.
7. **Confirmar que vale la pena.** Si el diff no hace el código más fácil de leer en algún lugar, el agente lo revierte.
8. **Ordenar los commits.** Primero la resta, después la nueva forma y al final la limpieza. Después abre el PR.

## Playbook de abrir un PR

Todos los playbooks terminan acá.

- El trabajo se hace en un git worktree que sale de la rama principal, sin trabajo ajeno mezclado.
- Los commits son chicos y cada uno se puede mergear solo.
- El título sigue `type(scope): subject`, por ejemplo `fix(orders): handle empty cart in totals`.
- El cuerpo tiene 40 líneas como máximo, con estas secciones en orden: `## Why`, `## What changed`, `## Scope`, `## Tradeoffs`, `## Blast Radius` y `## Verification`. Las vacías se omiten.
- Los logs largos van en un archivo o en un comentario del PR, con un enlace desde el cuerpo.
- El PR se abre listo para revisión, nunca como borrador.

El agente no mergea. El hook `irreversible.py` frena `gh pr merge` y los push a `main`. El merge lo haces tú.

## Playbook de eval

Este playbook es para quien mantiene vex-mode. Mide si un cambio a una skill mejora el trabajo del agente. Los pasos completos están en [`skills/vex-mode/playbooks/eval.md`](../../skills/vex-mode/playbooks/eval.md) y el uso del harness en el [README](../../README.md#evals).

En corto, `python3 evals/run.py <skill> <caso>` compara tres brazos con candidatos que no saben que los evalúan. Un juez de otra familia de modelos califica sin saber de qué brazo viene cada respuesta. Después tú lees las salidas y registras `promote`, `reject` o `inconclusive`.

## Los hooks

| Hook | Evento | Qué hace |
| --- | --- | --- |
| `session_start.py` | Inicio de sesión (solo Claude Code) | Carga `rules/AGENTS.md` como contexto y le dice al agente que lea el adaptador de Claude Code. |
| `activate.py` | Antes de cada mensaje | Con `/vex-mode`, activa el modo completo e inyecta la lista de lectura una vez. Con otro `/<skill>` del plugin, inyecta el texto de esa skill. |
| `irreversible.py` | Antes de cada comando de shell | Pide confirmación ante comandos irreversibles. Nunca aprueba por su cuenta. En modo no interactivo (`agy -p` o `claude -p`) el comando no corre. |
| `stop_gate.py` | Cuando el agente quiere terminar | En modo completo, pide una vez por mensaje la evidencia de verificación. No crea un ciclo: si el agente ya respondió a ese pedido, lo deja terminar. |

El hook de pausa analiza el comando completo. Sigue `bash -c`, `eval`, `sudo`, `env` y comandos encadenados con `&&`, `;` o `|`. Un `git push` sin argumentos estando en `main` no lo detecta; por eso también frena que una rama siga a `main`.

## Los subagentes

- El agente usa `vex-agent` para cada subagente que lanza dentro de un playbook. En Claude Code se llama `vex-mode:vex-agent`.
- Los subagentes corren en segundo plano y reciben rutas de archivos en lugar de contexto copiado.
- Cada reintento o ronda de arreglos va a un subagente nuevo con el encargo original, las indicaciones posteriores y el reporte del anterior. Se reanuda uno existente solo si tiene estado difícil de mover, como cambios sin commitear o un proceso corriendo.
- El agente principal es dueño del trabajo de cada subagente. Revisa su diff y escribe su propio resumen.
- Un subagente sigue las reglas de `worker.md`: no agrega revisiones por encima de lo pedido, no te hace preguntas, elige lo reversible y dice qué eligió. Solo se detiene ante un deploy, datos borrados, un force-push o un mensaje a alguien de afuera.

## Las skills de principios

El agente lee cada una entera cuando la aplica. Esta tabla dice cuándo entra cada una.

| Skill | Entra cuando el agente |
| --- | --- |
| `principle-laziness-protocol` | Refactoriza, mide el tamaño de un diff o siente la tentación de agregar capas. Prefiere borrar. |
| `principle-foundational-thinking` | Va a escribir lógica. Primero elige tipos y estructuras de datos. |
| `principle-redesign-from-first-principles` | Integra un requisito nuevo. Rediseña como si hubiera existido desde el principio. |
| `principle-subtract-before-you-add` | Ordena una suma o un refactor. Borra lo muerto primero. |
| `principle-minimize-reader-load` | Revisa código difícil de seguir. Cuenta capas y estado oculto. |
| `principle-model-the-domain` | Escribe lógica con estado o con muchas ramas. Usa una estructura en lugar de condicionales sueltos. |
| `principle-migrate-callers-then-delete-legacy-apis` | Introduce una API interna nueva. Migra y borra la vieja en la misma ola. |
| `principle-separate-before-serializing-shared-state` | Varios actores pueden escribir lo mismo. Elimina lo compartido primero. |
| `principle-prove-it-works` | Termina una tarea. Verifica sobre lo real. |
| `principle-fix-root-causes` | Depura. Arregla donde el sistema falló primero, no donde se ve el síntoma. |
| `principle-sequence-verifiable-units` | Hace trabajo de varios pasos. Cada unidad termina en un check. |
| `principle-explain-the-number` | Mide algo o confía en una medición. Busca qué la limita y qué midió en realidad. |
| `principle-never-block-on-the-human` | Siente la tentación de preguntar si hace algo reversible. Lo hace y te muestra el resultado. |
| `principle-encode-lessons-in-structure` | Escribe la misma instrucción por segunda vez. La convierte en un lint, un check o un script. |

## Las skills de tarea

| Skill | Para qué sirve |
| --- | --- |
| `architect` | Diseña tipos, firmas y módulos antes del código. Propone dos formas y elige una. |
| `why` | Explica por qué algo es como es, desde commits y PRs. |
| `tdd` | Escribe el test que falla antes del fix, solo cuando el test es barato. |
| `agent-ready` | Prepara un repo para agentes con reglas, un check, un hook de Stop y una skill de verificación. |
| `create-verification-skill` | Crea una skill que maneja tu app como un usuario. `agent-ready` la usa. |
| `maintain-verification-skill` | Revisa que la skill de verificación siga al día con la app. |
| `correct` | Convierte errores repetidos en checks que los hacen imposibles. |
| `reflect` | Saca lecciones de la conversación y propone ediciones a skills. Espera tu aprobación. |
| `show-me-your-work` | Lleva un log TSV de decisiones para trabajo largo o desatendido. |
| `unslop` | Quita patrones de texto generado por IA. |
| `technical-writing` | Aplica el estándar de documentación. |

## Las diferencias entre agy y Claude Code

| Tema | agy | Claude Code |
| --- | --- | --- |
| Comando del modo completo | `/vex-mode` | `/vex-mode:vex-mode` |
| Cómo llega el núcleo | Regla `always_on` del plugin | Hook `session_start.py` |
| Comando de shell que vigila el hook | `run_command` | `Bash` |
| Subagente | `vex-agent` | `vex-mode:vex-agent` |
| Revisión con otro proveedor | `agy --model <modelo>` | Igual si `agy` está instalado; si no, el agente lo salta y lo dice |
| Hooks de un repo preparado con `agent-ready` | `.agents/hooks.json` | La clave `hooks` de `.claude/settings.json` |

El núcleo no llega a los subagentes de Claude Code por el hook de inicio. Les llega por `worker.md`, que está en la primera línea de cada encargo.
