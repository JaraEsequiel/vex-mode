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
- **Lo que sí lo predice, en las 18 corridas de los brazos A y B de los tres evals,** es si el test de regresión que escribe el agente llama a la función como lo hacen sus llamadores actuales, con `float`. Si lo hace, conserva la interfaz convirtiendo con `Decimal(str(x))` y pasa. Si no, cambia el contrato y falla.
- **Por eso el arreglo va en nuestro playbook, no en las skills de pstack.** El paso 5 de bug-fix ahora dice (adaptación nuestra): "Keep the public contract: the regression test calls the code the way its existing callers do, with the same argument types, and the fix changes an interface only when the ticket asks for it." Con esa línea, las 3 corridas de B testearon con `float` y pasaron.

## Costo y límites

- B usa un 19 % más de tokens que A.
- **La evidencia sale del mismo caso que inspiró el arreglo:** la línea se escribió a partir de fallas de `tax-rounding` y se midió solo en `tax-rounding`, con 3 corridas por brazo. No muestra que generalice a otros bugs; para eso hace falta un caso distinto.
- **"Promote" respalda la tanda A junto con la línea, no sola.** La tanda A sola dio 0/3 contra 2/3 (`cc500b7097a8`).
- Con 3 corridas por brazo, la diferencia de resultado sigue siendo ruido estadístico. Lo que sostiene el veredicto es el mecanismo, consistente en las 18 corridas, y que B no empeora.
- El primer intento del último eval se cortó por falta de memoria (un bucle del generador del HTML del diseño, ya arreglado en `main`). La primera llamada al juez del intento siguiente agotó el timeout de 600 s; se volvió a calificar con `rejudge`, sin repetir las corridas.
- Este eval es del 2026-11-19, anterior a la medida de calidad de código (M5), así que no la trae.

## Seguimiento: la línea en el paso 3 y la primera medición de calidad

- **Eval `67413f0d1cc4`** (es la primera corrida con la medida de calidad del M5). Además del cambio de paso, la línea ahora incluye el boceto de `architect` y dice "request" en vez de "ticket". Resultado: B 3/3, A 2/3, **promote**. Las 3 corridas de B testearon con `float`.
- **Calidad (solo sobre las corridas que pasan):**
  - B sale mejor que A en líneas removibles (0 contra 2), en simplicidad según el juez y en líneas de test.
  - El resto de las medidas da ruido.
  - Ninguna medida que bloquea empeora.
- **Lo que vio el juez de contrato y el check no:** `judge_contract` da 0 en los tres brazos. Incluso los parches que pasan convierten solo el precio a `Decimal`, así que una cantidad fraccionaria (`invoice_total([(10.0, 1.5)])`) ahora lanza `TypeError`. Además, varios cambian el tipo de retorno de `line_total` o `read_lines`. El `check.py` oculto solo prueba cantidades enteras y acepta retornos `Decimal`, por eso no lo detecta.
- **Pendiente:** reforzar `check.py` para que pruebe cantidades `float` y tipos de retorno. Con eso el resultado mediría el contrato completo, no solo el caso del redondeo.

## Comprobación estricta del contrato

- **Decisión del usuario:** la comprobación oculta de `tax-rounding` exige el contrato público completo.
  - Acepta `float` en precios, cantidades y `tax_rate`.
  - `invoice_total` devuelve `float`.
  - `line_total` y `read_lines` siguen mezclándose con `float`.
  - El comando imprime lo mismo.
- **Replay:** sobre los 8 parches de la corrida `20261119-182057-379714`, la comprobación nueva reprobó los 8. Incluye los que pasaban la comprobación vieja.
- **Eval `c8e9083ef54b`** (bug-fix pasa a nombrar también los tipos de retorno): B 1/3, A 1/3, C 2/3. Veredicto: **inconclusive**.
  - Las dos fallas de B rompen cantidades fraccionarias: convierten solo el precio a `Decimal`. Como el CSV tiene cantidades enteras, el agente no considera que `1.5` sea una llamada válida.
  - La línea queda porque no empeora y va en la dirección de los criterios del usuario, pero su efecto no está medido.
  - Seguir ajustándola contra este único caso sería sobreajustar (§9.6). Lo que sigue es un segundo caso distinto, sacado de un ticket real.
