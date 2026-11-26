import os
import json
import random
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, List, TypedDict
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

MIN_PLAYERS = 2
MAX_PLAYERS = 5
TOTAL_LAPS = 10
SKILL_POINTS = 10
OVERTAKE_DETECTION_SECONDS = 1.0  # Ajuste para 1.5 para uma corrida mais casual
SEGMENTS_PER_LAP = 6  # sequência própria por circuito

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CIRCUITS = {
    "Interlagos": {
        "base_lap": 102.35,
        "corners": 0.28, "straights": 0.27, "braking": 0.18,
        "acceleration": 0.17, "control": 0.10,
        "segments": ["reta", "curva", "curva", "reta", "curva", "reta"],
    },
    "Monza": {
        "base_lap": 83.20,
        "corners": 0.15, "straights": 0.42, "braking": 0.20,
        "acceleration": 0.15, "control": 0.08,
        "segments": ["reta", "reta", "curva", "reta", "reta", "curva"],
    },
    "Silverstone": {
        "base_lap": 92.80,
        "corners": 0.34, "straights": 0.23, "braking": 0.15,
        "acceleration": 0.16, "control": 0.12,
        "segments": ["curva", "curva", "reta", "curva", "reta", "curva"],
    },
}

WEATHER = {
    "Sol": {"rain": 0.00, "ambient": (25, 34), "track": (35, 48), "surface": "Seca"},
    "Parcialmente nublado": {"rain": 0.00, "ambient": (21, 30), "track": (29, 40), "surface": "Seca"},
    "Nublado": {"rain": 0.05, "ambient": (18, 27), "track": (22, 32), "surface": "Seca"},
    "Chuva leve": {"rain": 0.35, "ambient": (16, 24), "track": (18, 27), "surface": "Úmida"},
    "Chuva forte": {"rain": 0.80, "ambient": (14, 22), "track": (15, 23), "surface": "Molhada"},
}

TIRES = {
    "Soft": {"label": "Macio (Soft)", "grip": 1.08, "wear": 1.45, "dry": 1.00, "damp": 0.78, "wet": 0.52},
    "Medium": {"label": "Médio (Medium)", "grip": 1.00, "wear": 1.00, "dry": 1.00, "damp": 0.88, "wet": 0.65},
    "Hard": {"label": "Duro (Hard)", "grip": 0.94, "wear": 0.70, "dry": 0.96, "damp": 0.82, "wet": 0.58},
    "Intermediate": {"label": "Intermediário (Intermediate)", "grip": 0.96, "wear": 0.90, "dry": 0.78, "damp": 1.05, "wet": 0.84},
    "Wet": {"label": "Chuva extrema (Wet)", "grip": 0.92, "wear": 1.00, "dry": 0.55, "damp": 0.85, "wet": 1.10},
}

SKILL_FIELDS = (
    ("tyre_management", "Gerenciamento de pneus", "🛞"),
    ("curves", "Curvas", "🌀"),
    ("speed", "Velocidade", "🏎️"),
    ("qualifying", "Classificação", "⏱️"),
    ("engine", "Motor", "⚙️"),
    ("control", "Controle", "🎯"),
)
STYLE_SKILL_MAP = {
    "tyre_management": "tyre_management",
    "curves": "curves",
    "speed": "straights",
    "qualifying": "braking",
    "engine": "acceleration",
    "control": "control",
}
ABILITY_CATALOG = {
    "Ultrapassador Nato": "Bônus pequeno em tentativas de ultrapassagem.",
    "Largada Explosiva": "Pequena vantagem na primeira volta.",
    "Especialista em DRS": "Bônus leve de velocidade em retas ao atacar.",
    "Defensor Nato": "Reduz um pouco a chance de ser ultrapassado.",
    "Mãos de Cirurgião": "Reduz discretamente o risco de erro.",
    "Sangue Frio": "Reduz o impacto de decisões agressivas.",
    "Mestre dos Pneus": "Reduz levemente o desgaste dos pneus.",
    "Pit Stop Perfeito": "Pequena recuperação de desgaste no início.",
    "Rei da Chuva": "Reduz a penalidade em condições de chuva.",
    "Motorista de Qualificação": "Pequeno bônus na classificação.",
    "Recuperação Rápida": "Recupera um pouco mais de energia.",
    "Última Volta": "Pequeno bônus de ritmo na última volta.",
}
DRIVING_MODES = {
    "normal": {"label": "Normal", "pace": 0.0, "risk": 0.0, "defense": 0.0, "attack": 0.0},
    "aggressive": {"label": "Agressivo", "pace": -0.22, "risk": 0.12, "defense": -0.04, "attack": 0.16},
    "defensive": {"label": "Defensivo", "pace": 0.18, "risk": -0.08, "defense": 0.18, "attack": -0.12},
    "safe": {"label": "Seguro", "pace": 0.30, "risk": -0.16, "defense": 0.04, "attack": -0.18},
}


class DecisionAction(TypedDict, total=False):
    mode: str
    attack: bool
    boost: bool
    line: str
    pit: bool
    pit_tire: str


@dataclass
class Driver:
    user: discord.Member
    race_name: Optional[str] = None
    team_name: Optional[str] = None
    favorite_tire: Optional[str] = None
    tyre_management: int = 0
    curves: int = 0
    speed: int = 0
    qualifying: int = 0
    engine: int = 0
    control: int = 0
    # Espelhos para manter compatibilidade com a lógica de corrida existente.
    straights: int = 0
    braking: int = 0
    acceleration: int = 0
    ability: Optional[str] = None
    tire: Optional[str] = None
    ready: bool = False
    qualifying_time: Optional[float] = None
    grid_position: Optional[int] = None
    total_time: float = 0.0
    last_lap_time: float = 0.0
    best_lap_time: Optional[float] = None
    tire_wear: float = 0.0  # 0-100
    energy: float = 100.0  # energia de jogo, 0-100
    distance: float = 0.0  # progresso em unidades de segmento
    finished: bool = False
    current_mode: str = "normal"
    chosen_action: Optional[DecisionAction] = None
    lap_segment_times: List[float] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    style_name: Optional[str] = None
    style_tyre_management: int = 0
    style_curves: int = 0
    style_straights: int = 0
    style_braking: int = 0
    style_acceleration: int = 0
    style_control: int = 0
    car_damage: float = 0.0  # 0-100, cresce durante a corrida
    retired: bool = False
    pit_stops: int = 0
    last_pit_lap: int = 0

    def effective_skill(self, attribute):
        return getattr(self, attribute) + getattr(self, f"style_{attribute}", 0)

    @property
    def total_skills(self):
        return sum(getattr(self, key) for key, _, _ in SKILL_FIELDS)

    @property
    def skills_complete(self):
        return self.total_skills == SKILL_POINTS

    @property
    def skill_summary(self):
        return " | ".join(f"{label}: {getattr(self, key)}" for key, label, _ in SKILL_FIELDS)

    @property
    def lobby_status(self):
        if self.ready:
            return "🟢 Pronto"
        if self.tire is not None or self.total_skills > 0:
            return "🟡 Configurando"
        return "⚪ Configurando"


@dataclass
class Race:
    channel: discord.abc.Messageable
    channel_id: int
    guild_id: int
    host_id: int
    circuit_name: str
    weather_name: str
    ambient_temp: int
    track_temp: int
    surface: str
    drivers: Dict[int, Driver] = field(default_factory=dict)
    started: bool = False
    qualifying_done: bool = False
    race_started: bool = False
    current_lap: int = 0
    current_segment: int = 0
    message: Optional[discord.Message] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    decision_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    race_task: Optional[asyncio.Task] = None
    total_laps: int = TOTAL_LAPS
    decision_seconds: int = 45
    current_decision_label: str = "Aguardando decisões"
    current_segment_type: str = "reta"
    safety_car_laps: int = 0
    early_finish: bool = False

    @property
    def full(self):
        return len(self.drivers) >= MAX_PLAYERS

    @property
    def all_ready(self):
        return len(self.drivers) >= MIN_PLAYERS and all(d.ready for d in self.drivers.values())


races: Dict[int, Race] = {}

# Dados mutáveis dos jogadores ficam fora do controle de versão.
# O arquivo permanece em app/profiles.json na instalação local, mas é ignorado pelo Git.
PROFILE_FILE = Path(__file__).with_name("profiles.json")
PROFILE_BACKUP_FILE = PROFILE_FILE.with_suffix(".json.bak")

