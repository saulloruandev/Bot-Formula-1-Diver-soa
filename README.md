# F1 Discord Racing

Bot de corrida de Fórmula 1 para Discord, desenvolvido em Python com `discord.py`.

## Estrutura

```text
F1_Discord_Racing/
├── app/
│   ├── __init__.py
│   ├── bot.py
│   ├── profiles.json
│   └── assets/
│       ├── circuitos/
│       └── eventos/
├── .env
├── .env.example
├── .gitignore
├── bot.py
├── README.md
└── requirements.txt
```

- `bot.py` (raiz): ponto de entrada.
- `app/bot.py`: lógica principal do bot.
- `app/profiles.json`: dados locais dos jogadores (criado automaticamente; ignorado pelo Git).
- `app/campeonato.json`: histórico e pontuação das temporadas oficiais (criado automaticamente).
- `app/ranking_normal.json`: pontuação e partidas das corridas casuais (criado automaticamente; ignorado pelo Git).
- `app/assets/eventos/`: imagens opcionais para eventos importantes.
- `app/assets/circuitos/`: mapas esquemáticos usados como prévia do circuito no lobby.
- `.env`: token do Discord. Nunca envie esse arquivo ao GitHub.

## Como executar

1. Mantenha seu arquivo `.env` na raiz. Se necessário, copie `.env.example` para `.env` e configure `DISCORD_TOKEN`.
2. Instale as dependências: `pip install -r requirements.txt`.
3. Execute: `python bot.py`.

**Importante:** faça backup de `app/profiles.json` antes de atualizar. A migração dos cinco atributos antigos para os seis novos acontece automaticamente. Os perfis antigos recebem uma habilidade especial uma única vez.

## Sistema de piloto

Os dez pontos pessoais são distribuídos entre seis atributos: Gerenciamento de pneus, Curvas, Velocidade, Classificação, Motor e Controle. A distribuição pode ser alterada pelo botão **Distribuir pontos** no perfil, inclusive fora de uma corrida. A habilidade especial é sorteada separadamente e não pode ser trocada por comando.

Cada jogador possui somente um estilo ativo: ao aceitar um novo resultado, o estilo anterior é substituído. Jogadores novos recebem um estilo aleatório gratuito na primeira criação do perfil. A carta do resultado permanece no canal e o perfil mostra a arte do estilo abaixo da foto pessoal (miniatura no canto superior direito). Os estilos do gacha mantêm as chances originais de raridade e distribuem bônus em seis atributos, incluindo gerenciamento de pneus. Cada raridade recebeu +1 ponto em relação à tabela anterior, e estilos comuns/incomuns podem ter atributos zerados para representar fraquezas reais. Membros podem transferir giros de estilo com `!transferir-giros @membro quantidade`. Habilidades podem ser sorteadas com `!roll-habilidade`; cada giro custa 25k sonhos e é liberado manualmente pelo administrador após pagamento.

## Corridas casuais e oficiais

O bot mantém dois modos independentes:

- **Corrida casual — `!f1`:** lobby com até 10 pilotos. Pode haver vários lobbies simultâneos, inclusive no mesmo canal. Os resultados não alteram o campeonato; somam pontos e partidas no ranking normal (`!rankingnormal`). A pontuação casual é 10, 8, 6, 5, 4, 3, 2 e 1 ponto para as oito primeiras posições; as demais não pontuam. Só entram no ranking corridas com pelo menos 3 humanos e humanos em maioria; partidas que não atendem a essa regra não somam pontos nem partidas.
- **Corrida oficial — `!f1rank`:** lobby com até 10 pilotos. Exige uma temporada ativa e registra resultados no campeonato (`!ranking` e `!campeonato`). Pontuação oficial: 1º = 10, 2º = 7, 3º = 5, 4º = 3, 5º = 1. A volta mais rápida vale +1 ponto somente para quem terminar no top 3. Abandonos e corridas canceladas não pontuam.

