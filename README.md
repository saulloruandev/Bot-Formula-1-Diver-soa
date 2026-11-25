# F1 Discord Racing

Esta versão organiza os arquivos em pastas sem dividir nem reescrever a lógica do bot.

## Estrutura

```text
F1_Discord_Racing/
├── app/
│   ├── __init__.py
│   ├── bot.py
│   └── profiles.json
├── .env
├── .env.example
├── .gitignore
├── bot.py
├── README.md
└── requirements.txt
```

- `bot.py` (raiz): ponto de entrada. É o arquivo que você executa.
- `app/bot.py`: código original do bot, mantido sem alterações.
- `app/profiles.json`: perfis, giros e coleção persistidos.
- `.env`: token do Discord. Não envie esse arquivo ao GitHub.

## Como executar

1. Mantenha seu arquivo `.env` original na raiz desta pasta. Se não tiver, copie `.env.example` para `.env` e coloque seu token em `DISCORD_TOKEN`.
2. Instale as dependências: `pip install -r requirements.txt`
3. Execute: `python bot.py`

**Importante:** não apague `app/profiles.json`, pois ele contém os dados salvos dos jogadores.
