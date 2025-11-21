# Simulador / Notebook — Controle de Semáforo com Lógica Fuzzy

Resumo
------
Notebook (main.ipynb) que implementa um sistema fuzzy para recomendar o tempo do semáforo (`tempo_semaforo`) a partir de variáveis: `fluxo_de_carros`, `fluxo_de_pedestres`, `horario` e `clima`. Usa scikit-fuzzy (skfuzzy) para definir MFs, montar regras e executar a simulação (ControlSystemSimulation).

Requisitos
----------
- Python 3.8+
- Dependências (instalar no notebook ou venv):
  pip install scikit-fuzzy==0.5.0 numpy matplotlib

Como usar o notebook
--------------------
1. Abrir `main.ipynb` no Jupyter / VS Code.  
2. Executar as células na ordem. A primeira célula contém a linha de instalação `pip install scikit-fuzzy==0.5.0`.  
3. Definir entradas em `execucao_simulador.input[...]`, chamar `execucao_simulador.compute()` e visualizar `tempo_semaforo` com `tempo_semaforo.view(sim=execucao_simulador)` ou imprimir `execucao_simulador.output['tempo_semaforo']`.

Variáveis e universos (conforme notebook)
----------------------------------------
- fluxo_de_carros, fluxo_de_pedestres: universo np.arange(0,11,1) → valores inteiros 0..10  
- horario, clima (no notebook definidos também como np.arange(0,11,1)) — neste notebook `horario` e `clima` usam universo 0..10 
- tempo_semaforo (saída): np.arange(0,31,1) → 0..30 segundos

Funções de Pertinência (fuzzificação)
------------------------------------
Todas as MFs são definidas via fuzz.trimf (triangular):
- fluxo_de_carros / fluxo_de_pedestres:
  - Baixo:  [0, 0, 4]
  - Médio:  [2, 5, 8]
  - Alto:   [6, 10, 10]
- horario (no notebook): rotulados como Baixo/Normal/Pico com mesmas trimf acima (universo 0..10)
- clima (no notebook): Ensolarado/Nublado/Chuvoso com mesmas trimf acima
- tempo_semaforo (saída):
  - Baixo:  [0,0,8]
  - Médio:  [6,15,22]
  - Alto:   [18,30,30]

Base de Regras (inferência)
---------------------------
Regras implementadas no notebook (9 regras principais):
1. SE fluxo_de_carros É Alto E horario É Pico ENTÃO tempo_semaforo É Alto.  
2. SE fluxo_de_carros É Médio E fluxo_de_pedestres É Médio E horario É Normal ENTÃO tempo_semaforo É Médio.  
3. SE fluxo_de_carros É Baixo OU fluxo_de_pedestres É Baixo ENTÃO tempo_semaforo É Baixo.  
4. SE fluxo_de_carros É Alto E fluxo_de_pedestres É Alto E horario É Normal ENTÃO tempo_semaforo É Médio.  
5. SE fluxo_de_carros É Alto E fluxo_de_pedestres É Alto E horario É Pico ENTÃO tempo_semaforo É Alto.  
6. SE fluxo_de_carros É Alto E clima É Chuvoso ENTÃO tempo_semaforo É Alto.  
7. SE fluxo_de_carros Baixo E fluxo_de_pedestres Baixo E horario Baixo ENTÃO tempo_semaforo Baixo.  
8. SE fluxo_de_carros Baixo E fluxo_de_pedestres Alto ENTÃO tempo_semaforo Médio.  
9. SE fluxo_de_carros Médio E horario Baixo ENTÃO tempo_semaforo Médio.

- Implementação: regras criadas com `ctrl.Rule` (skfuzzy). AND = min, OR = max (padrões do framework).

Defuzzificação
--------------
- Método: centróide (ControlSystemSimulation.compute()). A saída é um float em segundos: `execucao_simulador.output['tempo_semaforo']`.

Exemplo de execução (célula)
----------------------------
- Atribuição de entradas (exemplo do notebook):
```python
execucao_simulador.input['fluxo_de_carros'] = 2
execucao_simulador.input['fluxo_de_pedestres'] = 10
execucao_simulador.input['horario'] = 4
execucao_simulador.input['clima'] = 5
execucao_simulador.compute()
print(execucao_simulador.output['tempo_semaforo'])
tempo_semaforo.view(sim=execucao_simulador)
```
- Observação: `horario` e `clima` foram definidos com universo 0..10 no notebook; valores usados nas entradas devem respeitar esse universo.

Visualização e Debug
--------------------
- `*.view()` (skfuzzy) plota MFs e o estado do sistema quando passado `sim=execucao_simulador`.  
- Para inspeção manual de graus, `fuzz.interp_membership()` pode ser usado por variável/rotulo.

