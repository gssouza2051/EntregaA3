# Simulador de Semáforo com Spawn Manual

Descrição
---------
Simulador 2D (pygame) de um cruzamento controlado por um controlador Fuzzy (scikit-fuzzy). Dois eixos lógicos (vertical e horizontal) controlam semáforos visuais; carros podem ser spawnados manualmente nas duas direções.

Como funciona (resumo)
----------------------
- Carros são sprites que se movem em linhas retas (up/down/left/right).  
- O controlador Fuzzy (classe `FuzzyController`) recebe:
  - número de carros esperando na via vermelha, e
  - tempo atual do verde (em segundos).
  - retorna uma "prioridade de troca" que o `TrafficLightController` usa para iniciar a sequência amarelo→troca.  
- A detecção de carros "esperando" considera uma área de fila (constante `QUEUE_LENGTH`) e bloqueio por colisão com o carro da frente.  
- Visual: ruas, faixas, semáforos e carros com desenho melhorado (classe `TrafficLight` e `Car`).

Controles
---------
- H: adiciona um carro na via horizontal (alternando esquerda/direita).  
- V: adiciona um carro na via vertical (alternando cima/baixo).  
- ESC / fechar janela: encerra.

Requisitos
----------
- Python 3.11 recomendado (algumas bibliotecas podem falhar em Python 3.12/3.13 devido a módulos legados).  
- Dependências: pygame, scikit-fuzzy, numpy

Instalação e execução (Windows)
-------------------------------
1. Abrir terminal na pasta do projeto:
   cd "EntregaA3"

2. Criar e ativar venv:
   - python -m venv .venv
   - PowerShell: .\.venv\Scripts\Activate.ps1
   - CMD: .venv\Scripts\activate

3. Instalar dependências:
   python -m pip install --upgrade pip setuptools wheel
   python -m pip install pygame scikit-fuzzy numpy

4. Rodar:
   python main.py

Observações e ajustes úteis
--------------------------
- Parâmetros relevantes no código:
  - STOP_* (zonas de parada), QUEUE_LENGTH (tamanho da fila visual),
  - FPS, MIN_GREEN / MAX_GREEN (se presentes), PRIORITY_THRESHOLD (limiar de troca fuzzy).  
  Ajuste esses valores conforme o comportamento observado.

- Se aparecerem erros como "No module named 'imp'" ou "No module named 'distutils'", recomende-se recriar a venv usando Python 3.11.

- Para remover a mensagem do pygame e warnings do pkg_resources, já estão aplicadas no topo do `main.py`:
  - os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
  - warnings.filterwarnings(...)

Arquitetura (rápido)
--------------------
- main.py:
  - Classes principais: `FuzzyController`, `TrafficLight`, `Car`, `TrafficLightController`.
  - `main()` contém loop principal: eventos → percepção (contagem de filas) → update controlador → update sprites → desenho → tick.

Contribuições / melhorias sugeridas
----------------------------------
- múltiplas faixas (lanes), curvas para left/right turns, tipos de veículo diferentes, chegada Poisson, semáforos para pedestres, UI para ajustar parâmetros em tempo real, gravação de métricas (CSV/plots).

Licença
-------
Uso acadêmico / pessoal. Ajuste conforme necessário.

## Como a lógica Fuzzy atua neste simulador

Resumo rápido
- O controlador Fuzzy decide quando trocar qual via fica com o verde a partir de duas entradas:
  1. número de carros esperando na via que está com sinal vermelho (carros_via_vermelha);
  2. tempo que o verde atual já está ativo (tempo_verde_atual, em segundos).
- A saída é uma pontuação contínua chamada `prioridade_troca` (valor numérico entre 0 e 10). Se essa prioridade ultrapassar um limiar (no código: 5.0) a troca é iniciada (verde → amarelo → troca).

Variáveis fuzzy (implementação)
- carros_via_vermelha: antecedente com universo 0..10; usa automf para gerar termos linguísticos 'poucos', 'medio', 'muitos'.
- tempo_verde_atual: antecedente com universo 0..20; definido com três funções triangulares:
  - curto  ≈ [0, 0, 7]
  - medio  ≈ [5, 10, 15]
  - longo  ≈ [12, 20, 20]
- prioridade_troca: consequente com universo 0..10; automf cria termos 'baixa', 'media', 'alta'.

Regras fuzzy (resumidas)
- Se há muitos carros na via vermelha E o tempo de verde atual é longo → prioridade ALTA.
- Se há muitos carros na via vermelha E o tempo de verde atual é médio → prioridade ALTA.
- Se há número médio de carros na via vermelha → prioridade MÉDIA.
- Se há poucos carros na via vermelha → prioridade BAIXA.
- Se o tempo de verde atual é curto → prioridade BAIXA.

Processo de inferência
1. Fuzzificação: converte os valores numéricos de entrada nas pertinências (graus) das funções de pertinência.
2. Avaliação de regras: cada regra combina suas condições (AND usa operação mínima) e produz um conjunto fuzzy de saída parcial.
3. Agregação: as saídas parciais das regras são combinadas em uma única função fuzzy para `prioridade_troca`.
4. Defuzzificação: a função agregada é convertida em um número (método padrão: centroid), produzindo a pontuação final de prioridade (valor contínuo).

Como isso influencia o comportamento do semáforo
- O `TrafficLightController` consulta o FuzzyController a cada atualização, passando:
  - `carros_na_vermelha` (contagem de carros que estão "na fila" com semáforo vermelho),
  - `tempo_verde_segundos` (tempo desde que o verde foi acionado).
- Se a prioridade retornada ≥ 5.0, inicia-se a sequência para trocar (o semáforo atual vai para amarelo; após YELLOW_TIME ocorre a troca de verde).
- Isso evita trocas imediatas e favorece a via que está acumulando espera, equilibrando tempo de serviço e tempo de espera.

Parâmetros relevantes no código
- Limiar de troca: 5.0 (em TrafficLightController.update).
- Duração do amarelo: YELLOW_TIME = 2 * FPS (no código; ajustável).
- Universos e funções de pertinência estão em `FuzzyController.__init__` (use automf e trimf conforme necessidade).

Dicas para ajuste e experimentação
- A sensibilidade do sistema muda alterando:
  - os universos/funções de pertinência (ex.: aumentar alcance de 'muitos');
  - as regras (ex.: penalizar muito tempo de verde mesmo com poucos carros);
  - o limiar de troca (5.0) para tornar o sistema mais conservador ou agressivo.
- Teste com diferentes FPS / LOG_INTERVAL para ver impacto no logging e na resposta do controlador.
- A pontuação `last_priority_score` é registrada e exibida durante a simulação e também é gravada em `metrics.csv` para análise posterior.

Exemplo prático
- Se a via vertical acumula 6 carros enquanto a horizontal já ficou com verde por 12 s, muitas regras irão disparar e a prioridade tende a alto → o controlador irá colocar o semáforo da horizontal em amarelo e depois trocar para vertical.
