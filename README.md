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
- `app/profiles.json`: perfis, atributos, habilidades, giros e estilos.
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

Os estilos do gacha mantêm suas raridades, chances e bônus atuais. Os bônus antigos são compatibilizados com os atributos novos sem alterar a tabela de raridades.

## Campeonato

Inicie uma temporada com `!iniciartemporada Nome`. Ao terminar cada corrida, o resultado é salvo automaticamente. Consulte com `!campeonato`, `!ranking`, `!temporada`, `!resultado` e `!estatisticas`. Administradores podem encerrar com `!finalizartemporada` ou reiniciar os resultados da temporada ativa com `!resetcampeonato`.

Pontuação: 1º = 10, 2º = 7, 3º = 5, 4º = 3, 5º = 1. A volta mais rápida vale +1 ponto somente para quem terminar no top 3. Abandonos e corridas canceladas não pontuam.

## Imagens dos eventos

Os arquivos são opcionais. Consulte `app/assets/eventos/README.md` para os nomes esperados. Sem uma imagem local, o evento continua sendo mostrado em texto no painel da corrida.