Cada lobby tem painel e identificador próprios. Se a classificação e a corrida não forem iniciadas em até 10 minutos, o lobby é encerrado automaticamente. O criador pode cancelar a própria corrida com `!f1cancel`; administradores podem cancelar a corrida de alguém usando `!f1cancel @criador`. Use `!f1status [@criador]` para consultar o estado dos lobbies no canal.

## Campeonato

Inicie uma temporada oficial com `!iniciartemporada Nome`. Ao terminar uma corrida `!f1rank`, o resultado é salvo automaticamente. Consulte com `!campeonato`, `!ranking`, `!temporada`, `!resultado` e `!estatisticas`. Administradores podem encerrar com `!finalizartemporada` ou reiniciar os resultados da temporada ativa com `!resetcampeonato`.

## Transmissão, pneus e pódio

A transmissão separa o painel de corrida do rádio de acontecimentos. Ultrapassagens registram quem passou quem, em qual volta e trecho; eventos importantes são publicados abaixo do painel mais recente. No lobby, **Configurar carro** abre uma tela interativa com os seis atributos identificados, os pontos atuais e um seletor para alterar cada valor. Cada piloto começa com um jogo de pneus e pode usar apenas mais um jogo durante a corrida (2 jogos no total). O lobby mostra uma prévia esquemática do circuito escolhido; os mapas são ilustrativos, não desenhos oficiais em escala. Pit stops normais têm 18 segundos de tempo-base; durante o Safety Car, a perda-base cai para 6 segundos, além da perda adicional variável da equipe. O Safety Car neutraliza o restante da volta do incidente e mais uma volta completa para permitir a limpeza da pista. O criador pode adicionar bots pelo botão **Adicionar bots**; cada bot recebe nome de piloto, estilo aleatório, atributos e decisões automáticas. Corridas com menos de 3 humanos ou com bots em maioria não entram nos rankings; os bots nunca recebem pontos. Pneus inadequados para o clima causam perda de ritmo, desgaste e risco de incidente maiores. Ao final, o bot monta uma arte de pódio com fotos, nomes e tempos em tamanho ampliado, além de exibir a volta mais rápida válida e o número da volta em que ocorreu.

## Imagens dos eventos

Os arquivos são opcionais. Consulte `app/assets/eventos/README.md` para os nomes esperados. Sem uma imagem local, o evento continua sendo mostrado em texto no painel da corrida.


## Imagens de acontecimentos

As imagens ficam em `app/assets/eventos/`, separadas por acontecimento. Adicione arquivos PNG, JPG, JPEG ou WEBP à pasta correspondente; o bot escolhe um deles aleatoriamente. Também é possível configurar links diretos em `app/assets/eventos/links.json`. Consulte o README dessa pasta para instruções.

## Central de informações

Use `!sistema` no Discord para abrir o painel interativo com informações sobre estilos e bônus, pneus e clima, habilidades especiais, atributos, pilotagem, modalidades de corrida e rankings. `!perfil @membro` consulta o perfil de outro piloto.


## Persistência dos perfis dos jogadores

Os perfis, giros, estilos obtidos/equipados, atributos e dados pessoais são salvos em `app/profiles.json` na máquina que executa o bot. Esse arquivo **não deve ser enviado ao GitHub**: ele está no `.gitignore` para que atualizações do código não sobrescrevam o progresso dos jogadores.

O bot cria o arquivo automaticamente quando necessário e mantém apenas uma cópia rotativa em `app/profiles.json.bak` ao salvar. Não são criados arquivos de backup versionados como `v2.bak` a cada inicialização. Faça backup periódico desses dois arquivos. Se trocar de computador ou servidor, copie os arquivos para a pasta `app` da nova instalação antes de iniciar o bot.

**Importante ao atualizar uma instalação antiga:** antes de fazer `git pull`, copie `app/profiles.json` para um local seguro. Como esse arquivo era versionado em versões anteriores, a primeira atualização que o remover do Git pode exigir que você restaure o backup local depois do pull.
