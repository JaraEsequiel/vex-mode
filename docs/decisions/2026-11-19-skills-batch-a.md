# Tanda A de skills: tdd, why, architect, unslop, technical-writing

Se trajeron de pstack@e58dd04 las cinco skills que nuestros playbooks ya nombraban. Además se restauraron, palabra por palabra, las líneas del router y de los playbooks de bug-fix y feature que las usan. Las tres corridas de `tax-rounding` fueron estas:

| Eval | Variante (B) | Resultado A | Resultado B | Veredicto |
|---|---|---|---|---|
| `cc500b7097a8` | Tanda A completa | 2/3 | **0/3** | inconclusive |
| `2dd3219903c3` | Tanda A sin las referencias a `architect` (B1) | 3/3 | 1/3 | inconclusive |
| `6a998600e906` | Tanda A + línea "keep the public contract" en bug-fix | 2/3 | **3/3** | **promote** |

## Qué explica los números

- **Todas las fallas de B, y la única de A en el último eval, son el mismo error:** el agente "arregla" el redondeo pasando `invoice_total` a `Decimal` de punta a punta y rompe a quien la llama con `float`. El juez aprobó esas soluciones; las detectó la comprobación oculta, como en #1178.
- **Qué skills leyó cada corrida no predice el resultado.** En B1, la corrida que leyó `tdd` pasó y la que no leyó ninguna falló.
- **Lo que sí lo predice, en 18 de 18 corridas de los tres evals,** es si el test de regresión que escribe el agente llama a la función como lo hacen sus llamadores actuales, con `float`. Si lo hace, conserva la interfaz convirtiendo con `Decimal(str(x))` y pasa. Si no, cambia el contrato y falla.
- **Por eso el arreglo va en nuestro playbook, no en las skills de pstack.** El paso 5 de bug-fix ahora dice (adaptación nuestra): "Keep the public contract: the regression test calls the code the way its existing callers do, with the same argument types, and the fix changes an interface only when the ticket asks for it." Con esa línea, las 3 corridas de B testearon con `float` y pasaron.

## Costo y límites

- B usa un 19 % más de tokens que A.
- Con 3 corridas por brazo, la diferencia de resultado sigue siendo ruido estadístico. Lo que sostiene el veredicto es el mecanismo, consistente en las 18 corridas, y que B no empeora.
- El primer intento del último eval se cortó por falta de memoria (un bucle del generador del HTML del diseño, ya arreglado en `main`). La primera llamada al juez del intento siguiente agotó el timeout de 600 s; se volvió a calificar con `rejudge`, sin repetir las corridas.
- Este eval es del 2026-11-19, anterior a la medida de calidad de código (M5), así que no la trae.
