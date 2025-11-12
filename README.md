# Simulador de Semáforo com Lógica Fuzzy — README (atualizado)

Resumo
------
Simulador 2D (pygame) de um cruzamento controlado por um controlador Fuzzy. Além do controle original por "prioridade de troca", o sistema agora possui uma segunda base fuzzy que recomenda o "Tempo do Semáforo" (segundos) a partir de variáveis ambientais (clima, fluxo de carros, fluxo de pedestres e horário). As variáveis ambientais mudam periodicamente e são exibidas na HUD.

O que são Variáveis Linguísticas (VLs)
-------------------------------------
Variáveis linguísticas representam grandezas numéricas por meio de termos qualitativos (ex.: "Baixo", "Médio", "Alto"). Cada termo tem uma Função de Pertinência (membership function) que indica o grau (0..1) com que um valor numérico pertence ao termo. A lógica fuzzy usa esses graus para avaliar regras IF–THEN em vez de decisões booleanas rígidas.

Entradas e Saídas do Sistema
----------------------------
- Entradas usadas pelo controlador de prioridade (legado/compatibilidade):
  - carros_via_vermelha: número de carros esperando na via que está vermelha (0..10).
  - tempo_verde_atual: tempo, em segundos, que o verde atual já está ativo (0..30).
  - pedestres_esperando: (opcional) contagem de pedestres aguardando.

- Entradas novas (ambiente) usadas para recomendar tempo do semáforo:
  - car_flow (label): "Baixo" / "Médio" / "Alto" — representando fluxo de carros.
  - ped_flow (label): "Baixo" / "Médio" / "Alto" — fluxo de pedestres.
  - horario (label derivado de HH:MM:SS): "Outro" / "Normal" / "Pico" (picos definidos).
  - clima (label): "Ensolarado" / "Nublado" / "Chuvoso".

- Saídas:
  - prioridade_troca (0..10) — pontuação que aciona a sequência amarelo→troca quando >= limiar.
  - tempo_semaforo (0..30 s) — tempo recomendado para manter o verde antes de iniciar troca.

Funções de Pertinência (Fuzzificação)
------------------------------------
Implementadas com `skfuzzy` (trimf/automf):

1. car_flow, ped_flow (Universo 0..10)
   - Baixo  : trimf [0, 0, 4]
   - Médio  : trimf [2, 5, 8]
   - Alto   : trimf [6, 10, 10]

2. horario (Universo 0..2)
   - Outro  : trimf [0, 0, 1]
   - Normal : trimf [0, 1, 2]
   - Pico   : trimf [1, 2, 2]
   - Observação: horários classificados como PICO quando hora em 06:30:00–08:00:00 ou 18:00:00–19:00:00.

3. clima (Universo 0..2)
   - Ensolarado: trimf [0, 0, 1]
   - Nublado   : trimf [0, 1, 2]
   - Chuvoso    : trimf [1, 2, 2]

4. tempo_semaforo (Universo 0..30 segundos) — saída
   - Baixo  : trimf [0, 0, 8]
   - Médio  : trimf [6, 15, 22]
   - Alto   : trimf [18, 30, 30]

5. prioridade_troca (legado) — universo 0..10, criado via automf como 'baixa/media/alta'.

Base de Regras Fuzzy (Inferência)
---------------------------------
Regras implementadas (texto usado para prints de ativação):

1) SE (Fluxo de Carros é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).  
2) SE (Fluxo de Carros é Médio) E (Fluxo de Pedestres é Médio) E (Horário é Normal) ENTÃO (Tempo é Médio).  
3) SE (Fluxo de Carros é Baixo) OU (Fluxo de Pedestres é Baixo) ENTÃO (Tempo é Baixo).  
4) SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Normal) ENTÃO (Tempo é Médio).  
5) SE (Fluxo de Carros é Alto) E (Fluxo de Pedestres é Alto) E (Horário é Pico) ENTÃO (Tempo é Alto).  
6) SE (Fluxo de Carros é Alto) E (Clima é Chuvoso) ENTÃO (Tempo é Alto).  
7) SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Baixo E Horário Outro ENTÃO Tempo Baixo.  
8) SE Fluxo de Carros é Baixo E Fluxo de Pedestres é Alto ENTÃO Tempo Médio.  
9) SE Fluxo de Carros é Médio E Horário é Outro ENTÃO Tempo Médio.

- Implementação: as regras são montadas com objetos `ctrl.Rule` do scikit-fuzzy; para debug existe `evaluate_rules(...)` que calcula os graus de ativação de cada regra (usando interp_membership e min/max) e imprime no terminal quando o ambiente é avaliado.

Defuzzificação
--------------
- Método: centroid (padrão do scikit-fuzzy `ControlSystemSimulation.compute()`).
- Resultado: número real (ex.: `tempo_semaforo = 12.34`) que é usado como tempo recomendado em segundos. O TrafficLightController usa esse valor como critério adicional para iniciar a sequência de troca (se o verde atual exceder esse tempo).

Comportamento Integrado
-----------------------
- O controlador combina duas decisões:
  1. Prioridade de troca (método legado compute_priority() — heurística rápida compatível) → aciona troca quando >= limiar (ex.: 5.0).
  2. Tempo recomendado pela base fuzzy ambiente → se o verde atual exceder esse tempo, inicia troca.
- Pedestres: ao spawnar, é feita solicitação (request_ped_cross) que força a sequência amarelo→troca quando necessário; carros são bloqueados para não invadir faixas (várias proteções no update do sprite).

Logs e Diagnóstico
------------------
- Impressões no terminal:
  - `[FUZZY-PRIOR]` — ativação da heurística de prioridade (componentes).
  - `[FUZZY-TEMPO]` — tempo recomendado e regras (só imprime regras com grau > 0.01).
- HUD: exibe clima, fluxo de carros, fluxo de pedestres e horário; alerta visual ao mudar ambiente.

Ajustes Possíveis
-----------------
- Universos, parâmetros das trimf e limites (por exemplo universo de `car_flow`) podem ser calibrados para comportamento desejado.
- Limiar de troca (atualmente 5.0) e duração do amarelo (YELLOW_TIME) ajustáveis.
- Pode-se substituir `compute_priority` heurística por um subsistema fuzzy dedicado caso deseje unificar decisões.

Execução
--------
1. Criar/ativar venv e instalar dependências: pygame, scikit-fuzzy, numpy.  
2. Rodar: `python main.py`  

