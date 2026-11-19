# Primera revisión de cambios en pstack upstream

- **Comando:** `python3 scripts/upstream_drift.py --fetch` contra `cursor/plugins` HEAD `e58dd04`.
- **Resultado:** cambió 1 de los 26 archivos copiados: `skills/vex-mode/SKILL.md`, que viene de `pstack/skills/poteto-mode/SKILL.md` y está adaptado.
- **El cambio upstream:** dos líneas del ruteo de modelos (`gemini-4-carbon-high` → `gemini-4-neon-high`): la del panel de revisión y la del techo de la familia Gemini.
- **Reconciliación:** nuestra adaptación quitó esa sección de ruteo, porque en vex-mode los subagentes heredan el modelo del padre. `grep` confirma que ninguna de esas frases está en nuestro router, así que no hay nada que reaplicar. Se registró con `--accept`: `vendor.lock` guarda el hash y el commit `e58dd04` del archivo, y el reporte vuelve a dar "No drift".
- **Desde ahora:** el workflow semanal `upstream-drift` mantiene el issue "pstack upstream drift".