def write_profiles_file():
    """Salva perfis de forma atômica e mantém um backup do arquivo anterior."""
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(USER_PROFILES, ensure_ascii=False, indent=2)
    temporary = PROFILE_FILE.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    if PROFILE_FILE.exists():
        temporary_backup = PROFILE_FILE.with_suffix(".json.bak.tmp")
        temporary_backup.write_text(PROFILE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        temporary_backup.replace(PROFILE_BACKUP_FILE)
    temporary.replace(PROFILE_FILE)
PROFILE_PRESETS = {
    "balanced": {
        "label": "Piloto equilibrado",
        "emoji": "⚖️",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "description": "Versátil em retas e curvas, sem fraqueza marcante."
    },
    "corner": {
        "label": "Especialista em curvas",
        "emoji": "🌀",
        "skills": {
            "curves": 3,
            "straights": 1,
            "braking": 2,
            "acceleration": 1,
            "control": 3
        },
        "description": "Forte em trechos técnicos e curvas."
    },
    "speed": {
        "label": "Velocista",
        "emoji": "🚀",
        "skills": {
            "curves": 1,
            "straights": 3,
            "braking": 1,
            "acceleration": 3,
            "control": 2
        },
        "description": "Muito rápido nas retas e saídas."
    },
    "precision": {
        "label": "Precisão e frenagem",
        "emoji": "🎯",
        "skills": {
            "curves": 2,
            "straights": 1,
            "braking": 3,
            "acceleration": 1,
            "control": 3
        },
        "description": "Controle e frenagem elevados."
    },
    "launch": {
        "label": "Arrancada e freios",
        "emoji": "⚡",
        "skills": {
            "curves": 1,
            "straights": 2,
            "braking": 2,
            "acceleration": 3,
            "control": 2
        },
        "description": "Boa aceleração e frenagem."
    },
    "rain": {
        "label": "Especialista em chuva",
        "emoji": "🌧️",
        "skills": {
            "curves": 2,
            "straights": 1,
            "braking": 2,
            "acceleration": 1,
            "control": 4
        },
        "description": "Controle extra para condições instáveis."
    }
}

def load_profiles():
    """Carrega os dados locais sem modificá-los antes de criar o backup de migração."""
    try:
        if PROFILE_FILE.exists():
            data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        print("⚠️ profiles.json inválido ou inacessível; os dados não serão sobrescritos.")
    return {}

USER_PROFILES = load_profiles()

def migrate_skill_distribution(skills):
    """Converte os cinco atributos antigos para seis sem retirar pontos existentes."""
    skills = skills if isinstance(skills, dict) else {}
    if "speed" not in skills and "straights" in skills:
        values = {
            "tyre_management": 0,
            "curves": max(0, int(skills.get("curves", 0))),
            "speed": max(0, int(skills.get("straights", 0))),
            "qualifying": max(0, int(skills.get("braking", 0))),
            "engine": max(0, int(skills.get("acceleration", 0))),
            "control": max(0, int(skills.get("control", 0))),
        }
    else:
        values = {key: max(0, int(skills.get(key, 0))) for key, _, _ in SKILL_FIELDS}
    total = sum(values.values())
    if total <= 0:
        return {"tyre_management": 0, "curves": 2, "speed": 2, "qualifying": 2, "engine": 2, "control": 2}
    if total != SKILL_POINTS:
        exact = {key: value * SKILL_POINTS / total for key, value in values.items()}
        scaled = {key: int(value) for key, value in exact.items()}
        remainder = SKILL_POINTS - sum(scaled.values())
        for key in sorted(exact, key=lambda k: exact[k] - scaled[k], reverse=True)[:remainder]:
            scaled[key] += 1
        values = scaled
    return values

# Gacha de estilos: loja apenas visual; confirmação de compra não consulta a Loritta.
RARITY_DATA = {
    "Comum": {
        "points": 6,
        "chance": 50,
        "color": 9807270,
        "emoji": "⚪"
    },
    "Incomum": {
        "points": 9,
        "chance": 28,
        "color": 3066993,
        "emoji": "🟢"
    },
    "Raro": {
        "points": 12,
        "chance": 15,
        "color": 3447003,
        "emoji": "🔵"
    },
    "Épico": {
        "points": 16,
        "chance": 5,
        "color": 10181046,
        "emoji": "🟣"
    },
    "Lendário": {
        "points": 21,
        "chance": 2,
        "color": 15844367,
        "emoji": "🟠"
    }
}
# Distribuições individualizadas dos 40 estilos; a soma de cada vetor é igual aos pontos da raridade.
PILOT_STYLES = [
    {
        "name": "Lance Stroll",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Adaptação e controle"
    },
    {
        "name": "Kevin Magnussen",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Frenagem e defesa"
    },
    {
        "name": "Nicholas Latifi",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Ritmo de reta"
    },
    {
        "name": "Nikita Mazepin",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Aceleração"
    },
    {
        "name": "Pastor Maldonado",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Ataque e frenagem"
    },
    {
        "name": "Marcus Ericsson",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Retas"
    },
    {
        "name": "Jolyon Palmer",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Equilíbrio técnico"
    },
    {
        "name": "Sergey Sirotkin",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Frenagem"
    },
    {
        "name": "Rio Haryanto",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Retas e controle"
    },
    {
        "name": "Bruno Senna",
        "rarity": "Comum",
        "skills": {
            "curves": 1,
            "straights": 1,
            "braking": 1,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Curvas e controle"
    },
    {
        "name": "Pierre Gasly",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Versatilidade"
    },
    {
        "name": "Esteban Ocon",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 1,
            "acceleration": 1,
            "control": 2
        },
        "trait": "Controle e defesa"
    },
    {
        "name": "Sergio Pérez",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 1,
            "acceleration": 1,
            "control": 2
        },
        "trait": "Gestão de pneus"
    },
    {
        "name": "Valtteri Bottas",
        "rarity": "Incomum",
        "skills": {
            "curves": 1,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 1
        },
        "trait": "Velocidade em reta"
    },
    {
        "name": "Mark Webber",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Ritmo e ataque"
    },
    {
        "name": "Felipe Massa",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Curvas e consistência"
    },
    {
        "name": "Rubens Barrichello",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 1,
            "acceleration": 1,
            "control": 2
        },
        "trait": "Controle e adaptação"
    },
    {
        "name": "David Coulthard",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Ritmo"
    },
    {
        "name": "Giancarlo Fisichella",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Frenagem"
    },
    {
        "name": "Nico Hülkenberg",
        "rarity": "Incomum",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 1
        },
        "trait": "Consistência"
    },
    {
        "name": "Charles Leclerc",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Ataque em curvas e frenagem"
    },
    {
        "name": "Lando Norris",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Curvas e controle"
    },
    {
        "name": "Oscar Piastri",
        "rarity": "Raro",
        "skills": {
            "curves": 2,
            "straights": 3,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Precisão e consistência"
    },
    {
        "name": "George Russell",
        "rarity": "Raro",
        "skills": {
            "curves": 2,
            "straights": 3,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Pilotagem limpa"
    },
    {
        "name": "Daniel Ricciardo",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Frenagens tardias"
    },
    {
        "name": "Jenson Button",
        "rarity": "Raro",
        "skills": {
            "curves": 2,
            "straights": 2,
            "braking": 2,
            "acceleration": 1,
            "control": 4
        },
        "trait": "Adaptação e controle"
    },
    {
        "name": "Nico Rosberg",
        "rarity": "Raro",
        "skills": {
            "curves": 2,
            "straights": 3,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Precisão técnica"
    },
    {
        "name": "Nigel Mansell",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Agressividade e aceleração"
    },
    {
        "name": "Damon Hill",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Curvas e frenagem"
    },
    {
        "name": "Juan Pablo Montoya",
        "rarity": "Raro",
        "skills": {
            "curves": 3,
            "straights": 2,
            "braking": 2,
            "acceleration": 2,
            "control": 2
        },
        "trait": "Ataque e velocidade"
    },
    {
        "name": "Sebastian Vettel",
        "rarity": "Épico",
        "skills": {
            "curves": 3,
            "straights": 3,
            "braking": 3,
            "acceleration": 3,
            "control": 3
        },
        "trait": "Tração e curvas"
    },
    {
        "name": "Fernando Alonso",
        "rarity": "Épico",
        "skills": {
            "curves": 3,
            "straights": 3,
            "braking": 3,
            "acceleration": 2,
            "control": 4
        },
        "trait": "Versatilidade e leitura de corrida"
    },
    {
        "name": "Lewis Hamilton",
        "rarity": "Épico",
        "skills": {
            "curves": 4,
            "straights": 3,
            "braking": 3,
            "acceleration": 2,
            "control": 3
        },
        "trait": "Consistência e adaptação"
    },
    {
        "name": "Max Verstappen",
        "rarity": "Épico",
        "skills": {
            "curves": 4,
            "straights": 3,
            "braking": 3,
            "acceleration": 3,
            "control": 2
        },
        "trait": "Precisão e agressividade"
    },
    {
        "name": "Kimi Räikkönen",
        "rarity": "Épico",
        "skills": {
            "curves": 3,
            "straights": 3,
            "braking": 3,
            "acceleration": 3,
            "control": 3
        },
        "trait": "Controle e ritmo"
    },
    {
        "name": "Ayrton Senna",
        "rarity": "Lendário",
        "skills": {
            "curves": 5,
            "straights": 2,
            "braking": 5,
            "acceleration": 3,
            "control": 5
        },
        "trait": "Curvas, precisão e domínio na chuva"
    },
    {
        "name": "Michael Schumacher",
        "rarity": "Lendário",
        "skills": {
            "curves": 4,
            "straights": 5,
            "braking": 3,
            "acceleration": 5,
            "control": 3
        },
        "trait": "Ritmo, técnica e aceleração"
    },
    {
        "name": "Alain Prost",
        "rarity": "Lendário",
        "skills": {
            "curves": 3,
            "straights": 5,
            "braking": 5,
            "acceleration": 2,
            "control": 5
        },
        "trait": "Gestão de corrida e eficiência"
    },
    {
        "name": "Niki Lauda",
        "rarity": "Lendário",
        "skills": {
            "curves": 4,
            "straights": 3,
            "braking": 5,
            "acceleration": 3,
            "control": 5
        },
        "trait": "Precisão e consistência"
    },
    {
        "name": "Juan Manuel Fangio",
        "rarity": "Lendário",
        "skills": {
            "curves": 4,
            "straights": 5,
            "braking": 3,
            "acceleration": 3,
            "control": 5
        },
        "trait": "Controle e adaptação"
    }
]

# Expande os estilos para seis atributos. Cada raridade recebe +1 ponto.
# Os estilos comuns/incomuns podem ter uma fraqueza real (atributo zerado).
def expand_style_distributions():
    keys = ("curves", "straights", "braking", "acceleration", "control")
    for index, style in enumerate(PILOT_STYLES):
        old = {key: max(0, int(style.get("skills", {}).get(key, 0))) for key in keys}
        old_total = sum(old.values())
        target = RARITY_DATA[style["rarity"]]["points"]
        tyre_points = index % 3
        remaining = target - tyre_points
        if old_total:
            exact = {key: old[key] * remaining / old_total for key in keys}
            allocated = {key: int(value) for key, value in exact.items()}
            remainder = remaining - sum(allocated.values())
            for key in sorted(keys, key=lambda item: exact[item] - allocated[item], reverse=True)[:remainder]:
                allocated[key] += 1
        else:
            allocated = {key: 0 for key in keys}
            allocated["control"] = remaining
        if style["rarity"] in ("Comum", "Incomum") and index % 2 == 0:
            weakest = keys[index % len(keys)]
            if allocated[weakest] == 0:
                weakest = next(
                    (keys[(index + offset) % len(keys)] for offset in range(1, len(keys)) if allocated[keys[(index + offset) % len(keys)]] > 0),
                    weakest
                )
            lost = allocated[weakest]
            allocated[weakest] = 0
            strongest = max((key for key in keys if key != weakest), key=lambda key: allocated[key])
            allocated[strongest] += lost
        style["skills"] = {"tyre_management": tyre_points, **allocated}

expand_style_distributions()

# IDs dos cargos dos estilos: substitua None pelos IDs reais do seu servidor. NÃO invente IDs.
PILOT_ROLE_IDS = {
    'Lance Stroll': 1570222401315147896,  # ID do cargo de Lance Stroll
    'Kevin Magnussen': 1570222403852828672,  # ID do cargo de Kevin Magnussen
    'Nicholas Latifi': 1570222406478471269,  # ID do cargo de Nicholas Latifi
    'Nikita Mazepin': 1570222409296912476,  # ID do cargo de Nikita Mazepin
    'Pastor Maldonado': 1570222412069474304,  # ID do cargo de Pastor Maldonado
    'Marcus Ericsson': 1570222414648836136,  # ID do cargo de Marcus Ericsson
    'Jolyon Palmer': 1570222417215889558,  # ID do cargo de Jolyon Palmer
    'Sergey Sirotkin': 1570222419514364076,  # ID do cargo de Sergey Sirotkin
    'Rio Haryanto': 1570222422152454264,  # ID do cargo de Rio Haryanto
    'Bruno Senna': 1570222424451059732,  # ID do cargo de Bruno Senna
    'Pierre Gasly': 1570223289043910827,  # ID do cargo de Pierre Gasly
    'Esteban Ocon': 1570223292839891066,  # ID do cargo de Esteban Ocon
    'Sergio Pérez': 1570223296174362785,  # ID do cargo de Sergio Pérez
    'Valtteri Bottas': 1570223298720301177,  # ID do cargo de Valtteri Bottas
    'Mark Webber': 1570223301253660733,  # ID do cargo de Mark Webber
    'Felipe Massa': 1570223303707328583,  # ID do cargo de Felipe Massa
    'Rubens Barrichello': 1570223306819371130,  # ID do cargo de Rubens Barrichello
    'David Coulthard': 1570223309197541387,  # ID do cargo de David Coulthard
    'Giancarlo Fisichella': 1570223311974174810,  # ID do cargo de Giancarlo Fisichella
    'Nico Hülkenberg': 1570223314029383781,  # ID do cargo de Nico Hülkenberg
    'Charles Leclerc': 1570224069880713318,  # ID do cargo de Charles Leclerc
    'Lando Norris': 1570224073940803584,  # ID do cargo de Lando Norris
    'Oscar Piastri': 1570224076625158214,  # ID do cargo de Oscar Piastri
    'George Russell': 1570224079313703035,  # ID do cargo de George Russell
    'Daniel Ricciardo': 1570224082358632458,  # ID do cargo de Daniel Ricciardo
    'Jenson Button': 1570224085777252473,  # ID do cargo de Jenson Button
    'Nico Rosberg': 1570224088973058129,  # ID do cargo de Nico Rosberg
    'Nigel Mansell': 1570224092060192996,  # ID do cargo de Nigel Mansell
    'Damon Hill': 1570224095193337887,  # ID do cargo de Damon Hill
    'Juan Pablo Montoya': 1570224098225692724,  # ID do cargo de Juan Pablo Montoya
    'Sebastian Vettel': 1570224964840464595,  # ID do cargo de Sebastian Vettel
    'Fernando Alonso': 1570224967696523264,  # ID do cargo de Fernando Alonso
    'Lewis Hamilton': 1570224970481795092,  # ID do cargo de Lewis Hamilton
    'Max Verstappen': 1570224972935467018,  # ID do cargo de Max Verstappen
    'Kimi Räikkönen': 1570224975573422170,  # ID do cargo de Kimi Räikkönen
    'Ayrton Senna': 1570225542790123661,  # ID do cargo de Ayrton Senna
    'Michael Schumacher': 1570225550172356809,  # ID do cargo de Michael Schumacher
    'Alain Prost': 1570225552768372926,  # ID do cargo de Alain Prost
    'Niki Lauda': 1570225555482087596,  # ID do cargo de Niki Lauda
    'Juan Manuel Fangio': 1570225558036422757,  # ID do cargo de Juan Manuel Fangio
}

PROFILE_MIGRATION_VERSION = 2
PROFILE_MIGRATION_BACKUP_FILE = PROFILE_FILE.with_name(
    f"profiles.json.pre-migration-v{PROFILE_MIGRATION_VERSION}.bak"
)

def migrate_existing_profiles():
    """Normaliza perfis antigos e mantém somente o estilo atualmente equipado."""
    if not isinstance(USER_PROFILES, dict) or not USER_PROFILES:
        return
    changed = False
    styles_by_name = {item["name"].casefold(): item for item in PILOT_STYLES}
    for profile in USER_PROFILES.values():
        if not isinstance(profile, dict):
            continue
        old_skills = profile.get("skills")
        new_skills = migrate_skill_distribution(old_skills)
        if old_skills != new_skills:
            profile["skills"] = new_skills
            changed = True
        defaults = {
            "age": None, "team": "", "photo_url": "", "spins": 0,
            "equipped_style": None, "equipped_style_data": None,
            "skip_roll_gamepass": False, "skip_roll_active": False,
            "ability": None, "ability_collection": [], "ability_spins": 0,
            "pending_ability_roll": None, "skills_locked": False, "pending_roll": None,
        }
        for key, value in defaults.items():
            if key not in profile:
                profile[key] = value.copy() if isinstance(value, (dict, list)) else value
                changed = True
        if profile.get("ability") and profile["ability"] not in profile["ability_collection"]:
            profile["ability_collection"].append(profile["ability"])
            changed = True
        current = styles_by_name.get(str(profile.get("equipped_style") or "").casefold())
        if current and profile.get("equipped_style_data") != current:
            profile["equipped_style_data"] = dict(current)
            changed = True
        if "style_collection" in profile:
            profile.pop("style_collection", None)
            changed = True
        profile["ability_spins"] = max(0, int(profile.get("ability_spins") or 0))
        profile["spins"] = max(0, int(profile.get("spins") or 0))
    if changed:
        try:
            write_profiles_file()
            print("Perfis migrados para estilo único.")
        except OSError as exc:
            print(f"Falha ao salvar migração dos perfis: {exc}")

migrate_existing_profiles()

SHOP_PACKAGES = {
    "1": {"spins": 1, "dreams": "5k sonhos"},
    "5": {"spins": 5, "dreams": "25k sonhos"},
    "10": {"spins": 10, "dreams": "50k sonhos"},
    "25": {"spins": 25, "dreams": "125k sonhos"},
}

async def sync_pilot_role(guild, member, style_name):
    """Synchroniza cargos de piloto; retorna (role, aviso) sem alterar IDs configurados."""
    if guild is None or member is None:
        return None, "Não foi possível sincronizar cargos fora de um servidor."
    mapped_ids = {int(role_id) for role_id in PILOT_ROLE_IDS.values() if role_id}
    target_id = PILOT_ROLE_IDS.get(style_name) if style_name else None
    target_role = guild.get_role(int(target_id)) if target_id else None
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        return target_role, "O bot precisa da permissão Gerenciar cargos."
    if target_role and target_role >= bot_member.top_role:
        return target_role, f"O cargo {target_role.name} está acima ou no mesmo nível do cargo do bot."
    remove_roles = [r for r in member.roles if r.id in mapped_ids and (not target_role or r.id != target_role.id)]
    try:
        if remove_roles:
            await member.remove_roles(*remove_roles, reason="Substituição do estilo de piloto equipado")
        if target_role and target_role not in member.roles:
            await member.add_roles(target_role, reason="Estilo de piloto equipado")
        return target_role, None
    except discord.Forbidden:
        return target_role, "Discord negou a alteração de cargos; confira permissões e hierarquia."
    except discord.HTTPException as exc:
        return target_role, f"Falha ao sincronizar cargos no Discord: {exc}"

async def equip_style_consistently(guild, member, profile, style):
    """Substitui o único estilo ativo do jogador."""
    role, warning = await sync_pilot_role(guild, member, style.get("name"))
    profile["equipped_style"] = style["name"]
    profile["equipped_style_data"] = dict(style)
    profile.pop("style_collection", None)
    save_profiles()
    return role, warning

def gacha_profile(user_id: int):
    is_new_profile = str(user_id) not in USER_PROFILES
    if is_new_profile:
        starter_style = dict(roll_style())
        profile = {
            "name": "", "age": None, "team": "", "photo_url": "",
            "skills": dict(PROFILE_PRESETS["balanced"]["skills"]),
            "spins": 0, "equipped_style": starter_style["name"],
            "equipped_style_data": starter_style,
            "skip_roll_gamepass": False, "skip_roll_active": False,
            "skills_locked": False, "ability": random.choice(list(ABILITY_CATALOG)),
        }
        USER_PROFILES[str(user_id)] = profile
    else:
        profile = USER_PROFILES[str(user_id)]
    profile.setdefault("age", None)
    profile.setdefault("team", "")
    profile.setdefault("photo_url", "")
    profile.setdefault("spins", 0)
    profile.setdefault("equipped_style", None)
    profile.setdefault("skip_roll_gamepass", False)
    profile.setdefault("skip_roll_active", False)
    profile["skills"] = migrate_skill_distribution(profile.get("skills"))
    profile.setdefault("ability", random.choice(list(ABILITY_CATALOG)))
    profile.setdefault("ability_collection", [profile["ability"]] if profile.get("ability") else [])
    profile.setdefault("ability_spins", 0)
    profile.pop("style_collection", None)
    if profile.get("equipped_style") and not profile.get("equipped_style_data"):
        profile["equipped_style_data"] = next(
            (dict(item) for item in PILOT_STYLES if item["name"] == profile["equipped_style"]), None
        )
    if is_new_profile:
        save_profiles()
    return profile

def roll_style():
    rarity = random.choices(
        list(RARITY_DATA.keys()),
        weights=[RARITY_DATA[r]["chance"] for r in RARITY_DATA],
        k=1,
    )[0]
    candidates = [style for style in PILOT_STYLES if style["rarity"] == rarity]
    return random.choice(candidates)

def save_profiles():
    try:
        write_profiles_file()
    except OSError as exc:
        print(f"⚠️ Erro ao salvar perfis: {exc}")
        raise

def profile_for(user_id: int):
    return USER_PROFILES.get(str(user_id))

def driver_display_name(driver: Driver):
    return driver.race_name or driver.user.display_name


def race_for_channel(channel_id: int):
    return races.get(channel_id)


def format_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--.---"
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes}:{remaining:06.3f}"


def tire_weather_multiplier(tire_key: str, rain_level: float) -> float:
    tire = TIRES[tire_key]
    if rain_level <= 0.10:
        climate_factor = tire["dry"]
    elif rain_level <= 0.50:
        climate_factor = tire["damp"]
    else:
        climate_factor = tire["wet"]
    return tire["grip"] * climate_factor


def weather_tire_penalty(tire_key: str, rain_level: float) -> float:
    # Positivo significa perda de tempo; composto adequado pode reduzir a penalidade.
    multiplier = tire_weather_multiplier(tire_key, rain_level)
    return max(-0.15, (1.0 - multiplier) * 1.35)


def lobby_embed(race: Race, title="🏁 F1 Discord Racing — Lobby", description=None):
    circuit = CIRCUITS[race.circuit_name]
    embed = discord.Embed(
        title=title,
        description=description or f"**{race.circuit_name}** • {race.total_laps} voltas\nCircuito com retas e curvas.",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="🌦️ Condições",
        value=f"**Clima:** {race.weather_name}\n**Ambiente:** {race.ambient_temp}°C\n**Pista:** {race.track_temp}°C ({race.surface})",
        inline=True,
    )
    embed.add_field(name="👥 Lobby", value=f"**Pilotos:** {len(race.drivers)}/{MAX_PLAYERS}\n**Mínimo:** {MIN_PLAYERS}", inline=True)
    if race.drivers:
        rows = []
        for pos, driver in enumerate(race.drivers.values(), 1):
            tire_label = TIRES[driver.tire]["label"] if driver.tire else "Não escolhido"
            badge_bits = []
            if driver.team_name:
                badge_bits.append(f"🏢 {driver.team_name}")
            if driver.favorite_tire:
                badge_bits.append(f"⭐ Favorito: {TIRES.get(driver.favorite_tire, {}).get('label', driver.favorite_tire)}")
            badge_line = ("\n└ " + " • ".join(badge_bits)) if badge_bits else ""
            rows.append(f"**P{pos}** {driver.user.mention} (**{driver_display_name(driver)}**) — {driver.lobby_status}\n└ Pneus da corrida: {tire_label} • Pontos: {driver.total_skills}/{SKILL_POINTS}{badge_line}")
        embed.add_field(name="🏎️ Pilotos e posições provisórias", value="\n".join(rows), inline=False)
    else:
        embed.add_field(name="🏎️ Pilotos", value="Ninguém entrou ainda.", inline=False)
    embed.set_footer(text="Distribua 10 pontos (ajustáveis no lobby), escolha pneus e marque Estou pronto.")
    return embed


async def refresh_lobby(race, view):
    if race.message:
        await race.message.edit(embed=lobby_embed(race), view=view)


class SkillSelect(discord.ui.Select):
    def __init__(self, race, user_id, attribute, label, emoji):
        self.race = race
        self.user_id = user_id
        self.attribute = attribute
        options = [discord.SelectOption(label=f"{i} ponto(s)", value=str(i)) for i in range(SKILL_POINTS + 1)]
        super().__init__(placeholder=f"{emoji} {label}: escolha pontos", options=options, min_values=1, max_values=1,
                         row=SKILL_FIELDS.index((attribute, label, emoji)))

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Esse menu pertence a outro piloto.", ephemeral=True)
        race = race_for_channel(interaction.channel_id)
        if not race or race.started or self.user_id not in race.drivers:
            return await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
        driver = race.drivers[self.user_id]
        new_value = int(self.values[0])
        old_value = getattr(driver, self.attribute)
        total = driver.total_skills - old_value + new_value
        if total > SKILL_POINTS:
            return await interaction.response.send_message(f"Você ultrapassaria {SKILL_POINTS} pontos (total {total}).", ephemeral=True)
        setattr(driver, self.attribute, new_value)
        driver.ready = False
        await interaction.response.send_message(f"Atualizado: {driver.skill_summary}\nTotal {driver.total_skills}/{SKILL_POINTS}", ephemeral=True)
        await refresh_lobby(race, LobbyView(race))


class SkillView(discord.ui.View):
    def __init__(self, race, user_id):
        super().__init__(timeout=60)
        self.race = race
        self.user_id = user_id
        self.add_item(discord.ui.Button(label="Distribuir pelo perfil", style=discord.ButtonStyle.primary, disabled=True))


class TireSelect(discord.ui.Select):
    def __init__(self, race, user_id):
        self.race = race
        self.user_id = user_id
        options = [discord.SelectOption(label=v["label"], value=k) for k, v in TIRES.items()]
        super().__init__(placeholder="Escolha seu composto", options=options, min_values=1, max_values=1)

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Esse menu pertence a outro piloto.", ephemeral=True)
        race = race_for_channel(interaction.channel_id)
        if not race or race.started or self.user_id not in race.drivers:
            return await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
        driver = race.drivers[self.user_id]
        driver.tire = self.values[0]
        driver.ready = False
        rain = WEATHER[race.weather_name]["rain"]
        penalty = weather_tire_penalty(driver.tire, rain)
        note = "Composto compatível." if penalty < 0.08 else "⚠️ Composto inadequado: penalidade de aderência/ritmo aplicada."
        await interaction.response.send_message(f"Pneu escolhido: **{TIRES[driver.tire]['label']}**. {note}", ephemeral=True)
        await refresh_lobby(race, LobbyView(race))


class TireView(discord.ui.View):
    def __init__(self, race, user_id):
        super().__init__(timeout=180)
        self.add_item(TireSelect(race, user_id))


class LobbyView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race

    def active(self, interaction):
        current = race_for_channel(interaction.channel_id)
        return current is self.race and not current.started

    @discord.ui.button(label="Entrar na corrida", emoji="🏎️", style=discord.ButtonStyle.success, row=0)
    async def join(self, interaction, button):
        if not self.active(interaction):
            return await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
        async with self.race.lock:
            if interaction.user.id in self.race.drivers:
                return await interaction.response.send_message("Você já está inscrito.", ephemeral=True)
            if self.race.full:
                return await interaction.response.send_message(f"Lobby cheio ({MAX_PLAYERS} pilotos).", ephemeral=True)
            profile = gacha_profile(interaction.user.id)
            saved_skills = profile.get("skills", PROFILE_PRESETS["balanced"]["skills"])
            equipped = profile.get("equipped_style")
            style = profile.get("equipped_style_data") or next((s for s in PILOT_STYLES if s["name"] == equipped), None)
            bonuses = (style or {}).get("skills", {})
            driver = Driver(
                user=interaction.user, race_name=profile.get("name") or interaction.user.display_name,
                tyre_management=int(saved_skills.get("tyre_management", 0)),
                curves=int(saved_skills.get("curves", 0)), speed=int(saved_skills.get("speed", 0)),
                qualifying=int(saved_skills.get("qualifying", 0)), engine=int(saved_skills.get("engine", 0)),
                control=int(saved_skills.get("control", 0)),
                straights=int(saved_skills.get("speed", 0)), braking=int(saved_skills.get("qualifying", 0)),
                acceleration=int(saved_skills.get("engine", 0)), ability=profile.get("ability"),
                style_name=equipped, style_tyre_management=int(bonuses.get("tyre_management",0)),
                style_curves=int(bonuses.get("curves",0)),
                style_straights=int(bonuses.get("straights",0)), style_braking=int(bonuses.get("braking",0)),
                style_acceleration=int(bonuses.get("acceleration",0)), style_control=int(bonuses.get("control",0)),
            )
            self.race.drivers[interaction.user.id] = driver
        await interaction.response.edit_message(embed=lobby_embed(self.race), view=self)

    @discord.ui.button(label="Configurar carro", emoji="⚙️", style=discord.ButtonStyle.primary, row=0)
    async def configure(self, interaction, button):
        if not self.active(interaction) or interaction.user.id not in self.race.drivers:
            return await interaction.response.send_message("Entre no lobby antes.", ephemeral=True)
        modal = ProfileSkillsModal(interaction.user.id, race=self.race)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Escolher pneus", emoji="🛞", style=discord.ButtonStyle.secondary, row=0)
    async def tires(self, interaction, button):
        if not self.active(interaction) or interaction.user.id not in self.race.drivers:
            return await interaction.response.send_message("Entre no lobby antes.", ephemeral=True)
        await interaction.response.send_message(f"Clima: {self.race.weather_name} • Pista {self.race.surface}.", view=TireView(self.race, interaction.user.id), ephemeral=True)

    @discord.ui.button(label="Estou pronto", emoji="✅", style=discord.ButtonStyle.success, row=1)
    async def ready(self, interaction, button):
        if not self.active(interaction) or interaction.user.id not in self.race.drivers:
            return await interaction.response.send_message("Você precisa estar inscrito.", ephemeral=True)
        driver = self.race.drivers[interaction.user.id]
        if not driver.skills_complete:
            return await interaction.response.send_message(f"Você precisa distribuir exatamente {SKILL_POINTS} pontos (atualmente {driver.total_skills}).", ephemeral=True)
        if not driver.tire:
            return await interaction.response.send_message("Escolha os pneus antes.", ephemeral=True)
        driver.ready = not driver.ready
        await interaction.response.send_message(f"Status: {'pronto' if driver.ready else 'configurando'}.", ephemeral=True)
        await refresh_lobby(self.race, self)

    @discord.ui.button(label="Configurar corrida", emoji="🛠️", style=discord.ButtonStyle.primary, row=2)
    async def settings(self, interaction, button):
        if interaction.user.id != self.race.host_id:
            return await interaction.response.send_message("Somente o host pode configurar a corrida.", ephemeral=True)
        if not self.active(interaction):
            return await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
        await interaction.response.send_message("Configurações da corrida (somente host):", view=LobbyConfigView(self.race), ephemeral=True)

    @discord.ui.button(label="Iniciar classificação", emoji="⏱️", style=discord.ButtonStyle.success, row=2)
    async def start_qualifying_button(self, interaction, button):
        if interaction.user.id != self.race.host_id:
            return await interaction.response.send_message("Somente o host pode iniciar a classificação.", ephemeral=True)
        ok, message = await start_qualifying(self.race)
        if not ok:
            return await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
        await interaction.response.send_message("Classificação iniciada/concluída.", ephemeral=True)

    @discord.ui.button(label="Sair do lobby", emoji="🚪", style=discord.ButtonStyle.danger, row=1)
    async def leave(self, interaction, button):
        if not self.active(interaction) or interaction.user.id not in self.race.drivers:
            return await interaction.response.send_message("Você não está no lobby.", ephemeral=True)
        async with self.race.lock:
            self.race.drivers.pop(interaction.user.id, None)
        await interaction.response.edit_message(embed=lobby_embed(self.race), view=self)


def calculate_qualifying_time(driver, race):
    circuit = CIRCUITS[race.circuit_name]
    rain = WEATHER[race.weather_name]["rain"]
    weighted = (
        driver.effective_skill("curves") * circuit["corners"] + driver.effective_skill("straights") * circuit["straights"]
        + driver.effective_skill("acceleration") * circuit["acceleration"]
        + driver.effective_skill("control") * circuit["control"]
        + (driver.qualifying + driver.style_braking) * 0.08
    )
    skill_delta = weighted - 4.0
    tire_delta = (tire_weather_multiplier(driver.tire, rain) - 1.0) * 2.8
    weather_penalty = rain * 1.8
    if driver.ability == "Motorista de Qualificação":
        skill_delta += 0.20
    random_delta = random.uniform(-0.22, 0.22)
    return max(60.0, circuit["base_lap"] - skill_delta * 0.65 + tire_delta + weather_penalty + random_delta)


def qualifying_embed(race):
    sorted_drivers = sorted(race.drivers.values(), key=lambda d: d.qualifying_time or float("inf"))
    lines = []
    for pos, driver in enumerate(sorted_drivers, 1):
        driver.grid_position = pos
        lines.append(f"**P{pos} — {driver_display_name(driver)}** | `{format_time(driver.qualifying_time)}` | {TIRES[driver.tire]['label']}")
    embed = discord.Embed(
        title="⏱️ Classificação — Grid de largada",
        description=f"**Circuito:** {race.circuit_name}\n**Clima:** {race.weather_name} • **Pista:** {race.surface}\n\n" + "\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="A classificação define a ordem inicial da corrida.")
    return embed


async def start_qualifying(race):
    async with race.lock:
        if race.started:
            return False, "A classificação já foi realizada."
        if len(race.drivers) < MIN_PLAYERS:
            return False, f"São necessários pelo menos {MIN_PLAYERS} pilotos."
        if not all(d.ready for d in race.drivers.values()):
            return False, "Todos os pilotos devem estar prontos."
        race.started = True
        for driver in race.drivers.values():
            driver.qualifying_time = calculate_qualifying_time(driver, race)
        race.qualifying_done = True
    if race.message:
        await race.message.edit(embed=qualifying_embed(race), view=QualifyingView(race))
    return True, "Classificação concluída."


class ClosedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for child in self.children:
            child.disabled = True


class RaceDecisionView(discord.ui.View):
    """Ações contextuais: traçado em curvas, DRS/Boost/Box em retas."""
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race
        if race.current_segment_type == "curva":
            self.add_action("Por dentro", "🟠", "normal", line="inside", row=0)
            self.add_action("Por fora", "🔵", "normal", line="outside", row=0)
            self.add_action("Defender a linha", "🛡️", "defensive", line="defend", row=1)
            self.add_action("Traçado seguro", "🟢", "safe", line="safe", row=1)
        else:
            self.add_action("Manter ritmo", "⚖️", "normal", row=0)
            self.add_action("Defender posição", "🛡️", "defensive", row=0)
            if self.any_driver_in_drs_window():
                self.add_action("DRS / Ultrapassar", "↗️", "normal", attack=True, row=1)
            self.add_action("Boost Mode", "⚡", "normal", boost=True, row=1)
            for row, tires in ((2, (("Box: Soft", "Soft", "🔴"), ("Box: Medium", "Medium", "🟡"), ("Box: Hard", "Hard", "⚪"))),
                               (3, (("Box: Inter", "Intermediate", "🟢"), ("Box: Wet", "Wet", "🔵")))):
                for label, tire, emoji in tires:
                    self.add_action(label, emoji, "normal", pit=True, pit_tire=tire, row=row)

    def any_driver_in_drs_window(self):
        active = sorted([d for d in self.race.drivers.values() if not d.finished and not d.retired], key=lambda d: d.total_time)
        return any(active[i].total_time - active[i-1].total_time <= OVERTAKE_DETECTION_SECONDS for i in range(1, len(active)))

    def add_action(self, label, emoji, mode, attack=False, boost=False, line=None, pit=False, pit_tire=None, row=0):
        button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary if attack or pit else discord.ButtonStyle.secondary, row=row)
        async def callback(interaction):
            await self.record_choice(interaction, mode, attack=attack, boost=boost, line=line, pit=pit, pit_tire=pit_tire)
        button.callback = callback
        self.add_item(button)

    async def record_choice(self, interaction, mode, attack=False, boost=False, line=None, pit=False, pit_tire=None):
        race = race_for_channel(interaction.channel_id)
        driver = race.drivers.get(interaction.user.id) if race else None
        if race is not self.race or not race.race_started or driver is None or driver.finished or driver.retired:
            return await interaction.response.send_message("Você não é um piloto ativo nesta corrida.", ephemeral=True)
        active = sorted([d for d in race.drivers.values() if not d.finished and not d.retired], key=lambda d: d.total_time)
        index = active.index(driver) if driver in active else 0
        gap = driver.total_time - active[index-1].total_time if index > 0 else None
        if attack and (race.current_segment_type != "reta" or gap is None or gap > OVERTAKE_DETECTION_SECONDS):
            return await interaction.response.send_message("DRS indisponível: precisa estar até 1,0s do carro à frente em uma reta.", ephemeral=True)
        if (boost or pit or attack) and race.current_segment_type != "reta":
            return await interaction.response.send_message("Essa ação só está disponível em uma reta.", ephemeral=True)
        if pit and driver.last_pit_lap == race.current_lap:
            return await interaction.response.send_message("Você já fez um pit stop nesta volta.", ephemeral=True)
        async with race.decision_lock:
            if driver.chosen_action is not None:
                return await interaction.response.send_message("Você já confirmou sua decisão neste trecho.", ephemeral=True)
            action: DecisionAction = {"mode": mode, "attack": attack, "boost": boost}
            if line: action["line"] = line
            if pit:
                action["pit"] = True
                action["pit_tire"] = pit_tire
            driver.chosen_action = action
            active_now = [d for d in race.drivers.values() if not d.finished and not d.retired]
            await interaction.response.edit_message(embed=decision_status_embed(race, active_now, race.current_decision_label, []), view=self)


def segment_base_time(segment, circuit):
    segments = circuit.get("segments", ["reta", "curva"])
    total_weight = sum(0.82 if item == "reta" else 1.18 for item in segments) or 1
    weight = 0.82 if segment == "reta" else 1.18
    return circuit["base_lap"] * weight / total_weight


def skill_segment_bonus(driver, segment):
    if segment == "reta":
        # Reta e aceleração predominam; reta impacta a velocidade média.
        return driver.effective_skill("straights") * 0.055 + driver.effective_skill("acceleration") * 0.035
    # Curva, frenagem e controle fazem diferença na zona técnica.
    return driver.effective_skill("curves") * 0.065 + driver.effective_skill("control") * 0.045


def calculate_segment_time(driver, race, segment, action, opponent_gap=None, opponent=None):
    circuit = CIRCUITS[race.circuit_name]
    rain = WEATHER[race.weather_name]["rain"]
    mode = DRIVING_MODES[action["mode"]]
    base = segment_base_time(segment, circuit)

    skill_bonus = skill_segment_bonus(driver, segment)
    pit_penalty = 0.0
    event = ""
    if action.get("pit"):
        chosen_tire = action.get("pit_tire") or ("Wet" if rain > 0.50 else "Intermediate" if rain > 0.10 else "Medium")
        if chosen_tire not in TIRES:
            chosen_tire = "Medium"
        old_tire = driver.tire
        driver.tire = chosen_tire
        driver.tire_wear = 0.0
        driver.car_damage = max(0.0, driver.car_damage - 12.0)
        driver.pit_stops += 1
        driver.last_pit_lap = race.current_lap
        pit_penalty = 18.0
        event = f"🛠️ PIT STOP: {driver_display_name(driver)} trocou {TIRES[old_tire]['label'] if old_tire in TIRES else 'pneus'} por {TIRES[chosen_tire]['label']} e reparou parte do dano."
    if driver.ability == "Largada Explosiva" and race.current_lap == 1:
        skill_bonus += base * 0.006
    if driver.ability == "Última Volta" and race.current_lap == race.total_laps:
        skill_bonus += base * 0.006
    tire_mult = tire_weather_multiplier(driver.tire, rain)
    tire_condition = max(0.60, 1.0 - driver.tire_wear / 160.0)
    tire_loss = max(0.0, 1.0 - tire_mult) * (base * 0.12)
    weather_loss = rain * (base * 0.08)
    if driver.ability == "Rei da Chuva":
        weather_loss *= 0.90
    mode_adjustment = mode["pace"]
    line_risk = 0.0
    if segment == "curva":
        line = action.get("line")
        if line == "inside":
            mode_adjustment -= 0.035
            line_risk += 0.012
        elif line == "outside":
            mode_adjustment -= 0.018
        elif line == "defend":
            mode_adjustment += 0.012
            line_risk -= 0.012
        elif line == "safe":
            mode_adjustment += 0.025
            line_risk -= 0.020

    # Energia de jogo substitui um uso simplificado da gestão elétrica:
    # Boost consome energia e dá bônus, Overtake Mode consome energia quando elegível.
    energy_adjustment = 0.0

    if action["boost"]:
        if driver.energy >= 15:
            driver.energy -= 15
            energy_adjustment -= base * 0.055
            event = "⚡ Boost Mode ativado (-15 energia)."
        else:
            energy_adjustment += base * 0.025
            event = "🔋 Energia insuficiente para Boost Mode."

    if action["attack"]:
        if opponent is None or opponent_gap is None or opponent_gap > OVERTAKE_DETECTION_SECONDS:
            mode_adjustment += 0.12
            event = "⛔ Overtake Mode indisponível: carro à frente fora da janela de 1,0s."
        elif driver.energy >= 12:
            driver.energy -= 12
            energy_adjustment -= base * 0.035
            event = "↗️ Overtake Mode ativado (-12 energia), tentativa de ultrapassagem."
        else:
            mode_adjustment += 0.10
            event = "🔋 Energia insuficiente para Overtake Mode."

    # Modo agressivo/defensivo/seguro ajusta risco, ritmo e disputa.
    # Dano persistente reduz o desempenho; estrutura pronta para pit stop/reparos futuros.
    damage_penalty = driver.car_damage * 0.0018
    mode_risk = mode["risk"]
    random_error = random.uniform(-0.12, 0.12)  # moderado
    time = base - skill_bonus - (tire_condition * 0.12) + tire_loss + weather_loss + mode_adjustment + energy_adjustment + random_error + base * damage_penalty + pit_penalty

    curve_intensity = 1.0 if segment == "curva" else 0.35
    risk = 0.025 + mode["risk"] + line_risk + rain * (0.12 if segment == "curva" else 0.06)
    risk += (driver.tire_wear / 100) * 0.20 + (driver.car_damage / 100) * 0.12
    risk += curve_intensity * max(0, 5 - driver.effective_skill("curves")) * 0.012
    risk += curve_intensity * max(0, 5 - driver.effective_skill("control")) * 0.014
    if driver.ability == "Mãos de Cirurgião":
        risk -= 0.008
    if driver.ability == "Sangue Frio" and action["mode"] == "aggressive":
        risk -= 0.006
    risk += max(0, -mode["pace"]) * 0.30  # agressividade/ação rápida
    risk = max(0.008, min(0.52, risk))

    if random.random() < risk:
        severity = random.random()
        if severity < 0.68:
            lost = base * random.uniform(0.05, 0.14)
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(3, 9))
            event = (event + " " if event else "") + f"💥 Derrapagem/contato: +{driver.car_damage:.0f}% dano, perdeu tempo."
        elif severity < 0.96:
            lost = base * random.uniform(0.14, 0.30)
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(12, 24))
            event = (event + " " if event else "") + f"🚧 Acidente moderado: dano do carro {driver.car_damage:.0f}%."
        else:
            lost = base * random.uniform(0.30, 0.55)
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(30, 45))
            event = (event + " " if event else "") + f"🛑 Acidente grave: dano do carro {driver.car_damage:.0f}%."
        time += lost
        driver.tire_wear = min(100.0, driver.tire_wear + 2.0)
        driver.events.append(event)
    else:
        driver.events.append("—")

    # Desgaste progride em cada segmento e afeta ritmo nos segmentos futuros.
    wear_increment = TIRES[driver.tire]["wear"] * (0.75 if segment == "reta" else 1.15)
    wear_increment *= max(0.75, 1.0 - driver.effective_skill("tyre_management") * 0.025)
    if driver.ability == "Mestre dos Pneus":
        wear_increment *= 0.90
    if driver.ability == "Pit Stop Perfeito" and race.current_lap == 1 and segment == "reta":
        wear_increment *= 0.85
    if action["mode"] == "aggressive":
        wear_increment *= 1.20
    if action["mode"] == "safe":
        wear_increment *= 0.85
    if rain > 0.50 and driver.tire in ("Intermediate", "Wet"):
        wear_increment *= 0.85
    driver.tire_wear = min(100.0, driver.tire_wear + wear_increment)
    # Estouro progressivo: probabilidade insignificante com pneus frescos, maior no limite.
    if driver.tire_wear >= 72:
        burst_chance = min(0.20, ((driver.tire_wear - 72) / 28) ** 2 * 0.20)
        if random.random() < burst_chance:
            driver.tire_wear = 100.0
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(8, 22))
            time += base * random.uniform(0.20, 0.42)
            event = (event + " " if event else "") + f"🛞 ESTOURO DE PNEU! Dano {driver.car_damage:.0f}% e grande perda de tempo."
            driver.events.append(event)
    if driver.car_damage >= 90:
        driver.retired = True
        event = (event + " " if event else "") + "⛔ Abandono: danos críticos no carro."

    # Recuperação pequena de energia em ritmo normal/seguro; manter tática como decisão.
    if not action["boost"] and not action["attack"]:
        recovery = 2.0 if action["mode"] in ("normal", "safe") else 0.5
        if driver.ability == "Recuperação Rápida":
            recovery += 0.5
        driver.energy = min(100.0, driver.energy + recovery)

    return max(1.0, time), event


