# Simulador de Semáforo com Lógica Fuzzy — README (atualizado)

Resumo
------
Simulador 2D (pygame) de um cruzamento controlado por um controlador Fuzzy. Além do controle original por "prioridade de troca", o sistema possui uma base fuzzy que recomenda o `tempo_semaforo` (segundos) a partir de variáveis ambientais (`clima`, `fluxo_de_carros`, `fluxo_de_pedestres`, `hora`). As variáveis ambientais podem ser mudadas manualmente (botão/tecla) e são exibidas na HUD.

O que são Variáveis Linguísticas (VLs)
-------------------------------------
Variáveis linguísticas representam grandezas numéricas por termos qualitativos (ex.: "Baixo", "Médio", "Alto"). Cada termo tem uma Função de Pertinência (membership function) que fornece um grau (0..1). A lógica fuzzy usa esses graus para avaliar regras IF–THEN de forma gradual, não-binária.

Entradas e Saídas do Sistema
----------------------------
- Entradas legado (para prioridade):
  - número de carros na via vermelha (`carros_via` / até 10).
  - tempo que o verde atual já está ativo (`tempo_verde` / segundos).
  - pedestres esperando (`pedestres_esperando`).

- Entradas ambientais (usadas pela base fuzzy de tempo):
  - `fluxo_de_carros` : "Baixo" / "Médio" / "Alto"
  - `fluxo_de_pedestres` : "Baixo" / "Médio" / "Alto"
  - `hora` : string "HH:MM:SS" mapeada para `horario` (Outro/Normal/Pico)
  - `clima` : "Ensolarado" / "Nublado" / "Chuvoso"

- Saídas:
  - `prioridade` (0..10) — score heurístico que pode forçar troca.
  - `tempo_semaforo` (0..30 s) — tempo recomendado para manter o verde.

Funções de Pertinência (Fuzzificação)
------------------------------------
Implementadas com `skfuzzy` (trimf):

1. `fluxo_de_carros`, `fluxo_de_pedestres` (universo 0..10)
   - Baixo : trimf [0, 0, 4]
   - Médio : trimf [2, 5, 8]
   - Alto  : trimf [6, 10, 10]

2. `horario` (universo 0..2)
   - Outro  : trimf [0,0,1]
   - Normal : trimf [0,1,2]
   - Pico   : trimf [1,2,2]
   - (mapeamento feito por `mapear_rotulo_hora_para_valor`)

3. `clima` (universo 0..2)
   - Ensolarado: trimf [0,0,1]
   - Nublado   : trimf [0,1,2]
   - Chuvoso    : trimf [1,2,2]

4. `tempo_semaforo` (universo 0..30)
   - Baixo  : trimf [0,0,8]
   - Médio  : trimf [6,15,22]
   - Alto   : trimf [18,30,30]

Base de Regras Fuzzy (Inferência)
---------------------------------
Regras implementadas (usadas para `tempo_semaforo`):

1) SE (`fluxo_de_carros` é Alto) E (`horario` é Pico) ENTÃO (`tempo_semaforo` é Alto).  
2) SE (`fluxo_de_carros` é Médio) E (`fluxo_de_pedestres` é Médio) E (`horario` é Normal) ENTÃO (`tempo_semaforo` é Médio).  
3) SE (`fluxo_de_carros` é Baixo) OU (`fluxo_de_pedestres` é Baixo) ENTÃO (`tempo_semaforo` é Baixo).  
4) SE (`fluxo_de_carros` é Alto) E (`fluxo_de_pedestres` é Alto) E (`horario` é Normal) ENTÃO (`tempo_semaforo` é Médio).  
5) SE (`fluxo_de_carros` é Alto) E (`fluxo_de_pedestres` é Alto) E (`horario` é Pico) ENTÃO (`tempo_semaforo` é Alto).  
6) SE (`fluxo_de_carros` é Alto) E (`clima` é Chuvoso) ENTÃO (`tempo_semaforo` é Alto).  
7) SE `fluxo_de_carros` Baixo E `fluxo_de_pedestres` Baixo E `horario` Outro ENTÃO `tempo_semaforo` Baixo.  
8) SE `fluxo_de_carros` Baixo E `fluxo_de_pedestres` Alto ENTÃO `tempo_semaforo` Médio.  
9) SE `fluxo_de_carros` Médio E `horario` Outro ENTÃO `tempo_semaforo` Médio.

- Implementação: regras criadas com `ctrl.Rule` do `skfuzzy`. Para debug existe `avaliar_regras(...)` que calcula graus por `fuzz.interp_membership` e combinações min/max, e imprime apenas regras com grau > 0.01.

Defuzzificação
--------------
- Método: centróide (usado por `ControlSystemSimulation.compute()`).
- Saída: `tempo_semaforo` em segundos (float) usado pelo `ControladorSemaforo` como referência adicional para iniciar troca.

Comportamento Integrado
-----------------------
- Decisão híbrida:
  - Heurística de prioridade (`prioridade_de_computacao`) produz `prioridade` (0–10). Se `prioridade >= 5.0` → força troca.
  - Caso contrário, se `tempo_verde >= tempo_semaforo` (quando disponível) → inicia troca.
- Pedestres acionam `requisicao_travessia_pedestre` que inicia sequência amarelo→troca.
- Mudança manual de ambiente (botão/tecla E) reseta carros/pedestres para testes limpos.

Logs e Diagnóstico
------------------
- Impressões no terminal:
  - `[FUZZY-PRIOR]` — componentes da prioridade.
  - `[FUZZY-TEMPO]` — `tempo_semaforo` calculado e regras ativadas (graus).
- HUD exibe `clima`, `fluxo_de_carros`, `fluxo_de_pedestres`, `hora`, `tempo_recomendado` e `prioridade`.

Execução
--------
1. Criar/ativar venv e instalar dependências: pygame, scikit-fuzzy, numpy.  
2. Rodar: `python main.py`
