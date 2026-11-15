\# Memoria · Kivora pipeline



\## 1. Decisiones con el agente



| # | Fase | Decisión | Propuesta por | Opciones | Motivo |

|---|---|---|---|---|---|

| 1 | 1 | Analizar en plan mode y escribir en modo manual (permiso por archivo) | Yo, siguiendo assignment.md y la recomendación de human in the loop del profesor | Auto mode / plan / manual | Revisar cada cambio antes de aceptarlo |

| 2 | 1 | Reglas de CLAUDE.md generales, no ligadas a fases | Yo (al revisar el plan del agente) | Reglas por fase / reglas generales | CLAUDE.md debe servir a cualquier sesión futura |

| 3 | 1 | No aprobar "don't ask again" para los comandos uv run ni git | Yo | Aprobar todos / aprobar uno a uno | Evitar que tasks.py deliver, git push o git reset se ejecuten sin control |



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



\## 4. Trazabilidad



\_(fase 4)\_



\## 5. Cambio de esquema



\_(fase 5)\_



\## 6. Revisión



\_(fase 6)\_



\## 7. Qué haría distinto



\_(fase 6)\_