def current_order(race):
    return sorted(race.drivers.values(), key=lambda d: (d.retired, d.total_time))


def standings_embed(race, lap, segment_label, events):
    order = current_order(race)
    lines = []
    for pos, driver in enumerate(order, 1):
        if pos == 1:
            gap = "Líder"
        else:
            gap = f"+{driver.total_time - order[pos-2].total_time:.3f}s para P{pos-1}"
        lines.append(
            f"**P{pos} — {driver_display_name(driver)}** | Volta {lap}/{race.total_laps}\n"
            f"└ Tempo: `{format_time(driver.total_time)}` • {gap}\n"
            f"└ {TIRES[driver.tire]['label']} • desgaste {driver.tire_wear:.0f}% • energia {driver.energy:.0f}% • dano {driver.car_damage:.0f}%" + (" • ⛔ ABANDONOU" if driver.retired else "")
        )
    embed = discord.Embed(
        title=f"📊 Classificação — Volta {lap}/{race.total_laps} • {segment_label}",
        description="\n".join(lines),
        color=discord.Color.blue(),
    )
    embed.add_field(name="🌦️ Condições da pista", value=f"**{race.weather_name}** • {race.surface} • Ambiente {race.ambient_temp}°C • Pista {race.track_temp}°C", inline=False)
    if events:
        event_text = "\n".join(events[-12:])
        if len(event_text) > 1000:
            event_text = event_text[:997] + "..."
        embed.add_field(name="📺 Transmissão — acontecimentos da volta", value=event_text, inline=False)
    return embed




