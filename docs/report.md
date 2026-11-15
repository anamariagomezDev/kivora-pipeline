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



\_(fase 3)\_



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

