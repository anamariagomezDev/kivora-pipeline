\# Memoria · Kivora pipeline



\## 1. Decisiones con el agente



| # | Fase | Decisión | Propuesta por | Opciones | Motivo |
|---|---|---|---|---|---|
| 1 | 1 | Analizar en plan mode y escribir en modo manual (permiso por archivo) | Yo, siguiendo assignment.md y la recomendación de human in the loop del profesor | Auto mode / plan / manual | Revisar cada cambio antes de aceptarlo |
| 2 | 1 | Reglas de CLAUDE.md generales, no ligadas a fases | Yo (al revisar el plan del agente) | Reglas por fase / reglas generales | CLAUDE.md debe servir a cualquier sesión futura |
| 3 | 1 | No aprobar "don't ask again" para los comandos uv run ni git | Yo | Aprobar todos / aprobar uno a uno | Evitar que tasks.py deliver, git push o git reset se ejecuten sin control |
| 4 | 2 | D1: la devolución va al día de refunded\_at en Madrid; se aceptan netos negativos | Yo, sobre la propuesta del agente | Día de devolución / de compra / del fichero | Contabilidad registra el movimiento el día en que ocurre |
| 5 | 2 | D2: se rechaza la devolución que hace superar el total del pedido | Yo, sobre la propuesta del agente | Rechazar / aceptar hasta el límite / aceptar todo | Nunca devolver más de lo vendido y dejarlo trazado |
| 6 | 2 | D3: venta = contrato de daily\_sales; las devoluciones de no-ventas se rechazan | Yo, sobre la propuesta del agente | Solo ventas / todo pedido | Definición ya contratada |
| 7 | 2 | D4: qué va a rejected.csv | Yo, sobre la propuesta del agente | — | "No lo tiréis sin más" (KIV-101) |
| 8 | 2 | D5: corregir daily\_sales queda fuera de alcance | Yo | Corregir ahora / documentar | KIV-101 no lo pide y el plazo es corto |
| 9 | 2 | Tres controles de calidad en lugar de seis | Yo, al revisar la propuesta | 3 / 6 | Los dos del enunciado más la unicidad; el resto no suma |

\## 2. Configuración del agente



Archivos: `.claude/settings.json` (permisos y registro del hook, compartido con el equipo) y `.claude/hooks/protect_inputs.py`. Lo que no está ni en `allow` ni en `deny` (editar archivos, `git commit`, `uv sync`...) **pregunta** cada vez.

#### Tabla de protecciones

| Riesgo | Mecanismo | Tipo | Por qué ese tipo |
|---|---|---|---|
| Modificar los datos de entrada (`data/inbox/`, `data/reference/`, `deliveries/`) con las herramientas de edición | Hook `PreToolUse` `protect_inputs.py` sobre `Write\|Edit\|MultiEdit\|NotebookEdit` (`.claude/settings.json:41-45`), respaldado por `CLAUDE.md:24` | Hook (+ instrucción) | Los permisos filtran por herramienta y patrón, pero aquí hay que decidir por la ruta normalizada (relativa, absoluta, `..`, mayúsculas en Windows). El hook lo hace con código y es determinista; la instrucción sola se puede ignorar |
| Modificar los datos de entrada desde la shell (`Set-Content`, `Copy-Item`, `git checkout -- data/...`) | Ninguno automático: esos comandos no están en `allow`, así que piden permiso | Permiso (preguntar) | Limitación conocida: el hook no inspecciona comandos de shell. Reconocer rutas dentro de un comando arbitrario por patrones no es fiable; la red de seguridad es revisar cada petición |
| Recibir una entrega fuera de su fase | `deny` de `tasks.py deliver*` en Bash y PowerShell (`.claude/settings.json:24-25`); `CLAUDE.md:25` | Permiso (deny) | Es un comando concreto y reconocible por prefijo: el deny lo bloquea siempre. La entrega la ejecuto yo con `!`, en su commit propio |
| Subir o reescribir el historial | `deny` de `git push*`, `git reset --hard*`, `git rebase*` en Bash y PowerShell (`.claude/settings.json:26-28`, `30-32`); `CLAUDE.md:29` | Permiso (deny) + instrucción | Comandos con prefijo fijo: el permiso es la herramienta justa y no depende de que el agente lo recuerde |
| Borrar archivos | `deny` de `rm -rf*` en Bash y PowerShell y de `Remove-Item -Recurse*` en PowerShell (`.claude/settings.json:29`, `33-34`); el resto de `Remove-Item` no está permitido y pregunta | Permiso (deny / preguntar) | El borrado recursivo no tiene vuelta atrás, se prohíbe; el resto de borrados se aprueban uno a uno |
| Leer secretos | `deny` de `Read(./.env)` (`.claude/settings.json:35`); `settings.json` no contiene claves | Permiso (deny) | Bloquea la lectura con la herramienta Read aunque Read esté permitido en general (deny gana a allow). Leerlo por shell (`cat`, `Get-Content`) no está permitido y pregunta |
| Dar el trabajo por terminado sin verificar | Sección "Cuándo está terminado un trabajo" (`CLAUDE.md:31-34`) y `allow` de `test`, `check`, `acceptance` (`.claude/settings.json:8-11`, `15-18`) | Instrucción (+ permiso) | Es un criterio de cierre, no una acción que se pueda bloquear. Permitir esos comandos sin preguntar hace barato verificar. Se reforzará en la fase 4 con `acceptance` como señal de parada |
| Perder el control de lo que se ejecuta (comandos encadenados, scripts nuevos) | Lista `allow` corta: solo lectura, `tasks.py test/run/check/acceptance` y `git status/diff/log` (`.claude/settings.json:4-22`) | Permiso (allow) | Se permite sin preguntar solo lo que no modifica nada fuera de `output/` y se repite mucho (fases 1 y 2); lo demás pasa por mí |