class QualifyingView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race

    @discord.ui.button(label="Iniciar corrida", emoji="🚦", style=discord.ButtonStyle.success)
    async def begin_race(self, interaction, button):
        race = race_for_channel(interaction.channel_id)
        if race is not self.race or interaction.user.id != race.host_id:
            return await interaction.response.send_message("Somente o host desta corrida pode iniciar.", ephemeral=True)
        if not race.qualifying_done or race.race_started:
            return await interaction.response.send_message("A corrida ainda não está pronta para começar.", ephemeral=True)
        race.race_task = asyncio.create_task(run_race(race))
        await interaction.response.edit_message(content="🚦 Corrida iniciada! O painel será atualizado a cada trecho.", view=ClosedView())


class LobbyConfigView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=120)
        self.race = race
        self.add_item(LapsSelect(race))
        self.add_item(CircuitSelect(race))
        self.add_item(WeatherSelect(race))
        self.add_item(DecisionTimeSelect(race))


class LobbyConfigSelect(discord.ui.Select):
    def __init__(self, race, options, placeholder):
        self.race = race
        super().__init__(options=options, placeholder=placeholder, min_values=1, max_values=1)

    async def host_check(self, interaction):
        if race_for_channel(interaction.channel_id) is not self.race:
            await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
            return False
        if interaction.user.id != self.race.host_id or self.race.started:
            await interaction.response.send_message("Somente o host pode configurar antes da classificação.", ephemeral=True)
            return False
        return True


class LapsSelect(LobbyConfigSelect):
    def __init__(self, race):
        options = [discord.SelectOption(label=f"{n} voltas", value=str(n), default=race.total_laps == n) for n in (3, 5, 10, 15, 20)]
        super().__init__(race, options, "Número de voltas")

    async def callback(self, interaction):
        if not await self.host_check(interaction): return
        self.race.total_laps = int(self.values[0])
        await interaction.response.send_message(f"Corrida definida para {self.race.total_laps} voltas.", ephemeral=True)
        await refresh_lobby(self.race, LobbyView(self.race))


class CircuitSelect(LobbyConfigSelect):
    def __init__(self, race):
        options = [discord.SelectOption(label=name, value=name, default=race.circuit_name == name) for name in CIRCUITS]
        super().__init__(race, options, "Circuito")

    async def callback(self, interaction):
        if not await self.host_check(interaction): return
        self.race.circuit_name = self.values[0]
        await interaction.response.send_message(f"Circuito escolhido: {self.race.circuit_name}.", ephemeral=True)
        await refresh_lobby(self.race, LobbyView(self.race))


class WeatherSelect(LobbyConfigSelect):
    def __init__(self, race):
        options = [discord.SelectOption(label=name, value=name, default=race.weather_name == name) for name in WEATHER]
        super().__init__(race, options, "Clima")

    async def callback(self, interaction):
        if not await self.host_check(interaction): return
        self.race.weather_name = self.values[0]
        conditions = WEATHER[self.race.weather_name]
        self.race.ambient_temp = random.randint(*conditions["ambient"])
        self.race.track_temp = random.randint(*conditions["track"])
        self.race.surface = conditions["surface"]
        for driver in self.race.drivers.values(): driver.ready = False
        await interaction.response.send_message(f"Clima: {self.race.weather_name}. Todos precisam confirmar prontidão novamente.", ephemeral=True)
        await refresh_lobby(self.race, LobbyView(self.race))


class DecisionTimeSelect(LobbyConfigSelect):
    def __init__(self, race):
        options = [discord.SelectOption(label=f"{n} segundos", value=str(n), default=race.decision_seconds == n) for n in (20, 30, 45, 60, 90)]
        super().__init__(race, options, "Tempo para decisões")

    async def callback(self, interaction):
        if not await self.host_check(interaction): return
        self.race.decision_seconds = int(self.values[0])
        await interaction.response.send_message(f"Tempo de decisão: {self.race.decision_seconds}s.", ephemeral=True)


def decision_status_embed(race, active, segment_title, events):
    embed = standings_embed(race, race.current_lap, segment_title, events)
    statuses = [f"{'✅ Pronto' if d.chosen_action is not None else '⏳ Aguardando'} — **{driver_display_name(d)}**" for d in active]
    embed.add_field(name="🎮 Status das decisões", value="\n".join(statuses) or "Nenhum piloto ativo", inline=False)
    embed.set_footer(text=f"Escolhas ocultas até todos confirmarem • prazo: {race.decision_seconds}s")
    return embed


async def update_race_panel(race, active, segment_title, events, show_decision=False):
    if race.message:
        view = RaceDecisionView(race) if show_decision else ClosedView()
        embed = decision_status_embed(race, active, segment_title, events)
        # Reenvia o painel atualizado para o fim do canal, mantendo os botões funcionais.
        old_message = race.message
        new_message = await race.channel.send(embed=embed, view=view)
        race.message = new_message
        try:
            await old_message.delete()
        except discord.HTTPException:
            pass


def reveal_decisions_embed(race, active, segment_title, events):
    embed = standings_embed(race, race.current_lap, segment_title, events)
    lines = []
    for driver in active:
        action: DecisionAction = driver.chosen_action or {"mode": "safe", "attack": False, "boost": False}
        parts = [DRIVING_MODES[action["mode"]]["label"]]
        if action.get("attack"):
            parts.append("Overtake Mode")
        if action.get("boost"):
            parts.append("Boost Mode")
        suffix = " (automático: Seguro)" if driver.chosen_action is None else ""
        lines.append(f"**{driver_display_name(driver)}:** {' + '.join(parts)}{suffix}")
    embed.add_field(name="🔓 Decisões reveladas", value="\n".join(lines) or "—", inline=False)
    return embed


EVENT_ASSET_DIR = Path(__file__).parent / "assets" / "eventos"
EVENT_LINKS_FILE = EVENT_ASSET_DIR / "links.json"
EVENT_IMAGE_RULES = {
    "ultrapassagem": ("ultrapassagem", "↗️"),
    "acidente": ("colisao", "💥"),
    "derrapagem": ("rodada", "🌀"),
    "ESTOURO DE PNEU": ("pneu_estourado", "🛞"),
    "Abandono": ("quebra_motor", "⛔"),
    "Safety Car": ("safety_car", "🚨"),
    "bandeira vermelha": ("bandeira_vermelha", "🟥"),
    "volta mais rápida": ("volta_rapida", "⏱️"),
    "PIT STOP": ("pitstop", "🛠️"),
    "mudança de clima": ("clima", "🌦️"),
}

