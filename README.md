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
- `app/campeonato.json`: histórico e pontuação das temporadas (criado automaticamente).
- `app/assets/eventos/`: imagens opcionais para eventos importantes.
- `.env`: token do Discord. Nunca envie esse arquivo ao GitHub.

## Como executar

1. Mantenha seu arquivo `.env` na raiz. Se necessário, copie `.env.example` para `.env` e configure `DISCORD_TOKEN`.
2. Instale as dependências: `pip install -r requirements.txt`.
3. Execute: `python bot.py`.

**Importante:** faça backup de `app/profiles.json` antes de atualizar. A migração dos cinco atributos antigos para os seis novos acontece automaticamente. Os perfis antigos recebem uma habilidade especial uma única vez.

## Sistema de piloto

Os dez pontos pessoais são distribuídos entre seis atributos: Gerenciamento de pneus, Curvas, Velocidade, Classificação, Motor e Controle. Após a primeira distribuição, os pontos ficam bloqueados. A habilidade especial é sorteada separadamente e não pode ser trocada por comando.

Os estilos do gacha mantêm as chances originais de raridade e agora distribuem bônus em seis atributos, incluindo gerenciamento de pneus. Cada raridade recebeu +1 ponto em relação à tabela anterior, e estilos comuns/incomuns podem ter atributos zerados para representar fraquezas reais. Membros podem transferir giros de estilo com `!transferir-giros @membro quantidade`. Habilidades podem ser sorteadas com `!roll-habilidade`; cada giro custa 25k sonhos e é liberado manualmente pelo administrador após pagamento.

## Campeonato

Inicie uma temporada com `!iniciartemporada Nome`. Ao terminar cada corrida, o resultado é salvo automaticamente. Consulte com `!campeonato`, `!ranking`, `!temporada`, `!resultado` e `!estatisticas`. Administradores podem encerrar com `!finalizartemporada` ou reiniciar os resultados da temporada ativa com `!resetcampeonato`.

Pontuação: 1º = 10, 2º = 7, 3º = 5, 4º = 3, 5º = 1. A volta mais rápida vale +1 ponto somente para quem terminar no top 3. Abandonos e corridas canceladas não pontuam.

## Imagens dos eventos

Os arquivos são opcionais. Consulte `app/assets/eventos/README.md` para os nomes esperados. Sem uma imagem local, o evento continua sendo mostrado em texto no painel da corrida.


## Imagens de acontecimentos

As imagens ficam em `app/assets/eventos/`, separadas por acontecimento. Adicione arquivos PNG, JPG, JPEG ou WEBP à pasta correspondente; o bot escolhe um deles aleatoriamente. Também é possível configurar links diretos em `app/assets/eventos/links.json`. Consulte o README dessa pasta para instruções.

## Central de informações

Use `!sistema` no Discord para abrir o painel interativo com informações sobre estilos e bônus, pneus e clima, habilidades especiais, atributos, pilotagem e novidades do bot. `!perfil @membro` consulta o perfil de outro piloto. `!perfil @membro` consulta o perfil de outro piloto.


## Persistência dos perfis dos jogadores

Os perfis, giros, estilos obtidos/equipados, atributos e dados pessoais são salvos em `app/profiles.json` na máquina que executa o bot. Esse arquivo **não deve ser enviado ao GitHub**: ele está no `.gitignore` para que atualizações do código não sobrescrevam o progresso dos jogadores.

O bot cria o arquivo automaticamente quando necessário e mantém uma cópia anterior em `app/profiles.json.bak` ao salvar. Faça backup periódico desses dois arquivos. Se trocar de computador ou servidor, copie os arquivos para a pasta `app` da nova instalação antes de iniciar o bot.

**Importante ao atualizar uma instalação antiga:** antes de fazer `git pull`, copie `app/profiles.json` para um local seguro. Como esse arquivo era versionado em versões anteriores, a primeira atualização que o remover do Git pode exigir que você restaure o backup local depois do pull.