#### Mecanismo de extensión: hook `protect_inputs.py`

- **Qué problema resuelve.** `CLAUDE.md:24` prohíbe tocar `data/inbox/` y `deliveries/`, y `data/reference/` (tipos de cambio) tampoco debe tocarse. Ante datos anómalos (como los de KIV-101), lo más rápido para un agente es "arreglar" el CSV en vez de tratar el caso en el pipeline; así los tests pasan pero el pipeline sigue sin tratar ese caso.
- **Por qué un hook.** Se ejecuta antes de cada `Write`, `Edit`, `MultiEdit` o `NotebookEdit`, recibe la ruta destino por stdin y la normaliza (relativa o absoluta, `..`, separadores y mayúsculas de Windows). Si cae dentro de una carpeta protegida sale con código 2 y el motivo en stderr, que Claude Code le muestra al agente. Si el JSON no se puede leer, bloquea (falla cerrado).
- **Qué aporta frente a pedírselo al agente.** Una instrucción en CLAUDE.md se puede ignorar u olvidar en una sesión larga o tras compactar el contexto; el hook es determinista: se ejecuta siempre, sea cual sea el modelo o la sesión, y no depende de que yo revise cada diff. Además le explica al agente el motivo y la alternativa (resolverlo en el pipeline).
- **Prueba real** (PowerShell, `$env:CLAUDE_PROJECT_DIR` = raíz del repo, `... | python .claude/hooks/protect_inputs.py; $LASTEXITCODE`):

| Entrada (`tool_input`) | Código de salida |
|---|---|
| `file_path: data/inbox/2026-09-01/orders.csv` (Write) | 2 (bloqueado) |
| `file_path: docs/report.md` (Edit) | 0 (permitido) |
| `file_path: docs\..\DATA\Reference\fx_rates.csv` | 2 |
| `file_path: <ruta absoluta>/deliveries/2/orders.csv` | 2 |
| `notebook_path: data/inbox/x.ipynb` (NotebookEdit) | 2 |
| `file_path: data/inbox_notes.md` (prefijo parecido, fuera de la carpeta) | 0 |
| stdin que no es JSON | 2 |

  En el primer intento todas las pruebas salían con 2, incluida `docs/report.md`: PowerShell 5.1 antepone un BOM UTF-8 al stdin y el hook no lo aceptaba. Si solo se hubiera mirado el caso del inbox, habría parecido que funcionaba. Se corrigió leyendo stdin como `utf-8-sig` y se repitieron las pruebas.