def event_image_links():
    try:
        data = json.loads(EVENT_LINKS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

async def publish_important_event(race, message):
    lower = message.lower()
    for keyword, (event_folder, emoji) in EVENT_IMAGE_RULES.items():
        if keyword.lower() not in lower:
            continue
        folder = EVENT_ASSET_DIR / event_folder
        local_images = []
        if folder.exists():
            local_images = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        links = event_image_links().get(event_folder, [])
        if isinstance(links, str):
            links = [links]
        links = [url for url in links if isinstance(url, str) and url.startswith(("https://", "http://"))]
        try:
            embed = discord.Embed(description=message, color=discord.Color.orange())
            if local_images:
                asset = random.choice(local_images)
                file = discord.File(asset, filename=asset.name)
                embed.set_image(url=f"attachment://{asset.name}")
                await race.channel.send(content=emoji, embed=embed, file=file)
            elif links:
                embed.set_image(url=random.choice(links))
                await race.channel.send(content=emoji, embed=embed)
            else:
                await race.channel.send(content=f"{emoji} {message}")
        except discord.HTTPException:
            pass
        return

async def run_race(race):
    race.race_started = True
    grid = sorted(race.drivers.values(), key=lambda d: d.grid_position or 99)
    for rank, driver in enumerate(grid):
        driver.total_time = rank * 0.25
        driver.distance = float(rank)
    circuit = CIRCUITS[race.circuit_name]
    segments = circuit.get("segments") or ["reta", "curva"]
    for lap in range(1, race.total_laps + 1):
        if race.early_finish:
            break
        race.current_lap = lap
        lap_start_times = {d.user.id: d.total_time for d in race.drivers.values()}
        lap_events = []
        if lap > 1 and random.random() < 0.12:
            previous_weather = race.weather_name
            race.weather_name = random.choice([name for name in WEATHER if name != previous_weather])
            conditions = WEATHER[race.weather_name]
            race.ambient_temp = random.randint(*conditions["ambient"])
            race.track_temp = random.randint(*conditions["track"])
            race.surface = conditions["surface"]
            weather_event = f"🌦️ Mudança de clima: {previous_weather} -> {race.weather_name}. Pista {race.surface.lower()}."
            lap_events.append(weather_event)
            await publish_important_event(race, weather_event)
        for segment_index, segment in enumerate(segments, 1):
            race.current_segment = segment_index
            race.current_segment_type = segment
            active = [d for d in race.drivers.values() if not d.finished and not d.retired]
            if len(active) <= 1:
                if active:
                    active[0].finished = True
                    race.early_finish = True
                    winner_event = f"🏁 Corrida encerrada antecipadamente: {driver_display_name(active[0])} é o vencedor, único piloto restante na pista!"
                    lap_events.append(winner_event)
                    await publish_important_event(race, winner_event)
                break
            for driver in active:
                driver.chosen_action = None
            segment_title = f"{segment.upper()} {segment_index}/{len(segments)}"
            race.current_decision_label = f"Volta {lap}/{race.total_laps} • {segment_title}"
            await update_race_panel(race, active, segment_title, lap_events, show_decision=True)
            deadline = asyncio.get_running_loop().time() + (race.decision_seconds or 45)
            while any(driver.chosen_action is None for driver in active) and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(1)
            if race.message:
                await race.message.edit(embed=reveal_decisions_embed(race, active, segment_title, lap_events), view=ClosedView())
            pre_order = sorted(active, key=lambda d: d.total_time)
            gaps = {driver.user.id: (driver.total_time - pre_order[index-1].total_time if index else None)
                    for index, driver in enumerate(pre_order)}
            for driver in active:
                action: DecisionAction = driver.chosen_action or {"mode": "safe", "attack": False, "boost": False}
                index = pre_order.index(driver)
                opponent = pre_order[index-1] if index else None
                segment_time, event = calculate_segment_time(driver, race, segment, action, gaps[driver.user.id], opponent)
                driver.total_time += segment_time
                driver.distance += 1.0
                if event:
                    event_message = f"{driver_display_name(driver)}: {event}"
                    lap_events.append(event_message)
                    if any(word in event_message.lower() for word in ("pit stop", "acidente", "derrapagem", "estouro de pneu", "abandono")):
                        await publish_important_event(race, event_message)
            updated = sorted([d for d in active if not d.retired], key=lambda d: d.total_time)
            for index in range(1, len(updated)):
                driver, ahead = updated[index], updated[index-1]
                action = driver.chosen_action or {}
                prior_gap = gaps.get(driver.user.id)
                if action.get("attack") and prior_gap is not None and prior_gap <= OVERTAKE_DETECTION_SECONDS:
                    chance = 0.22 + driver.effective_skill("straights") * 0.025 + driver.effective_skill("acceleration") * 0.018 + driver.effective_skill("control") * 0.008
                    if driver.ability in ("Ultrapassador Nato", "Especialista em DRS"):
                        chance += 0.035
                    chance -= ahead.control * 0.012
                    if ahead.ability == "Defensor Nato":
                        chance -= 0.035
                    chance = max(0.08, min(0.68, chance))
                    if random.random() < chance and driver.total_time > ahead.total_time:
                        driver.total_time -= min(0.35, driver.total_time - ahead.total_time + 0.02)
                        overtake_event = f"↗️ {driver_display_name(driver)} completou uma ultrapassagem!"
                        lap_events.append(overtake_event)
                        await publish_important_event(race, overtake_event)
                    else:
                        lap_events.append(f"🚥 {driver_display_name(driver)} tentou ultrapassar, mas não conseguiu.")
            incident = any("acidente" in event.lower() or "abandono" in event.lower() for event in lap_events)
            still_running = [d for d in race.drivers.values() if not d.retired]
            if incident and len(still_running) > 1 and race.safety_car_laps == 0 and random.random() < 0.55:
                race.safety_car_laps = 1
                safety_event = "🚨 SAFETY CAR NA PISTA! Pelotão neutralizado; as diferenças foram reduzidas."
                lap_events.append(safety_event)
                await publish_important_event(race, safety_event)
            if race.safety_car_laps > 0 and len(still_running) > 1:
                ordered = sorted(still_running, key=lambda d: d.total_time)
                leader_time = ordered[0].total_time
                for position, driver in enumerate(ordered):
                    driver.total_time = leader_time + position * 0.45
            if race.message:
                await race.message.edit(embed=standings_embed(race, lap, segment_title, lap_events), view=ClosedView())
            still_active = [d for d in race.drivers.values() if not d.finished and not d.retired]
            if len(still_active) == 1:
                still_active[0].finished = True
                race.early_finish = True
                winner_event = f"🏁 Corrida encerrada antecipadamente: {driver_display_name(still_active[0])} é o vencedor, único piloto restante na pista!"
                lap_events.append(winner_event)
                await publish_important_event(race, winner_event)
                if race.message:
                    await race.message.edit(embed=standings_embed(race, lap, "FIM ANTECIPADO", lap_events), view=ClosedView())
                break
        for driver in race.drivers.values():
            if not driver.finished and not driver.retired:
                driver.last_lap_time = driver.total_time - lap_start_times.get(driver.user.id, driver.total_time)
                if driver.last_lap_time > 0 and (driver.best_lap_time is None or driver.last_lap_time < driver.best_lap_time):
                    driver.best_lap_time = driver.last_lap_time
        if race.safety_car_laps > 0:
            race.safety_car_laps -= 1
        await asyncio.sleep(0.5)
    final_order = current_order(race)
    for driver in final_order:
        if not driver.retired:
            driver.finished = True
    fastest = min((d for d in final_order if d.best_lap_time is not None and not d.retired), key=lambda d: d.best_lap_time, default=None)
    if fastest:
        await publish_important_event(race, f"⏱️ Volta mais rápida: {driver_display_name(fastest)} — {format_time(fastest.best_lap_time)}")
    await register_championship_result(race, final_order, fastest)
    podium = "\\n".join(
        f"**P{position} — {driver_display_name(driver)}** | Tempo: `{format_time(driver.total_time)}` | "
        f"{TIRES[driver.tire]['label']} • {driver.pit_stops} pit stop(s) • desgaste {driver.tire_wear:.0f}%"
        + (" • ⛔ Abandonou" if driver.retired else "")
        for position, driver in enumerate(final_order, 1)
    )
    title = "🏁 VITÓRIA ANTECIPADA" if race.early_finish else "🏆 FIM DE CORRIDA — RESULTADO FINAL"
    embed = discord.Embed(title=title, description=podium or "Corrida encerrada sem pilotos classificados.", color=discord.Color.gold())
    embed.set_footer(text=f"{race.circuit_name} • {race.current_lap}/{race.total_laps} voltas • corrida concluída")
    if race.message:
        await race.message.edit(embed=embed, view=ClosedView())
    else:
        await race.channel.send(embed=embed)
    races.pop(race.channel_id, None)




class ProfileNameModal(discord.ui.Modal, title="Configurar perfil de piloto"):
    pilot_name=discord.ui.TextInput(label="Nome exibido",max_length=32,required=True)
    age=discord.ui.TextInput(label="Idade",placeholder="Ex.: 22",max_length=3,required=False)
    team_name=discord.ui.TextInput(label="Equipe",max_length=32,required=False)
    photo_url=discord.ui.TextInput(label="URL da foto do piloto",placeholder="https://...",max_length=300,required=False)
    def __init__(self,owner_id,source_message_id=None): super().__init__(); self.owner_id=owner_id; self.source_message_id=source_message_id
    async def on_submit(self,interaction):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse formulário não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id); profile["name"]=str(self.pilot_name.value).strip() or interaction.user.display_name
        try: profile["age"]=int(self.age.value) if str(self.age.value).strip() else None
        except ValueError: return await interaction.response.send_message("Idade deve ser número inteiro.",ephemeral=True)
        profile["team"]=str(self.team_name.value).strip(); url=str(self.photo_url.value).strip()
        if url and not (url.startswith("https://") or url.startswith("http://")): return await interaction.response.send_message("A foto deve ser uma URL http(s).",ephemeral=True)
        profile["photo_url"]=url; save_profiles()
        await interaction.response.send_message("🛠️ Perfil personalizado salvo!",ephemeral=True)
        await refresh_profile_message(interaction, self.source_message_id, profile)

class InventoryView(discord.ui.View):
    def __init__(self,owner_id): super().__init__(timeout=180); self.owner_id=owner_id
    @discord.ui.button(label="Equipar estilo",emoji="🏎️",style=discord.ButtonStyle.primary)
    async def equip(self,interaction,button):
        if interaction.user.id!=self.owner_id:
            return await interaction.response.send_message("Esse inventário não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id)
        style=profile.get("equipped_style_data")
        if not style:
            return await interaction.response.send_message("Você ainda não possui estilo equipado.",ephemeral=True)
        await interaction.response.send_message(
            f"Seu único estilo ativo é **{style['name']}** ({style['rarity']}). "
            "Ao aceitar outro estilo, ele substituirá este.",
            ephemeral=True,
        )

    @discord.ui.button(label="Ativar Pular Giro", emoji="⏭️", style=discord.ButtonStyle.success, row=1)
    async def activate_gamepass(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse inventário não é seu.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        if not profile.get("skip_roll_gamepass"):
            return await interaction.response.send_message("Você não possui a Gamepass Pular Giro. Fale com o administrador após o pagamento externo.", ephemeral=True)
        profile["skip_roll_active"] = True
        save_profiles()
        await interaction.response.send_message("⏭️ Gamepass Pular Giro ativada no seu perfil.", ephemeral=True)

    @discord.ui.button(label="Desativar Pular Giro", emoji="⏸️", style=discord.ButtonStyle.secondary, row=1)
    async def deactivate_gamepass(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse inventário não é seu.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        profile["skip_roll_active"] = False
        save_profiles()
        await interaction.response.send_message("⏸️ Gamepass Pular Giro desativada no seu perfil.", ephemeral=True)

class ProfileSkillsModal(discord.ui.Modal, title="Distribuir 10 pontos pessoais"):
    distribution = discord.ui.TextInput(label="Pontos na ordem indicada", placeholder="1, 2, 2, 1, 2, 2", max_length=30, required=True)
    def __init__(self, owner_id, race=None):
        super().__init__(); self.owner_id = owner_id; self.source_message_id = None; self.race = race
        profile = gacha_profile(owner_id)
        self.distribution.default = ", ".join(str(profile["skills"].get(key, 0)) for key, _, _ in SKILL_FIELDS)
    async def on_submit(self, interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse formulário não é seu.", ephemeral=True)
        try:
            values = [int(part.strip()) for part in self.distribution.value.split(",")]
            if len(values) != 6: raise ValueError
            skills = {field[0]: value for field, value in zip(SKILL_FIELDS, values)}
        except ValueError:
            return await interaction.response.send_message("Informe seis números inteiros separados por vírgula, na ordem exibida no perfil.", ephemeral=True)
        if any(value < 0 or value > 10 for value in skills.values()) or sum(skills.values()) != SKILL_POINTS:
            return await interaction.response.send_message(f"Os seis atributos devem ser inteiros entre 0 e 10 e somar {SKILL_POINTS}.", ephemeral=True)
        profile = gacha_profile(self.owner_id); profile["skills"] = skills; profile["skills_locked"] = True; save_profiles()
        if self.race and self.owner_id in self.race.drivers and not self.race.started:
            driver = self.race.drivers[self.owner_id]
            for key, value in skills.items():
                setattr(driver, key, value)
            driver.straights = skills["speed"]
            driver.braking = skills["qualifying"]
            driver.acceleration = skills["engine"]
            driver.ready = False
        await interaction.response.send_message("✅ Distribuição salva. Você pode ajustá-la novamente enquanto o lobby estiver aberto.", ephemeral=True)
        await refresh_profile_message(interaction, self.source_message_id, profile)

class ProfileView(discord.ui.View):
    def __init__(self,owner_id): super().__init__(timeout=180);self.owner_id=owner_id
    @discord.ui.button(label="Histórico de corridas", emoji="📜", style=discord.ButtonStyle.success, row=1)
    async def history(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse botão não é seu.", ephemeral=True)
        guild_id = interaction.guild.id if interaction.guild else 0
        entries = []
        for season in CHAMPIONSHIP.get("seasons", {}).values():
            if str(season.get("guild_id")) != str(guild_id):
                continue
            for race_data in season.get("races", []):
                result = next((item for item in race_data.get("results", []) if item.get("user_id") == str(self.owner_id)), None)
                if result:
                    entries.append((race_data.get("date", ""), race_data, result, season.get("name", "Temporada")))
        entries.sort(key=lambda item: item[0], reverse=True)
        if not entries:
            return await interaction.response.send_message("Você ainda não possui corridas registradas no campeonato.", ephemeral=True)
        lines = []
        for _, race_data, result, season_name in entries[:10]:
            status = " • ⛔ Abandono" if result.get("retired") else ""
            fastest = " • 🟣 Volta mais rápida" if result.get("fastest_lap") else ""
            lines.append(f"**P{result['position']} — {race_data.get('circuit', 'Circuito')}**{status}{fastest}\\n_{season_name} • {race_data.get('date', 'Data não registrada')[:10]}_")
        embed = discord.Embed(title="📜 Histórico de corridas", description="\\n\\n".join(lines), color=discord.Color.gold())
        embed.set_footer(text="Exibindo as 10 corridas mais recentes.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="Configurar",emoji="⚙️",style=discord.ButtonStyle.primary,row=0)
    async def configure(self,interaction,button):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse botão não é seu.",ephemeral=True)
        modal=ProfileNameModal(self.owner_id, interaction.message.id); await interaction.response.send_modal(modal)
    @discord.ui.button(label="Distribuir pontos", emoji="📊", style=discord.ButtonStyle.secondary, row=0)
    async def distribute(self, interaction, button):
        if interaction.user.id != self.owner_id: return await interaction.response.send_message("Esse botão não é seu.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        modal=ProfileSkillsModal(self.owner_id); modal.source_message_id=interaction.message.id; await interaction.response.send_modal(modal)
    @discord.ui.button(label="Inventário",emoji="🎒",style=discord.ButtonStyle.secondary,row=0)
    async def inventory(self,interaction,button):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse botão não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id); equipped=profile.get("equipped_style") or "Nenhum"
        gp="Sim" if profile.get("skip_roll_gamepass") else "Não"
        active="Ativa" if profile.get("skip_roll_gamepass") and profile.get("skip_roll_active") else "Desativada"
        lines=[f"**Giros de estilo:** {profile['spins']}",f"**Giros de habilidade:** {profile.get('ability_spins', 0)}",f"**Habilidade equipada:** {profile.get('ability') or 'Nenhuma'}",f"**Habilidades obtidas:** {', '.join(profile.get('ability_collection', [])) or 'Nenhuma'}",f"**Estilo equipado:** {equipped}",f"**Gamepass Pular Giro:** {gp} • {active}","**Estilos possuídos:**"]
        active_style = profile.get('equipped_style_data')
        lines.append(f"**Estilo ativo:** {active_style['name']} — {active_style['rarity']}" if active_style else "**Estilo ativo:** Nenhum")
        embed=discord.Embed(title="🎒 Inventário do piloto",description="\n".join(lines),color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed,view=InventoryView(self.owner_id),ephemeral=True)

class GachaRollView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=None); self.owner_id = owner_id
        # ID customizado por usuário para restaurar o botão persistente após reinício.
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label == "Girar estilo":
                item.custom_id = f"f1:gacha:spin:{owner_id}"
    @discord.ui.button(label="Girar estilo", emoji="🎲", style=discord.ButtonStyle.primary)
    async def spin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse painel pertence a outro jogador.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        if profile.get("pending_roll"):
            return await interaction.response.send_message("Você já tem um estilo pendente. Aceite ou recuse antes de girar novamente.", ephemeral=True)
        if profile["spins"] < 1:
            return await interaction.response.send_message("Você está sem giros. A loja é apenas informativa; fale com o administrador para comprar.", ephemeral=True)
        # Debita um giro e persiste antes do loading, deixando estado pendente recuperável em caso de reinício.
        style = roll_style()
        profile["spins"] -= 1
        profile["pending_roll"] = {"style": style, "started_at": __import__("time").time()}
        save_profiles()
        skip_active = bool(profile.get("skip_roll_gamepass") and profile.get("skip_roll_active"))
        embed = discord.Embed(title="🎰 GIRANDO...", description="A roleta está escolhendo seu estilo de piloto...", color=discord.Color.dark_grey())
        view = RollLoadingView(self.owner_id, style)
        if skip_active: view.add_item(SkipLoadingButton(self.owner_id, style))
        await interaction.response.edit_message(embed=embed, view=view)
        if not skip_active: await asyncio.sleep(2.5)
        await view.show_result(interaction, style)

class RollLoadingView(discord.ui.View):
    def __init__(self, owner_id, style):
        super().__init__(timeout=180); self.owner_id=owner_id; self.style_data=style
    async def show_result(self, interaction, style):
        rarity=RARITY_DATA[style["rarity"]]
        skills="\n".join(f"{emoji} **{label}:** {style.get('skills', {}).get(STYLE_SKILL_MAP.get(key), 0) if STYLE_SKILL_MAP.get(key) else 0}" for key,label,emoji in SKILL_FIELDS)
        embed=discord.Embed(title=f"{rarity['emoji']} ESTILO SORTEADO: {style['name']}",description=f"**Raridade: {style['rarity'].upper()}**\n{style['trait']}\n\n{skills}\n\n**Pontos do estilo: {rarity['points']}**\n\nDeseja ficar com este estilo?",color=rarity["color"])
        embed.set_footer(text="Aceitar adiciona ao inventário. Recusar descarta o resultado; o giro já foi consumido.")
        resultview=RollConfirmView(self.owner_id, style)
        try: await interaction.message.edit(embed=embed,view=resultview)
        except discord.HTTPException: pass

class SkipLoadingButton(discord.ui.Button):
    def __init__(self, owner_id, style):
        super().__init__(label="Pular animação",emoji="⏭️",style=discord.ButtonStyle.success)
        self.owner_id=owner_id; self.style_data=style
    async def callback(self, interaction):
        if interaction.user.id != self.owner_id: return await interaction.response.send_message("Este botão não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id)
        if not (profile.get("skip_roll_gamepass") and profile.get("skip_roll_active")):
            return await interaction.response.send_message("Gamepass Pular Giro não está ativa.",ephemeral=True)
        await interaction.response.defer()
        view=RollLoadingView(self.owner_id,self.style_data)
        await view.show_result(interaction,self.style_data)

class RollConfirmView(discord.ui.View):
    def __init__(self, owner_id, style):
        super().__init__(timeout=180); self.owner_id=owner_id; self.style_data=style
    async def finish(self, interaction, accept):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Este resultado pertence a outro jogador.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        pending = profile.get("pending_roll")
        if not pending or pending.get("style", {}).get("name") != self.style_data["name"]:
            return await interaction.response.send_message("Resultado pendente não encontrado; inventário não foi alterado.", ephemeral=True)
        if accept:
            style = dict(self.style_data); style["skills"] = dict(style["skills"])
            role, warning = await equip_style_consistently(interaction.guild, interaction.user, profile, style)
            msg = f"✅ **{style['name']}** ({style['rarity']}) aceito! Seu estilo anterior foi substituído."
            if role: msg += f" Cargo aplicado: {role.name}."
            if warning: msg += f"\n⚠️ {warning}"
        else:
            msg = f"🗑️ **{self.style_data['name']}** recusado e descartado. Seu estilo equipado permanece o mesmo."
        profile.pop("pending_roll", None); save_profiles()
        rarity = RARITY_DATA[self.style_data["rarity"]]
        result_embed = discord.Embed(title=f"{rarity['emoji']} Resultado: {self.style_data['name']}", description=f"**{self.style_data['rarity']}** • {self.style_data.get('trait','')}\n\nA mensagem continua disponível. Você pode girar novamente pelo botão abaixo.", color=rarity["color"])
        await interaction.response.edit_message(content=msg, embed=result_embed, view=GachaRollView(self.owner_id))
        # Move the persistent roll panel to the bottom of the channel after an action.
        panel_embed = discord.Embed(title="🎰 Gacha de estilos da F1", description=(
            f"**Giros disponíveis: {profile['spins']}**\nClique para girar. O estilo só entra no inventário após Aceitar.\n\n" +
            "\n".join(f"{RARITY_DATA[r]['emoji']} **{r}** — {RARITY_DATA[r]['chance']}% • {RARITY_DATA[r]['points']} pontos" for r in RARITY_DATA)
        ), color=discord.Color.purple())
        try:
            fresh_panel = await interaction.channel.send(embed=panel_embed, view=GachaRollView(self.owner_id))
            await interaction.message.delete()
        except discord.HTTPException:
            pass
    @discord.ui.button(label="Aceitar",emoji="✅",style=discord.ButtonStyle.success)
    async def accept(self,interaction,button): await self.finish(interaction,True)
    @discord.ui.button(label="Recusar",emoji="❌",style=discord.ButtonStyle.danger)
    async def refuse(self,interaction,button): await self.finish(interaction,False)

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        pass  # Gamepass continua sob liberação administrativa, fora da loja.

@bot.command(name="roll-estilo")
async def roll_style_command(ctx):
    profile=gacha_profile(ctx.author.id)
    embed=discord.Embed(title="🎰 Gacha de estilos da F1",description=(f"**Giros disponíveis: {profile['spins']}**\nClique para girar. O estilo só entra no inventário após Aceitar.\n\n"+"\n".join(f"{RARITY_DATA[r]['emoji']} **{r}** — {RARITY_DATA[r]['chance']}% • {RARITY_DATA[r]['points']} pontos" for r in RARITY_DATA)),color=discord.Color.purple())
    await ctx.send(embed=embed,view=GachaRollView(ctx.author.id))

@bot.command(name="transferir-giros")
async def transfer_style_spins(ctx, jogador: discord.Member, quantidade: int):
    if jogador.bot:
        return await ctx.send("Não é possível transferir giros para bots.")
    if jogador.id == ctx.author.id:
        return await ctx.send("Você não pode transferir giros para si mesmo.")
    if quantidade <= 0:
        return await ctx.send("Informe uma quantidade maior que zero.")
    sender = gacha_profile(ctx.author.id)
    receiver = gacha_profile(jogador.id)
    if int(sender.get("spins", 0)) < quantidade:
        return await ctx.send(f"Você tem apenas **{sender.get('spins', 0)}** giro(s) disponíveis.")
    sender["spins"] -= quantidade
    receiver["spins"] = int(receiver.get("spins", 0)) + quantidade
    save_profiles()
    await ctx.send(f"🎟️ {ctx.author.mention} transferiu **{quantidade} giro(s) de estilo** para {jogador.mention}.\nSaldo restante: **{sender['spins']}** giros.")


@bot.command(name="roll-pendente")
async def pending_roll_command(ctx):
    profile = gacha_profile(ctx.author.id)
    pending = profile.get("pending_roll")
    if not pending:
        return await ctx.send("Você não possui resultado pendente de confirmação.")
    style = pending.get("style", {})
    rarity = RARITY_DATA.get(style.get("rarity"), RARITY_DATA["Comum"])
    skills = "\n".join(f"{emoji} **{label}:** {style.get('skills', {}).get(STYLE_SKILL_MAP.get(key), 0) if STYLE_SKILL_MAP.get(key) else 0}" for key, label, emoji in SKILL_FIELDS)
    embed = discord.Embed(title=f"{rarity['emoji']} Resultado pendente: {style.get('name', 'Estilo desconhecido')}", description=f"**Raridade:** {style.get('rarity')}\n{style.get('trait', '')}\n\n{skills}\n\n**Pontos do estilo:** {rarity['points']}\nDeseja aceitar ou recusar?", color=rarity["color"])
    await ctx.send(embed=embed, view=RollConfirmView(ctx.author.id, style))


@bot.command(name="loja")
async def shop_command(ctx):
    profile = gacha_profile(ctx.author.id)
    embed = discord.Embed(
        title="🛒 Loja informativa — F1 Discord Racing",
        description=(
            f"**Seus giros de estilo:** {profile['spins']}\n"
            f"**Seus giros de habilidade:** {profile.get('ability_spins', 0)}\n\n"
            "**Pacotes de giros de estilo**\n"
            "1 giro — 5k sonhos\n5 giros — 25k sonhos\n10 giros — 50k sonhos\n25 giros — 125k sonhos\n\n"
            "**✨ Giro de habilidade**\n"
            "1 giro — **25k sonhos**\nCada giro sorteia uma habilidade especial.\n\n"
            "**Gamepass: Pular Giro**\nPermite pular o loading do roll quando ativada pelo administrador.\n\n"
            "⚠️ **Pagamento diretamente com o administrador do servidor.** O bot não consulta nem desconta sonhos automaticamente. "
            "Após o pagamento, o administrador libera o giro correspondente."
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed, view=ShopView())

class AbilityRollConfirmView(discord.ui.View):
    def __init__(self, owner_id, ability_name):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.ability_name = ability_name

    async def finish(self, interaction, accept):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Este resultado pertence a outro jogador.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        if profile.get("pending_ability_roll") != self.ability_name:
            return await interaction.response.send_message("Resultado pendente não encontrado.", ephemeral=True)
        if accept:
            profile["ability"] = self.ability_name
            owned = profile.setdefault("ability_collection", [])
            if self.ability_name not in owned:
                owned.append(self.ability_name)
            message = f"✨ Habilidade **{self.ability_name}** equipada com sucesso!"
        else:
            message = f"🗑️ Habilidade **{self.ability_name}** recusada. Sua habilidade anterior foi mantida."
        profile.pop("pending_ability_roll", None)
        save_profiles()
        embed = discord.Embed(title="✨ Resultado do giro de habilidade", description=f"**{self.ability_name}**\n{ABILITY_CATALOG[self.ability_name]}", color=discord.Color.gold())
        await interaction.response.edit_message(content=message, embed=embed, view=None)

    @discord.ui.button(label="Equipar habilidade", emoji="✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        await self.finish(interaction, True)

    @discord.ui.button(label="Recusar", emoji="❌", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction, button):
        await self.finish(interaction, False)


class AbilityRollView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.custom_id = f"f1:ability:spin:{owner_id}"

    @discord.ui.button(label="Girar habilidade", emoji="✨", style=discord.ButtonStyle.primary)
    async def spin(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Este painel pertence a outro jogador.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        if profile.get("pending_ability_roll"):
            return await interaction.response.send_message("Você já tem uma habilidade pendente. Confirme ou recuse antes de girar novamente.", ephemeral=True)
        if int(profile.get("ability_spins", 0)) < 1:
            return await interaction.response.send_message("Você não tem giros de habilidade. Cada giro custa 25k sonhos na loja.", ephemeral=True)
        ability_name = random.choice(list(ABILITY_CATALOG))
        profile["ability_spins"] -= 1
        profile["pending_ability_roll"] = ability_name
        save_profiles()
        await interaction.response.edit_message(embed=discord.Embed(title="✨ GIRANDO HABILIDADE...", description="A roleta está sorteando sua habilidade especial...", color=discord.Color.dark_grey()), view=None)
        await asyncio.sleep(2)
        result = discord.Embed(title=f"✨ HABILIDADE SORTEADA: {ability_name}", description=f"{ABILITY_CATALOG[ability_name]}\n\nDeseja equipar esta habilidade?", color=discord.Color.gold())
        try:
            await interaction.message.edit(embed=result, view=AbilityRollConfirmView(self.owner_id, ability_name))
        except discord.HTTPException:
            pass


@bot.command(name="roll-habilidade")
async def roll_ability_command(ctx):
    profile = gacha_profile(ctx.author.id)
    embed = discord.Embed(title="✨ Roleta de habilidades especiais", description=f"**Giros disponíveis:** {profile.get('ability_spins', 0)}\n**Custo:** 25.000 sonhos por giro\n\nClique para sortear uma habilidade. Você poderá equipar ou recusar o resultado.", color=discord.Color.gold())
    await ctx.send(embed=embed, view=AbilityRollView(ctx.author.id))


@bot.command(name="habilidade-pendente")
async def pending_ability_command(ctx):
    profile = gacha_profile(ctx.author.id)
    ability_name = profile.get("pending_ability_roll")
    if not ability_name or ability_name not in ABILITY_CATALOG:
        return await ctx.send("Você não possui uma habilidade pendente.")
    embed = discord.Embed(title=f"✨ Habilidade pendente: {ability_name}", description=f"{ABILITY_CATALOG[ability_name]}\n\nDeseja equipar?", color=discord.Color.gold())
    await ctx.send(embed=embed, view=AbilityRollConfirmView(ctx.author.id, ability_name))


@bot.command(name="colecao-estilos")
async def style_collection_command(ctx):
    profile=gacha_profile(ctx.author.id)
    style=profile.get("equipped_style_data")
    if not style:
        return await ctx.send("Você ainda não possui estilo equipado.")
    await ctx.send(embed=discord.Embed(
        title=f"{RARITY_DATA[style['rarity']]['emoji']} Seu estilo atual: {style['name']}",
        description=f"**{style['rarity']}** • {style.get('trait', '')}\nEste é seu único estilo ativo.",
        color=RARITY_DATA[style["rarity"]]["color"],
    ))

# Slash commands are administrator-only; purchases are authorized manually out-of-band.
COMPROVANTE_CHANNEL_ID = 1570301822940487690

async def send_admin_receipt(guild, admin, target, action, details):
    channel = guild.get_channel(COMPROVANTE_CHANNEL_ID) if guild else None
    if channel is None and guild:
        try: channel = await guild.fetch_channel(COMPROVANTE_CHANNEL_ID)
        except discord.HTTPException: channel = None
    if channel:
        embed = discord.Embed(title="🧾 Registro de ação administrativa", color=discord.Color.gold())
        embed.add_field(name="Quem realizou", value=f"{admin.mention} ({admin.id})", inline=False)
        embed.add_field(name="Alvo", value=f"{target.mention} ({target.id})", inline=False)
        embed.add_field(name="Ação", value=action, inline=True)
        embed.add_field(name="Detalhes", value=details, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)

COMPROVANTE_CHANNEL_ID = 1570301822940487690

async def send_admin_receipt(guild, admin, target, action, details):
    channel = guild.get_channel(COMPROVANTE_CHANNEL_ID) if guild else None
    if channel is None and guild:
        try: channel = await guild.fetch_channel(COMPROVANTE_CHANNEL_ID)
        except discord.HTTPException: channel = None
    if channel:
        embed = discord.Embed(title="🧾 Registro de ação administrativa", color=discord.Color.gold())
        embed.add_field(name="Quem realizou", value=f"{admin.mention} ({admin.id})", inline=False)
        embed.add_field(name="Alvo", value=f"{target.mention} ({target.id})", inline=False)
        embed.add_field(name="Ação", value=action, inline=True)
        embed.add_field(name="Detalhes", value=details, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)

COMPROVANTE_CHANNEL_ID = 1570301822940487690

async def send_admin_receipt(guild, admin, target, action, details):
    channel = guild.get_channel(COMPROVANTE_CHANNEL_ID) if guild else None
    if channel is None and guild:
        try: channel = await guild.fetch_channel(COMPROVANTE_CHANNEL_ID)
        except discord.HTTPException: channel = None
    if channel:
        embed = discord.Embed(title="🧾 Registro de ação administrativa", color=discord.Color.gold())
        embed.add_field(name="Quem realizou", value=f"{admin.mention} ({admin.id})", inline=False)
        embed.add_field(name="Alvo", value=f"{target.mention} ({target.id})", inline=False)
        embed.add_field(name="Ação", value=action, inline=True)
        embed.add_field(name="Detalhes", value=details, inline=True)
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)

@bot.tree.command(name="adicionar_giros",description="Libera giros manualmente para um jogador")
@app_commands.describe(jogador="Jogador que receberá os giros",quantidade="Quantidade de giros a adicionar")
@app_commands.checks.has_permissions(administrator=True)
async def adicionar_giros(interaction: discord.Interaction,jogador: discord.Member,quantidade: app_commands.Range[int,1,10000]):
    profile=gacha_profile(jogador.id); profile["spins"]+=quantidade; save_profiles()
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Adicionar giros", f"+{quantidade} giro(s). Total agora: {profile['spins']}")
    await interaction.response.send_message(f"🎟️ Adicionados {quantidade} giro(s) para {jogador.mention}. Total: **{profile['spins']}**.",ephemeral=True)

@bot.tree.command(name="adicionar_giros_habilidade", description="Libera giros de habilidade após pagamento externo")
@app_commands.describe(jogador="Jogador que receberá os giros", quantidade="Quantidade de giros de habilidade")
@app_commands.checks.has_permissions(administrator=True)
async def adicionar_giros_habilidade(interaction: discord.Interaction, jogador: discord.Member, quantidade: app_commands.Range[int, 1, 10000]):
    profile = gacha_profile(jogador.id)
    profile["ability_spins"] = int(profile.get("ability_spins", 0)) + quantidade
    save_profiles()
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Adicionar giros de habilidade", f"+{quantidade} giro(s). Total: {profile['ability_spins']}")
    await interaction.response.send_message(f"✨ Adicionados **{quantidade} giro(s) de habilidade** para {jogador.mention}. Total: **{profile['ability_spins']}**.", ephemeral=True)


def find_style_by_keyword(keyword: str):
    """Busca estilo por nome completo, início ou trecho; retorna (estilo, opções)."""
    query = keyword.strip().casefold()
    if not query:
        return None, []
    exact = [item for item in PILOT_STYLES if item["name"].casefold() == query]
    if exact:
        return exact[0], exact
    starts = [item for item in PILOT_STYLES if item["name"].casefold().startswith(query)]
    if len(starts) == 1:
        return starts[0], starts
    if starts:
        return None, starts
    contains = [item for item in PILOT_STYLES if query in item["name"].casefold()]
    if len(contains) == 1:
        return contains[0], contains
    return None, contains

@bot.tree.command(name="setar_estilo", description="Define o estilo de um jogador pelo nome ou palavra-chave (admin)")
@app_commands.describe(jogador="Pessoa que receberá o estilo", estilo="Nome ou palavra-chave, exemplo: prost, senna")
@app_commands.checks.has_permissions(administrator=True)
async def setar_estilo(interaction: discord.Interaction, jogador: discord.Member, estilo: str):
    chosen, matches = find_style_by_keyword(estilo)
    if chosen is None:
        if matches:
            options = "\n".join(f"• {item['name']} ({item['rarity']})" for item in matches[:15])
            return await interaction.response.send_message(
                f"Encontrei mais de um estilo para **{estilo}**. Seja mais específico:\n{options}",
                ephemeral=True,
            )
        return await interaction.response.send_message(
            f"Não encontrei estilo com a palavra **{estilo}**. Tente uma parte do nome, como prost ou senna.",
            ephemeral=True,
        )
    profile = gacha_profile(jogador.id)
    role, warning = await equip_style_consistently(interaction.guild, jogador, profile, dict(chosen))
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Setar estilo", f"Estilo atribuído: {chosen['name']} ({chosen['rarity']})")
    response = f"🏎️ Estilo **{chosen['name']}** setado para {jogador.mention}."
    if role: response += f" Cargo: {role.mention}."
    if warning: response += f"\n⚠️ {warning}"
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="setar_estilo_cargo", description="Define o estilo de um jogador selecionando o cargo (admin)")
@app_commands.describe(jogador="Pessoa que receberá o estilo", cargo="Cargo correspondente ao estilo")
@app_commands.checks.has_permissions(administrator=True)
async def setar_estilo_cargo(interaction: discord.Interaction, jogador: discord.Member, cargo: discord.Role):
    style_name = next(
        (name for name, role_id in PILOT_ROLE_IDS.items() if role_id and int(role_id) == cargo.id),
        None,
    )
    if not style_name:
        return await interaction.response.send_message(
            "Esse cargo não está associado a nenhum estilo em PILOT_ROLE_IDS.",
            ephemeral=True,
        )
    chosen = next((item for item in PILOT_STYLES if item["name"] == style_name), None)
    if not chosen:
        return await interaction.response.send_message(
            "O cargo foi reconhecido, mas o estilo correspondente não existe no catálogo atual.",
            ephemeral=True,
        )
    profile = gacha_profile(jogador.id)
    role, warning = await equip_style_consistently(interaction.guild, jogador, profile, dict(chosen))
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Setar estilo pelo cargo", f"Estilo atribuído: {chosen['name']} ({chosen['rarity']})")
    response = f"🏎️ Estilo **{chosen['name']}** setado para {jogador.mention} pelo cargo {cargo.mention}."
    if warning: response += f"\n⚠️ {warning}"
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="sincronizar_estilo", description="Atualiza o estilo do perfil conforme o cargo atual (admin)")
@app_commands.describe(jogador="Jogador cujos cargos serão verificados")
@app_commands.checks.has_permissions(administrator=True)
async def sincronizar_estilo(interaction: discord.Interaction, jogador: discord.Member):
    reverse_roles = {int(role_id): name for name, role_id in PILOT_ROLE_IDS.items() if role_id}
    found = [role for role in jogador.roles if role.id in reverse_roles]
    if len(found) != 1:
        if not found:
            message = "Esse membro não possui nenhum cargo de estilo reconhecido. O perfil foi mantido sem alterações."
        else:
            message = "Encontrei mais de um cargo de estilo. Remova os cargos extras e tente novamente; não alterei o perfil."
        return await interaction.response.send_message(message, ephemeral=True)

    style_name = reverse_roles[found[0].id]
    style = next((item for item in PILOT_STYLES if item["name"] == style_name), None)
    if not style:
        return await interaction.response.send_message("O cargo foi reconhecido, mas o estilo não existe no catálogo atual.", ephemeral=True)

    profile = gacha_profile(jogador.id)
    profile["equipped_style"] = style_name
    profile["equipped_style_data"] = dict(style)
    profile.pop("style_collection", None)
    save_profiles()
    await interaction.response.send_message(
        f"✅ Perfil de {jogador.mention} sincronizado com o cargo **{style_name}**.",
        ephemeral=True,
    )

@bot.tree.command(name="deletar_giros", description="Remove giros de um jogador (admin)")
@app_commands.describe(jogador="Pessoa de quem remover giros", quantidade="Quantidade de giros a remover")
@app_commands.checks.has_permissions(administrator=True)
async def deletar_giros(interaction: discord.Interaction, jogador: discord.Member, quantidade: app_commands.Range[int, 1, 10000]):
    profile = gacha_profile(jogador.id)
    before = int(profile.get("spins", 0))
    removed = min(before, quantidade)
    profile["spins"] = before - removed
    save_profiles()
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Remover giros", f"-{removed} giro(s). Total agora: {profile['spins']}")
    await interaction.response.send_message(f"🗑️ Removidos {removed} giro(s) de {jogador.mention}. Saldo: **{profile['spins']}**.", ephemeral=True)


@bot.tree.command(name="gamepass",description="Define Gamepass Pular Giro de um jogador")
@app_commands.describe(jogador="Jogador",possui="Se tem a Gamepass",ativa="Se a Gamepass fica ativa no perfil")
@app_commands.checks.has_permissions(administrator=True)
async def gamepass(interaction: discord.Interaction,jogador: discord.Member,possui: bool,ativa: bool):
    profile=gacha_profile(jogador.id); profile["skip_roll_gamepass"]=possui; profile["skip_roll_active"]=bool(possui and ativa); save_profiles()
    state="possui e está ativa" if possui and ativa else ("possui, mas está desativada" if possui else "não possui")
    await interaction.response.send_message(f"⏭️ Gamepass Pular Giro de {jogador.mention}: **{state}**.",ephemeral=True)

@bot.tree.command(name="gamepass_perfil",description="Ativa ou desativa Gamepass Pular Giro no perfil do jogador")
@app_commands.describe(ativa="Estado ativo da Gamepass")
async def gamepass_perfil(interaction: discord.Interaction,ativa: bool):
    profile=gacha_profile(interaction.user.id)
    if not profile.get("skip_roll_gamepass"): return await interaction.response.send_message("Você não possui a Gamepass Pular Giro.",ephemeral=True)
    profile["skip_roll_active"]=ativa; save_profiles()
    await interaction.response.send_message(f"Gamepass Pular Giro {'ativada' if ativa else 'desativada'} no seu perfil.",ephemeral=True)

@bot.tree.command(name="equipar_estilo",description="Mostra seu estilo atualmente equipado")
async def equipar_estilo(interaction: discord.Interaction):
    profile=gacha_profile(interaction.user.id)
    style=profile.get("equipped_style_data")
    if not style:
        return await interaction.response.send_message("Você ainda não possui estilo equipado.",ephemeral=True)
    await interaction.response.send_message(
        f"Seu estilo ativo é **{style['name']}** ({style['rarity']}). "
        "Para trocar, aceite um novo resultado em !roll-estilo.",
        ephemeral=True,
    )



# Campeonato persistente (uma temporada ativa por servidor).
CHAMPIONSHIP_FILE = Path(__file__).with_name("campeonato.json")
CHAMPIONSHIP_POINTS = {1: 10, 2: 7, 3: 5, 4: 3, 5: 1}

def load_championship():
    try:
        if CHAMPIONSHIP_FILE.exists():
            data = json.loads(CHAMPIONSHIP_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"seasons": {}, "active": {}}

CHAMPIONSHIP = load_championship()

def save_championship():
    CHAMPIONSHIP_FILE.write_text(json.dumps(CHAMPIONSHIP, ensure_ascii=False, indent=2), encoding="utf-8")

def season_for(guild_id):
    season_id = CHAMPIONSHIP.get("active", {}).get(str(guild_id))
    return CHAMPIONSHIP.get("seasons", {}).get(season_id) if season_id else None

async def register_championship_result(race, order, fastest):
    season = season_for(race.guild_id)
    if not season:
        return
    race_id = f"{race.guild_id}-{int(__import__('time').time())}-{race.channel_id}"
    if any(item.get("race_id") == race_id for item in season.get("races", [])):
        return
    results = []
    for position, driver in enumerate(order, 1):
        results.append({
            "user_id": str(driver.user.id),
            "name": driver_display_name(driver),
            "position": position,
            "retired": bool(driver.retired),
            "fastest_lap": bool(fastest and fastest.user.id == driver.user.id),
            "lap_time": driver.best_lap_time or driver.last_lap_time,
        })
    season.setdefault("races", []).append({
        "race_id": race_id, "circuit": race.circuit_name,
        "date": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "results": results,
    })
    save_championship()

def championship_table(season):
    table = {}
    for race_data in season.get("races", []):
        results = race_data.get("results", [])
        for result in results:
            uid = result["user_id"]
            row = table.setdefault(uid, {"user_id": uid, "name": result["name"], "points": 0, "wins": 0, "seconds": 0, "thirds": 0, "fastest": 0, "races": 0})
            row["races"] += 1
            pos = result["position"]
            if not result.get("retired"):
                row["points"] += CHAMPIONSHIP_POINTS.get(pos, 0)
                row["wins"] += pos == 1
                row["seconds"] += pos == 2
                row["thirds"] += pos == 3
                if result.get("fastest_lap") and pos <= 3:
                    row["points"] += 1
                    row["fastest"] += 1
    return sorted(table.values(), key=lambda x: (x["points"], x["wins"], x["seconds"], x["thirds"], x["fastest"]), reverse=True)

@bot.command(name="campeonato")
async def championship_command(ctx):
    season = season_for(ctx.guild.id if ctx.guild else 0)
    if not season:
        return await ctx.send("Não existe temporada ativa. Um administrador pode usar `!iniciartemporada nome`.")
    rows = championship_table(season)
    text_rows = [f"**P{i} — {r['name']}** • {r['points']} pts | {r['wins']}V {r['seconds']}S {r['thirds']}T | {r['fastest']} VR" for i, r in enumerate(rows, 1)]
    embed = discord.Embed(title=f"🏆 Campeonato — {season['name']}", description="\n".join(text_rows) or "Nenhuma corrida registrada.", color=discord.Color.gold())
    embed.set_footer(text=f"Etapas concluídas: {len(season.get('races', []))}")
    await ctx.send(embed=embed)

@bot.command(name="ranking")
async def ranking_command(ctx):
    await championship_command(ctx)

@bot.command(name="temporada")
async def season_command(ctx):
    season = season_for(ctx.guild.id if ctx.guild else 0)
    if not season:
        return await ctx.send("Nenhuma temporada ativa.")
    await ctx.send(f"🏁 **{season['name']}** — {len(season.get('races', []))} etapa(s) registrada(s).")

@bot.command(name="resultado")
async def result_command(ctx):
    season = season_for(ctx.guild.id if ctx.guild else 0)
    if not season or not season.get("races"):
        return await ctx.send("Ainda não há resultados registrados.")
    latest = season["races"][-1]
    lines = [f"**P{r['position']}** {r['name']}" + (" — ⛔ Abandonou" if r.get("retired") else "") + (" • 🟣 Volta mais rápida" if r.get("fastest_lap") else "") for r in latest["results"]]
    await ctx.send(embed=discord.Embed(title=f"Resultado — {latest['circuit']}", description="\n".join(lines), color=discord.Color.gold()))

@bot.command(name="estatisticas")
async def statistics_command(ctx):
    season = season_for(ctx.guild.id if ctx.guild else 0)
    if not season:
        return await ctx.send("Nenhuma temporada ativa.")
    rows = championship_table(season)
    if not rows:
        return await ctx.send("Ainda não há estatísticas.")
    r = next((x for x in rows if x["user_id"] == str(ctx.author.id)), None)
    if not r:
        return await ctx.send("Você ainda não participou de uma corrida desta temporada.")
    await ctx.send(f"📊 **{r['name']}** — {r['points']} pontos, {r['wins']} vitória(s), {r['fastest']} volta(s) mais rápida(s), {r['races']} corrida(s).")

@bot.command(name="iniciartemporada")
@commands.has_permissions(administrator=True)
async def start_season_command(ctx, *, name="Temporada"):
    gid = str(ctx.guild.id)
    season_id = f"{gid}-{int(__import__('time').time())}"
    CHAMPIONSHIP["seasons"][season_id] = {"name": name, "guild_id": gid, "races": []}
    CHAMPIONSHIP["active"][gid] = season_id
    save_championship()
    await ctx.send(f"🏆 Temporada **{name}** iniciada!")

@bot.command(name="finalizartemporada")
@commands.has_permissions(administrator=True)
async def finish_season_command(ctx):
    gid = str(ctx.guild.id)
    if gid not in CHAMPIONSHIP.get("active", {}):
        return await ctx.send("Não existe temporada ativa.")
    CHAMPIONSHIP["active"].pop(gid, None)
    save_championship()
    await ctx.send("🏁 Temporada finalizada. O histórico foi preservado.")

@bot.command(name="resetcampeonato")
@commands.has_permissions(administrator=True)
async def reset_championship_command(ctx):
    gid = str(ctx.guild.id)
    season = season_for(ctx.guild.id)
    if not season:
        return await ctx.send("Não existe temporada ativa.")
    season["races"] = []
    save_championship()
    await ctx.send("♻️ Resultados da temporada ativa foram reiniciados.")

SYSTEM_PAGES = ("estilos", "pneus", "habilidades", "pilotagem", "novidades")

def system_embed(page):
    if page == "estilos":
        rarity_lines = [f"{data['emoji']} **{rarity}** — {data['points']} pontos extras • chance {data['chance']}%" for rarity, data in RARITY_DATA.items()]
        stat_labels = {"tyre_management":"PNE","curves":"CUR","straights":"RET","braking":"CLA","acceleration":"MOT","control":"CTL"}
        style_lines = []
        for style in PILOT_STYLES:
            vals = " ".join(f"{stat_labels[k]}+{v}" for k, v in style.get("skills", {}).items() if v)
            style_lines.append(f"• **{style['name']}** ({style['rarity']}): {vals or 'sem bônus'}")
        description = "**Raridades e pontos extras**\n" + "\n".join(rarity_lines)
        description += "\n\n**Como ler os bônus**\nPNE = Gerenciamento de pneus • CUR = Curvas • RET = Velocidade em retas • CLA = Classificação/frenagem • MOT = Motor/aceleração • CTL = Controle. Os bônus são somados aos atributos pessoais durante a corrida. Cada estilo tem uma distribuição própria e pode ter atributos zerados."
        description += "\n\n**Estilos disponíveis**\n" + "\n".join(style_lines)
        if len(description) > 4000:
            description = description[:3900] + "\n… (catálogo completo permanece no código/coleção de estilos)."
        return discord.Embed(title="🎭 Sistema de estilos", description=description, color=discord.Color.purple())
    if page == "pneus":
        lines = []
        for key, tire in TIRES.items():
            lines.append(f"**{tire['label']}**\nAderência: {tire['grip']:.2f} • Desgaste: {tire['wear']:.2f}\nSeca: {tire['dry']:.2f} • Úmida: {tire['damp']:.2f} • Molhada: {tire['wet']:.2f}")
        return discord.Embed(title="🛞 Pneus e clima", description="O composto escolhido altera aderência, ritmo e desgaste. Escolha conforme a condição da pista.\n\n" + "\n\n".join(lines), color=discord.Color.orange())
    if page == "habilidades":
        lines = [f"✨ **{name}** — {description}" for name, description in ABILITY_CATALOG.items()]
        return discord.Embed(title="✨ Habilidades especiais", description="As habilidades passivas podem ser obtidas pela roleta `!roll-habilidade`, por 25k sonhos cada giro.\n\n" + "\n".join(lines), color=discord.Color.gold())
    if page == "pilotagem":
        mode_lines = [f"**{data['label']}** — ritmo {data['pace']:+.2f} • risco {data['risk']:+.2f} • defesa {data['defense']:+.2f} • ataque {data['attack']:+.2f}" for data in DRIVING_MODES.values()]
        skill_lines = [f"{emoji} **{label}** — atributo pessoal; os 10 pontos são distribuídos uma vez e ficam bloqueados." for key, label, emoji in SKILL_FIELDS]
        description = "**Atributos**\n" + "\n".join(skill_lines)
        description += "\n\n**Modos de pilotagem**\n" + "\n".join(mode_lines)
        description += "\n\n**Ações adicionais**\n• Overtake Mode: tenta ultrapassar quando há adversário elegível à frente.\n• Boost Mode: usa energia para buscar ritmo extra.\n• Decisões são privadas até todos os pilotos confirmarem."
        return discord.Embed(title="🏎️ Atributos e pilotagem", description=description, color=discord.Color.blue())
    description = (
        "**Novidades desta versão**\n"
        "• Seis atributos pessoais: gerenciamento de pneus, curvas, velocidade, classificação, motor e controle.\n"
        "• Distribuição fixa de 10 pontos por piloto.\n"
        "• Habilidades especiais obtidas pela roleta, por 25k sonhos cada giro.\n"
        "• Campeonato com pontuação, histórico, ranking e estatísticas persistentes.\n"
        "• Pontos do campeonato: 10 / 7 / 5 / 3 / 1; +1 pela volta mais rápida se terminar no top 3.\n"
        "• Imagens de eventos configuráveis por pastas e links, com seleção aleatória.\n"
        "• Circuitos, clima, pneus, desgaste, energia e decisões estratégicas influenciam a simulação.\n\n"
        "**Comandos úteis**\n"
        "f1 criar lobby • perfil ver piloto • roll-estilo girar estilo • campeonato consultar temporada • ranking ver classificação."
    )
    return discord.Embed(title="🆕 Novidades e sistemas", description=description, color=discord.Color.green())

class SystemView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    async def show(self, interaction, page):
        await interaction.response.edit_message(embed=system_embed(page), view=self)
    @discord.ui.button(label="Estilos", emoji="🎭", style=discord.ButtonStyle.primary, row=0)
    async def styles(self, interaction, button): await self.show(interaction, "estilos")
    @discord.ui.button(label="Pneus", emoji="🛞", style=discord.ButtonStyle.secondary, row=0)
    async def tires(self, interaction, button): await self.show(interaction, "pneus")
    @discord.ui.button(label="Habilidades", emoji="✨", style=discord.ButtonStyle.secondary, row=0)
    async def abilities(self, interaction, button): await self.show(interaction, "habilidades")
    @discord.ui.button(label="Atributos e pilotagem", emoji="🏎️", style=discord.ButtonStyle.secondary, row=1)
    async def driving(self, interaction, button): await self.show(interaction, "pilotagem")
    @discord.ui.button(label="Novidades", emoji="🆕", style=discord.ButtonStyle.success, row=1)
    async def news(self, interaction, button): await self.show(interaction, "novidades")

@bot.command(name="sistema")
async def system_command(ctx):
    await ctx.send(embed=system_embed("novidades"), view=SystemView())


@bot.command(name="comandos")
async def commands_list(ctx):
    embed = discord.Embed(title="📜 Comandos do F1 Discord Racing", color=discord.Color.blue())
    embed.description = (
        "`!f1` — cria um lobby; o host usa os botões do próprio painel para configurar, classificar e iniciar.\n"
        "`!perfil [@membro]` — consulta seu perfil ou o de outro piloto.\n`!roll-estilo` — roleta gacha de estilos de pilotos F1.\n`!transferir-giros @membro quantidade` — transfere giros de estilo.\n`!roll-habilidade` — roleta de habilidades especiais (25k sonhos por giro).\n`!habilidade-pendente` — recupera um resultado pendente.\n`!roll-pendente` — recupera resultado aguardando confirmação.\n`!loja` — loja visual de giros (sonhos da Loritta; confirmação manual).\n`!colecao-estilos` — mostra estilos obtidos.\n`/adicionar_giros`, `/adicionar_giros_habilidade`, `/deletar_giros`, `/setar_estilo` e `/gamepass` — administração de giros/estilos/habilidades.\n"
        "`!ajuda` — guia de funcionamento e explicação das estratégias.\n"
        "`!campeonato` / `!ranking` / `!estatisticas` / `!temporada` / `!resultado` — consultar campeonato, etapa e desempenho.\n"
        "`!iniciartemporada` / `!finalizartemporada` / `!resetcampeonato` — gestão de temporada (administradores).\n"
        "`!sistema` — painel interativo com explicações de estilos, pneus, habilidades, atributos e novidades.\n"
        "`!comandos` — exibe esta lista.\n"
        "`!f1status` — mostra estado do lobby/corrida.\n"
        "`!f1cancel` — cancela lobby/corrida (somente host).\n\n"
        "Não existem mais `!f1start` e `!f1race`: classificação e início da corrida são feitos pelos botões no painel `!f1`."
    )
    await ctx.send(embed=embed)


@bot.command(name="ajuda")
async def help_f1(ctx):
    embed = discord.Embed(title="📘 Guia de corrida — F1 Discord Racing", color=discord.Color.green())
    embed.description = (
        "**1) Criar e entrar:** use `!f1`. Pilotos clicam Entrar na corrida, configuram o carro e os pneus, e marcam Estou pronto.\n"
        "**2) Perfil/crachá:** `!perfil [@membro]` consulta o próprio perfil ou o perfil de outro piloto; os botões de configuração aparecem apenas no próprio perfil.\n**3) Gacha:** `!roll-estilo` permite gastar giros para obter estilos de pilotos. `!transferir-giros @membro quantidade` envia giros de estilo para outro membro. `!roll-habilidade` usa um giro de habilidade liberado pelo administrador após pagamento de 25k sonhos. `!loja` mostra pacotes em sonhos; a compra é confirmada manualmente e o bot não desconta sonhos. `!colecao-estilos` lista os estilos recebidos. Os estilos têm raridades e pontos extras próprios. Nome aparece na corrida; equipe e pneu favorito são visuais, sem impacto na simulação. Perfil salvo é carregado no próximo lobby; os pontos pessoais só podem ser distribuídos uma vez e depois ficam bloqueados.\n"
        "**4) Classificação:** o host clica Iniciar classificação no painel do lobby. A classificação usa habilidades, pneus, clima e uma variação aleatória moderada para definir o grid.\n"
        "**5) Corrida:** o host clica Iniciar corrida no painel de classificação. Cada volta é dividida em quatro trechos de reta/curva. Em cada trecho, todos escolhem pelos mesmos botões públicos; a escolha fica oculta até todos confirmarem. O prazo é 45 segundos (ou o valor configurado); quem não decidir recebe Seguro.\n\n"
        "**AÇÕES DE PILOTAGEM**\n"
        "⚖️ **Normal:** ritmo equilibrado, risco padrão e pequena recuperação de energia quando não usa Boost/Overtake. É a opção versátil.\n"
        "🔥 **Agressivo:** tenta ganhar tempo com ritmo mais rápido e maior potencial de ataque, mas aumenta o risco de erro/derrapagem e o desgaste dos pneus.\n"
        "🛡️ **Defensivo:** prioriza preservar a posição e reduzir riscos; perde um pouco de ritmo e tem menor força de ataque.\n"
        "🟢 **Seguro:** ritmo mais conservador, risco reduzido e desgaste menor. Bom para proteger pneus ou evitar erros, mas tende a perder tempo.\n"
        "↗️ **Overtake Mode:** seleciona uma tentativa de ultrapassagem. Só é elegível se houver um carro imediatamente à frente dentro da janela de 1,0 segundo e energia suficiente (12). Gasta energia; chance depende da diferença, atributos e fatores aleatórios. Não garante ultrapassar. Se estiver fora da janela/sem energia, a tentativa aplica penalidade.\n"
        "⚡ **Boost Mode:** usa 15 de energia para ganhar ritmo no trecho. Se não houver energia suficiente, não ativa e a simulação aplica uma penalidade leve.\n\n"
        "**CARRO, PNEUS E CONDIÇÕES**\n"
        "• Gerenciamento de pneus reduz desgaste; Curvas melhora trechos técnicos; Velocidade favorece retas e ultrapassagens; Classificação melhora o grid; Motor ajuda na aceleração; Controle reduz riscos. Os 10 pontos pessoais ficam bloqueados após a primeira distribuição.\n"
        "• Soft: rápido, mas desgasta muito. Medium: equilíbrio. Hard: menos aderência, maior durabilidade. Intermediate: indicado para pista úmida. Wet: melhor para chuva forte, mas fraco em pista seca. Pneus inadequados prejudicam o ritmo.\n"
        "• O desgaste reduz a condição do pneu ao longo dos segmentos. A energia é limitada e pode ser recuperada um pouco com Normal/Seguro. Clima chuvoso aumenta a perda de ritmo e o risco.\n"
        "• Erros e derrapagens são eventos probabilísticos; Controle, modo escolhido, chuva e desgaste influenciam o risco.\n"
        "• Habilidades especiais podem ser obtidas com `!roll-habilidade`; cada giro custa 25k sonhos e é liberado pelo administrador após pagamento. Use `!habilidade-pendente` se precisar recuperar um resultado interrompido.\n"
        "• Campeonato: 1º 10 pts, 2º 7, 3º 5, 4º 3, 5º 1; volta mais rápida vale +1 se o piloto terminar no top 3. Abandono não pontua.\n\n"
        "**Botões de gestão:** Configurar corrida permite ao host escolher voltas, circuito, clima e prazo de decisão. Iniciar classificação e Iniciar corrida avançam o fluxo sem comandos separados."
    )
    embed.set_footer(text="As mecânicas são uma simulação simplificada e não reproduzem integralmente as regras oficiais da F1.")
    await ctx.send(embed=embed)


STYLE_IMAGE_FILE = Path(__file__).parent / "assets" / "estilos" / "links.json"

def style_image_url(style_name):
    style = next((item for item in PILOT_STYLES if item["name"] == style_name), None)
    if style and style.get("image_url"):
        return style["image_url"]
    try:
        mapping = json.loads(STYLE_IMAGE_FILE.read_text(encoding="utf-8"))
        value = mapping.get(style_name, "") if isinstance(mapping, dict) else ""
        return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None
    except (OSError, json.JSONDecodeError):
        return None


def build_profile_embed(profile, member, guild):
    equipped = profile.get("equipped_style")
    style = profile.get("equipped_style_data") or next((item for item in PILOT_STYLES if item["name"] == equipped), None)
    role_id = PILOT_ROLE_IDS.get(equipped) if equipped else None
    role = guild.get_role(role_id) if guild and role_id else None
    style_label = role.mention if role else (f"**{equipped}** (cargo não configurado)" if equipped else "Nenhum estilo equipado")
    desc = (
        f"**🏷️ Piloto:** {profile.get('name') or member.display_name}\n"
        f"**🎂 Idade:** {profile.get('age') or 'Não definida'}\n"
        f"**🏢 Equipe:** {profile.get('team') or 'Não definida'}"
    )
    if guild:
        season = season_for(guild.id)
        if season:
            rows = championship_table(season)
            ranking = next((i for i, row in enumerate(rows, 1) if row["user_id"] == str(member.id)), None)
            points = next((row["points"] for row in rows if row["user_id"] == str(member.id)), 0)
            championship_line = f"**🏆 Campeonato atual:** P{ranking} • {points} pontos" if ranking else "**🏆 Campeonato atual:** ainda sem pontuação"
        else:
            championship_line = "**🏆 Campeonato:** nenhuma temporada ativa"
        desc += f"\n{championship_line}"
    desc += f"\n**🏎️ Estilo equipado:** {style_label}\n"
    personal = profile.get("skills", migrate_skill_distribution({}))
    bonuses = style.get("skills", {}) if style else {}
    desc += "\n**📊 Atributos pessoais (10 pontos)**\n"
    desc += " • ".join(f"{label}: {personal.get(key, 0)}" for key, label, _ in SKILL_FIELDS)
    ability = profile.get("ability")
    desc += f"\n\n**✨ Habilidade equipada:** {ability or 'Não definida'}\n_{ABILITY_CATALOG.get(ability, 'Habilidade passiva.')}_"
    style_values = {key: int(bonuses.get(source, 0)) if source else 0 for key, source in STYLE_SKILL_MAP.items()}
    desc += "\n\n**🏆 Bônus do estilo**\n"
    desc += " • ".join(f"{label}: +{style_values.get(key, 0)}" for key, label, _ in SKILL_FIELDS) if style else "Nenhum estilo equipado."
    desc += "\n\n**⚙️ Atributos finais (pessoal + estilo)**\n"
    desc += " • ".join(f"{label}: {int(personal.get(key, 0)) + style_values.get(key, 0)}" for key, label, _ in SKILL_FIELDS)
    embed = discord.Embed(title="🏎️ Perfil do piloto", description=desc, color=discord.Color.orange())
    photo_url = profile.get("photo_url")
    if photo_url and photo_url.startswith(("https://", "http://")):
        embed.set_thumbnail(url=photo_url)
    style_url = style_image_url(equipped) if equipped else None
    if style_url:
        embed.set_image(url=style_url)
    return embed


async def refresh_profile_message(interaction, message_id, profile):
    if not message_id or not interaction.channel or not interaction.guild:
        return
    try:
        message = await interaction.channel.fetch_message(message_id)
        await message.edit(embed=build_profile_embed(profile, interaction.user, interaction.guild), view=ProfileView(interaction.user.id))
    except discord.HTTPException:
        pass


@bot.command(name="perfil")
async def profile_command(ctx, membro: Optional[discord.Member] = None):
    target = membro or ctx.author
    profile = gacha_profile(target.id)
    view = ProfileView(ctx.author.id) if target.id == ctx.author.id else None
    await ctx.send(embed=build_profile_embed(profile, target, ctx.guild), view=view)


@bot.command(name="f1")
async def create_race(ctx):
    if ctx.channel.id in races:
        return await ctx.send("Já existe um lobby/corrida neste canal. Use `!f1cancel`.")
    circuit_name = random.choice(list(CIRCUITS.keys()))
    weather_name = random.choice(list(WEATHER.keys()))
    weather = WEATHER[weather_name]
    race = Race(
        channel=ctx.channel,
        channel_id=ctx.channel.id,
        guild_id=ctx.guild.id if ctx.guild else 0,
        host_id=ctx.author.id,
        circuit_name=circuit_name,
        weather_name=weather_name,
        ambient_temp=random.randint(*weather["ambient"]),
        track_temp=random.randint(*weather["track"]),
        surface=weather["surface"],
    )
    races[ctx.channel.id] = race
    race.message = await ctx.send(embed=lobby_embed(race), view=LobbyView(race))


@bot.command(name="f1status")
async def status_command(ctx):
    race = race_for_channel(ctx.channel.id)
    if not race:
        return await ctx.send("Não há lobby/corrida ativa neste canal.")
    if race.race_started:
        embed = standings_embed(race, race.current_lap, f"segmento {race.current_segment}", [])
    else:
        embed = lobby_embed(race)
    if race.message:
        await race.message.edit(embed=embed)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
    else:
        await ctx.send(embed=embed)


@bot.command(name="f1cancel")
async def cancel_command(ctx):
    race = race_for_channel(ctx.channel.id)
    if not race:
        return await ctx.send("Não há lobby/corrida ativa neste canal.")
    if ctx.author.id != race.host_id:
        return await ctx.send("Somente o host pode cancelar.")
    if race.race_task and not race.race_task.done():
        race.race_task.cancel()
    races.pop(ctx.channel.id, None)
    if race.message:
        try:
            await race.message.edit(embed=lobby_embed(race, title="🛑 Corrida cancelada"), view=ClosedView())
        except discord.HTTPException:
            pass
    await ctx.send("🛑 Corrida cancelada pelo host.")


_persistent_gacha_views_registered = False

@bot.event
async def on_ready():
    global _persistent_gacha_views_registered
    print(f"Bot conectado como {bot.user} (ID {bot.user.id}).")
    if not _persistent_gacha_views_registered:
        for user_id in USER_PROFILES.keys():
            bot.add_view(GachaRollView(int(user_id)))
            bot.add_view(AbilityRollView(int(user_id)))
        _persistent_gacha_views_registered = True
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")
    except Exception as exc:
        print(f"Falha ao sincronizar slash commands: {exc}")
    print("Comandos: !f1, !perfil, !roll-estilo, !loja, !sistema, !comandos, !ajuda, !f1status, !f1cancel")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Sincroniza o perfil quando o membro troca para exatamente um cargo de estilo."""
    if before.roles == after.roles:
        return
    reverse_roles = {int(role_id): name for name, role_id in PILOT_ROLE_IDS.items() if role_id}
    style_roles = [role for role in after.roles if role.id in reverse_roles]
    if len(style_roles) != 1:
        if len(style_roles) > 1:
            print(f"⚠️ {after} possui vários cargos de estilo; perfil não foi alterado.")
        # Remover o cargo não apaga o estilo salvo automaticamente.
        return

    style_name = reverse_roles[style_roles[0].id]
    style = next((item for item in PILOT_STYLES if item["name"] == style_name), None)
    if not style:
        return
    profile = gacha_profile(after.id)
    if profile.get("equipped_style") == style_name:
        return
    profile["equipped_style"] = style_name
    profile["equipped_style_data"] = dict(style)
    profile.pop("style_collection", None)
    try:
        save_profiles()
        print(f"🔄 Estilo de {after} sincronizado pelo cargo: {style_name}.")
    except OSError:
        print(f"⚠️ Não foi possível salvar o estilo sincronizado de {after}.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Erro em comando {ctx.command}: {error}")
    await ctx.send("⚠️ Erro ao executar comando. Confira o terminal.")


if not TOKEN:
    raise RuntimeError("Defina DISCORD_TOKEN no arquivo .env")

bot.run(TOKEN)