- **Límite.** Solo cubre las herramientas de edición; las escrituras desde Bash/PowerShell dependen del permiso (preguntar) y de mi revisión.



\## 3. Ciclo de iteración



| # | Fase | Objetivo | Propuesta del agente | Mi revisión | Feedback dado | Cambio y resultado comprobado | Pendiente |
|---|---|---|---|---|---|---|---|
| 1 | 1 | Analizar el pipeline sin modificar código (KIV-100) | Análisis en plan mode con evidencias archivo:línea, recálculo según el contrato y casos sintéticos A–F | Contraste independiente de las cifras clave (7840.72 frente a 7905.15, K-10053, K-10002, GB 09-01, US 09-02) | Errores: "15 de 20 combinaciones" (son 16), frase invertida sobre K-10002, regla de CLAUDE.md ligada a fases | Recalculó con un comando: coinciden 4, no coinciden 16 | — |
| 2 | 1 | Corregir el plan antes de escribir | Al reanudar la sesión, recuperó el plan antiguo (sin correcciones) y lo dio por aprobado | Lo detuve en la petición de permiso, antes de que escribiera ningún archivo | Reenvié las tres correcciones | Aplicó las tres correcciones | — |
| 3 | 1 | Revisar docs/analysis.md antes de crearlo | Vista previa del archivo | Revisé la vista previa | Faltaba la fila de "python run.py" y había una fila de la tabla de tests truncada | Añadió la fila y el apartado "Lo que no se comprueba". El agente afirmó que la fila ya estaba en su borrador; en la vista previa que revisé no aparecía | — |
| 4 | 1 | Revisar CLAUDE.md y KIV-100.md | Reemplazo de CLAUDE.md, respuesta a Irene y verificaciones (run, test, check, interfaz, SHA-256) | Revisé el diff y las verificaciones | Regla de Co-Authored-By imprecisa y una ruta local de mi equipo en analysis.md | Aplicó los dos retoques y comprobó que no quedaban rutas locales | — |
| 5 | 1 | Commit de los entregables | Commit con mensaje en español y Co-Authored-By | Revisé el comando antes de aprobarlo | El primer intento falló en PowerShell 5.1 por las comillas del mensaje (sin crear commit) | Repetido con git commit -F: commit d7279ee, 3 archivos, git status limpio | Tag phase-1 |
| 6 | 2 | Detectar ambigüedades de KIV-101 | Inventario de anomalías con casos y comandos, y 20 ambigüedades con opciones y recomendación | Contraste independiente: 156 ventas, 18490.74, 12 netos negativos, R-1009 | Tomé 5 decisiones de negocio (D1–D5) y reduje los controles de 6 a 3 | El agente confirmó las decisiones y sus consecuencias | — |
| 7 | 2 | Escribir la especificación | spec.md (R1–R18, E1–E19, S1–S8, A1–A20) y reference\_calc.py | Contrasté las 21 filas de E1–E17, los totales y los rechazos con mi propio cálculo: coinciden | Mi mensaje llegó cortado y el agente no asumió mis decisiones; pedí guardar el script en el repositorio; el orden de prioridad del documento no coincidía con el script | Commit 1f2c8a1 con la especificación aprobada | — |
| 8 | 2 | Caso límite refund\_id vacío | El agente detectó que un refund\_id vacío daría conflicting\_duplicate | Revisé el caso sintético | Decidí corregirlo antes del plan | Commit 82f1ca0; además corrigió que un null se convertía en "None" | — |
| 9 | 2 | Plan de implementación | Borrador con T0–T12, riesgos y T10 (comprobar que los tests fallan con el código roto) | Revisión crítica del borrador | P1: acceptance se rompería con la entrega 2; P2: faltaba la fase 3 y los tags; P3: comportamientos fuera de la especificación; P4: contrato innecesario; P5: faltaba exportar la sesión y registrar las vueltas | Commit 09ddd1b con la sección "Revisión del plan" | Fase 3 |

\## 4. Trazabilidad



\_(fase 4)\_



\## 5. Cambio de esquema



\_(fase 5)\_



\## 6. Revisión



\_(fase 6)\_



\## 7. Qué haría distinto



\_(fase 6)\_

