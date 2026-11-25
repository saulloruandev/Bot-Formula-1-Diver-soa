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
SEGMENTS_PER_LAP = 4  # reta, curva, reta, curva

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CIRCUITS = {
    "Interlagos": {
        "base_lap": 102.35,
        "corners": 0.28, "straights": 0.27, "braking": 0.18,
        "acceleration": 0.17, "control": 0.10,
        "segments": ["reta", "curva", "reta", "curva"],
    },
    "Monza": {
        "base_lap": 83.20,
        "corners": 0.15, "straights": 0.42, "braking": 0.20,
        "acceleration": 0.15, "control": 0.08,
        "segments": ["reta", "curva", "reta", "curva"],
    },
    "Silverstone": {
        "base_lap": 92.80,
        "corners": 0.34, "straights": 0.23, "braking": 0.15,
        "acceleration": 0.16, "control": 0.12,
        "segments": ["curva", "reta", "curva", "reta"],
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
    "tyre_management": None,
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


class DecisionAction(TypedDict):
    mode: str
    attack: bool
    boost: bool


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
    tire_wear: float = 0.0  # 0-100
    energy: float = 100.0  # energia de jogo, 0-100
    distance: float = 0.0  # progresso em unidades de segmento
    finished: bool = False
    current_mode: str = "normal"
    chosen_action: Optional[DecisionAction] = None
    lap_segment_times: List[float] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    style_name: Optional[str] = None
    style_curves: int = 0
    style_straights: int = 0
    style_braking: int = 0
    style_acceleration: int = 0
    style_control: int = 0
    car_damage: float = 0.0  # 0-100, cresce durante a corrida
    retired: bool = False

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

    @property
    def full(self):
        return len(self.drivers) >= MAX_PLAYERS

    @property
    def all_ready(self):
        return len(self.drivers) >= MIN_PLAYERS and all(d.ready for d in self.drivers.values())


races: Dict[int, Race] = {}

# Perfis são guardados localmente para sobreviver a reinícios do bot.
PROFILE_FILE = Path(__file__).with_name("profiles.json")
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
    try:
        if PROFILE_FILE.exists():
            data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            # Migra perfis antigos (20 pontos) para o novo limite de 10,
            # preservando proporcionalmente a distribuição anterior.
            changed = False
            for profile in data.values():
                if not isinstance(profile, dict):
                    continue
                skills = profile.get("skills")
                if not isinstance(skills, dict):
                    continue
                values = {key: max(0, int(skills.get(key, 0))) for key, label, emoji in SKILL_FIELDS}
                total = sum(values.values())
                if total > SKILL_POINTS:
                    exact = {key: values[key] * SKILL_POINTS / total for key in values}
                    scaled = {key: int(exact[key]) for key in exact}
                    remainder = SKILL_POINTS - sum(scaled.values())
                    order = sorted(exact, key=lambda key: exact[key] - scaled[key], reverse=True)
                    for key in order[:remainder]:
                        scaled[key] += 1
                    profile["skills"] = scaled
                    changed = True
            if changed:
                PROFILE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}

USER_PROFILES = load_profiles()

def migrate_skill_distribution(skills):
    """Migra cinco atributos antigos para seis, preservando a proporção total."""
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
        return {"tyre_management": 1, "curves": 2, "speed": 2, "qualifying": 1, "engine": 2, "control": 2}
    if total != SKILL_POINTS:
        exact = {key: value * SKILL_POINTS / total for key, value in values.items()}
        scaled = {key: int(value) for key, value in exact.items()}
        remainder = SKILL_POINTS - sum(scaled.values())
        for key in sorted(exact, key=lambda k: exact[k] - scaled[k], reverse=True)[:remainder]:
            scaled[key] += 1
        values = scaled
    return values

for _profile in USER_PROFILES.values():
    if isinstance(_profile, dict):
        _profile["skills"] = migrate_skill_distribution(_profile.get("skills"))
        _profile.setdefault("ability", random.choice(list(ABILITY_CATALOG)))
        _profile.setdefault("skills_locked", True)
try:
    PROFILE_FILE.write_text(json.dumps(USER_PROFILES, ensure_ascii=False, indent=2), encoding="utf-8")
except OSError:
    pass

# Gacha de estilos: loja apenas visual; confirmação de compra não consulta a Loritta.
RARITY_DATA = {
    "Comum": {
        "points": 5,
        "chance": 50,
        "color": 9807270,
        "emoji": "⚪"
    },
    "Incomum": {
        "points": 8,
        "chance": 28,
        "color": 3066993,
        "emoji": "🟢"
    },
    "Raro": {
        "points": 11,
        "chance": 15,
        "color": 3447003,
        "emoji": "🔵"
    },
    "Épico": {
        "points": 15,
        "chance": 5,
        "color": 10181046,
        "emoji": "🟣"
    },
    "Lendário": {
        "points": 20,
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
    """Troca estilo ativo e cargos. O inventário mantém apenas um estilo equipado/possuído."""
    role, warning = await sync_pilot_role(guild, member, style.get("name"))
    profile["equipped_style"] = style["name"]
    profile["style_collection"] = [dict(style)]
    save_profiles()
    return role, warning

def gacha_profile(user_id: int):
    profile = USER_PROFILES.setdefault(str(user_id), {
        "name": "", "age": None, "team": "", "photo_url": "",
        "skills": dict(PROFILE_PRESETS["balanced"]["skills"]),
        "spins": 0, "style_collection": [], "equipped_style": None,
        "skip_roll_gamepass": False, "skip_roll_active": False,
        "skills_locked": False, "ability": random.choice(list(ABILITY_CATALOG)),
    })
    profile.setdefault("age", None); profile.setdefault("team", ""); profile.setdefault("photo_url", "")
    profile.setdefault("spins", 0); profile.setdefault("style_collection", [])
    profile.setdefault("equipped_style", None); profile.setdefault("skip_roll_gamepass", False)
    profile.setdefault("skip_roll_active", False)
    profile["skills"] = migrate_skill_distribution(profile.get("skills"))
    profile.setdefault("ability", random.choice(list(ABILITY_CATALOG)))
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
    PROFILE_FILE.write_text(json.dumps(USER_PROFILES, ensure_ascii=False, indent=2), encoding="utf-8")

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
    embed.set_footer(text="Distribua exatamente 10 pontos, escolha pneus e marque Estou pronto.")
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
            style = next((s for s in profile.get("style_collection", []) if s.get("name") == equipped), None)
            bonuses = (style or {}).get("skills", {})
            driver = Driver(
                user=interaction.user, race_name=profile.get("name") or interaction.user.display_name,
                tyre_management=int(saved_skills.get("tyre_management", 0)),
                curves=int(saved_skills.get("curves", 0)), speed=int(saved_skills.get("speed", 0)),
                qualifying=int(saved_skills.get("qualifying", 0)), engine=int(saved_skills.get("engine", 0)),
                control=int(saved_skills.get("control", 0)),
                straights=int(saved_skills.get("speed", 0)), braking=int(saved_skills.get("qualifying", 0)),
                acceleration=int(saved_skills.get("engine", 0)), ability=profile.get("ability"),
                style_name=equipped, style_curves=int(bonuses.get("curves",0)),
                style_straights=int(bonuses.get("straights",0)), style_braking=int(bonuses.get("braking",0)),
                style_acceleration=int(bonuses.get("acceleration",0)), style_control=int(bonuses.get("control",0)),
            )
            self.race.drivers[interaction.user.id] = driver
        await interaction.response.edit_message(embed=lobby_embed(self.race), view=self)

    @discord.ui.button(label="Configurar carro", emoji="⚙️", style=discord.ButtonStyle.primary, row=0)
    async def configure(self, interaction, button):
        if not self.active(interaction) or interaction.user.id not in self.race.drivers:
            return await interaction.response.send_message("Entre no lobby antes.", ephemeral=True)
        profile = gacha_profile(interaction.user.id)
        if profile.get("skills_locked"):
            return await interaction.response.send_message("Seus atributos já foram definidos e estão bloqueados.", ephemeral=True)
        modal = ProfileSkillsModal(interaction.user.id)
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
    """Botões públicos compartilhados. O embed não mostra a escolha individual até todos decidirem."""
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race

    async def record_choice(self, interaction, mode, attack=False, boost=False):
        race = race_for_channel(interaction.channel_id)
        driver = race.drivers.get(interaction.user.id) if race else None
        if race is not self.race or not race.race_started or driver is None or driver.finished:
            return await interaction.response.send_message("Você não é um piloto ativo nesta corrida.", ephemeral=True)
        async with race.decision_lock:
            if driver.chosen_action is not None:
                return await interaction.response.send_message("Você já confirmou sua decisão neste trecho.", ephemeral=True)
            decision: DecisionAction = {"mode": mode, "attack": attack, "boost": boost}
            driver.chosen_action = decision
            # A resposta é pública, mas só informa o status. O botão escolhido não é revelado.
            active = [d for d in race.drivers.values() if not d.finished and not d.retired]
            embed = decision_status_embed(race, active, race.current_decision_label, [])
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Normal", emoji="⚖️", style=discord.ButtonStyle.secondary, row=0)
    async def normal(self, interaction, button):
        await self.record_choice(interaction, "normal")

    @discord.ui.button(label="Agressivo", emoji="🔥", style=discord.ButtonStyle.danger, row=0)
    async def aggressive(self, interaction, button):
        await self.record_choice(interaction, "aggressive")

    @discord.ui.button(label="Defensivo", emoji="🛡️", style=discord.ButtonStyle.primary, row=0)
    async def defensive(self, interaction, button):
        await self.record_choice(interaction, "defensive")

    @discord.ui.button(label="Seguro", emoji="🟢", style=discord.ButtonStyle.success, row=0)
    async def safe(self, interaction, button):
        await self.record_choice(interaction, "safe")

    @discord.ui.button(label="Overtake Mode", emoji="↗️", style=discord.ButtonStyle.primary, row=1)
    async def overtake(self, interaction, button):
        await self.record_choice(interaction, "aggressive", attack=True)

    @discord.ui.button(label="Boost Mode", emoji="⚡", style=discord.ButtonStyle.secondary, row=1)
    async def boost(self, interaction, button):
        await self.record_choice(interaction, "normal", boost=True)


def segment_base_time(segment, circuit):
    base_lap = circuit["base_lap"]
    if segment == "reta":
        return base_lap * 0.22
    return base_lap * 0.28


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

    # Energia de jogo substitui um uso simplificado da gestão elétrica:
    # Boost consome energia e dá bônus, Overtake Mode consome energia quando elegível.
    energy_adjustment = 0.0
    event = ""

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
    time = base - skill_bonus - (tire_condition * 0.12) + tire_loss + weather_loss + mode_adjustment + energy_adjustment + random_error + base * damage_penalty

    curve_intensity = 1.0 if segment == "curva" else 0.35
    risk = 0.045 + mode["risk"] + rain * (0.16 if segment == "curva" else 0.08)
    risk += (driver.tire_wear / 100) * 0.20 + (driver.car_damage / 100) * 0.12
    risk += curve_intensity * max(0, 5 - driver.effective_skill("curves")) * 0.012
    risk += curve_intensity * max(0, 5 - driver.effective_skill("control")) * 0.014
    if driver.ability == "Mãos de Cirurgião":
        risk -= 0.008
    if driver.ability == "Sangue Frio" and action["mode"] == "aggressive":
        risk -= 0.006
    risk += max(0, -mode["pace"]) * 0.30  # agressividade/ação rápida
    risk = max(0.008, min(0.52, risk))

    if driver.ability == "Mãos de Cirurgião":
        risk = max(0.005, risk - 0.008)
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
    return sorted(race.drivers.values(), key=lambda d: d.total_time)


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
    if events:
        embed.add_field(name="Eventos do trecho", value="\n".join(events[:10]), inline=False)
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
EVENT_IMAGE_RULES = {
    "ultrapassagem": ("ultrapassagem.png", "↗️"),
    "acidente": ("colisao.png", "💥"),
    "derrapagem": ("rodada.png", "🌀"),
    "ESTOURO DE PNEU": ("pneu.png", "🛞"),
    "Abandono": ("abandono.png", "⛔"),
    "Safety Car": ("safety_car.png", "🚨"),
    "bandeira vermelha": ("bandeira_vermelha.png", "🟥"),
    "volta mais rápida": ("volta_rapida.png", "⏱️"),
}

async def publish_important_event(race, message):
    lower = message.lower()
    for keyword, (filename, emoji) in EVENT_IMAGE_RULES.items():
        if keyword.lower() in lower:
            asset = EVENT_ASSET_DIR / filename
            if asset.exists():
                try:
                    file = discord.File(asset, filename=filename)
                    embed = discord.Embed(description=message, color=discord.Color.orange())
                    embed.set_image(url=f"attachment://{filename}")
                    await race.channel.send(content=emoji, embed=embed, file=file)
                except discord.HTTPException:
                    pass
            return

async def run_race(race):
    race.race_started = True
    # Ordem de grid de qualificação; tempo acumulado inicial usa o qualifying como
    # separação mínima de grid, não como tempo cronometrado de corrida.
    grid = sorted(race.drivers.values(), key=lambda d: d.grid_position or 99)
    for rank, driver in enumerate(grid):
        driver.total_time = rank * 0.25
        driver.distance = float(rank)

    circuit = CIRCUITS[race.circuit_name]
    for lap in range(1, race.total_laps + 1):
        race.current_lap = lap
        lap_start_times = {d.user.id: d.total_time for d in race.drivers.values()}
        lap_events = []
        for segment_index, segment in enumerate(circuit["segments"], 1):
            race.current_segment = segment_index
            active = [d for d in race.drivers.values() if not d.finished and not d.retired]
            if not active:
                break
            for d in active:
                d.chosen_action = None

            segment_title = f"{segment.upper()} {segment_index}/{SEGMENTS_PER_LAP}"
            race.current_decision_label = f"Volta {lap}/{race.total_laps} • {segment_title}"
            race.decision_seconds = race.decision_seconds or 45
            await update_race_panel(race, active, segment_title, lap_events, show_decision=True)

            deadline = asyncio.get_running_loop().time() + race.decision_seconds
            while any(d.chosen_action is None for d in active) and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(1)

            # Após todos confirmarem ou o prazo acabar, revela as escolhas e desativa os botões.
            if race.message:
                reveal_embed = reveal_decisions_embed(race, active, segment_title, lap_events)
                await race.message.edit(embed=reveal_embed, view=ClosedView())
            # Snapshot do ranking antes do trecho para detectar o carro à frente.
            pre_order = sorted(active, key=lambda d: d.total_time)
            gaps = {}
            for idx, driver in enumerate(pre_order):
                if idx == 0:
                    gaps[driver.user.id] = None
                else:
                    gaps[driver.user.id] = driver.total_time - pre_order[idx-1].total_time

            # Resolver por ranking pre trecho: decisão dos pilotos é simultânea,
            # mas o carro imediatamente à frente é identificado no ponto de detecção.
            for driver in active:
                action: DecisionAction = driver.chosen_action or {"mode": "safe", "attack": False, "boost": False}
                index = pre_order.index(driver)
                opponent = pre_order[index-1] if index > 0 else None
                gap = gaps[driver.user.id]
                segment_time, event = calculate_segment_time(driver, race, segment, action, gap, opponent)
                driver.total_time += segment_time
                driver.distance += 1.0
                if event:
                    event_message = f"{driver_display_name(driver)}: {event}"
                    lap_events.append(event_message)
                    await publish_important_event(race, event_message)

            # Resolver oportunidade de ultrapassagem, sem garantia automática:
            # se acionou ataque, está na janela de distância e o delta do segmento favoreceu,
            # inverter temporariamente o pequeno gap via bônus de tempo probabilístico.
            updated = sorted(active, key=lambda d: d.total_time)
            for idx in range(1, len(updated)):
                driver = updated[idx]
                ahead = updated[idx-1]
                action = driver.chosen_action or {}
                prior_gap = gaps.get(driver.user.id)
                if action.get("attack") and prior_gap is not None and prior_gap <= OVERTAKE_DETECTION_SECONDS:
                    mode = DRIVING_MODES[action.get("mode", "normal")]
                    chance = 0.22 + driver.effective_skill("straights") * 0.025 + driver.effective_skill("acceleration") * 0.018 + driver.effective_skill("control") * 0.008
                    if driver.ability in ("Ultrapassador Nato", "Especialista em DRS"):
                        chance += 0.035
                    chance += mode["attack"]
                    chance -= ahead.control * 0.012
                    if ahead.ability == "Defensor Nato":
                        chance -= 0.035
                    chance = max(0.08, min(0.68, chance))
                    if random.random() < chance and driver.total_time > ahead.total_time:
                        # Overtake representa uma vantagem marginal no tempo do segmento,
                        # nunca uma posição concedida de forma garantida.
                        driver.total_time -= min(0.35, driver.total_time - ahead.total_time + 0.02)
                        overtake_event = f"↗️ {driver_display_name(driver)} completou uma ultrapassagem!"
                        lap_events.append(overtake_event)
                        await publish_important_event(race, overtake_event)
                    else:
                        lap_events.append(f"🚥 {driver_display_name(driver)} tentou ultrapassar, mas não conseguiu.")

            # Avançar classificação, atualização publicada por segmento.
            embed = standings_embed(race, lap, segment_title, lap_events)
            if race.message:
                await race.message.edit(embed=embed, view=ClosedView())

        # Final da volta: contabilizar volta e checar chegada ao fim da volta 10.
        for driver in race.drivers.values():
            if not driver.finished:
                driver.last_lap_time = driver.total_time - lap_start_times.get(driver.user.id, driver.total_time)
                if lap == race.total_laps:
                    driver.finished = True
        await asyncio.sleep(0.5)

    final_order = current_order(race)
    fastest = min((d for d in final_order if d.last_lap_time > 0 and not d.retired), key=lambda d: d.last_lap_time, default=None)
    if fastest:
        await publish_important_event(race, f"⏱️ Volta mais rápida: {driver_display_name(fastest)} — {format_time(fastest.last_lap_time)}")
    await register_championship_result(race, final_order, fastest)
    podium = "\n".join(
        f"**P{position} — {driver_display_name(driver)}** | Tempo acumulado: `{format_time(driver.total_time)}` | "
        f"Pneu: {TIRES[driver.tire]['label']} | desgaste {driver.tire_wear:.0f}%"
        for position, driver in enumerate(final_order, 1)
    )
    embed = discord.Embed(title="🏆 FIM DE CORRIDA — RESULTADO FINAL", description=podium, color=discord.Color.gold())
    embed.set_footer(text=f"{race.circuit_name} • {race.total_laps} voltas • corrida concluída")
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
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse inventário não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id); collection=profile["style_collection"]
        if not collection: return await interaction.response.send_message("Inventário sem estilos.",ephemeral=True)
        opts=[]
        seen=set()
        for style in collection:
            if style["name"] not in seen: opts.append(discord.SelectOption(label=style["name"],description=style["rarity"],value=style["name"]));seen.add(style["name"])
        select=discord.ui.Select(placeholder="Selecione um estilo para equipar",options=opts[:25])
        async def cb(inter):
            if inter.user.id!=self.owner_id: return await inter.response.send_message("Esse seletor não é seu.",ephemeral=True)
            chosen=next(s for s in profile["style_collection"] if s["name"]==select.values[0])
            role, warning = await equip_style_consistently(inter.guild, inter.user, profile, chosen)
            note = f"Estilo equipado: **{chosen['name']}** {role.mention if role else '(cargo sem ID configurado)'}."
            if warning: note += f"\n⚠️ {warning}"
            await inter.response.send_message(note, ephemeral=True)
        select.callback=cb; view=discord.ui.View(timeout=120);view.add_item(select)
        await interaction.response.send_message("Escolha o estilo:",view=view,ephemeral=True)


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
    def __init__(self, owner_id):
        super().__init__(); self.owner_id = owner_id; self.source_message_id = None
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
        await interaction.response.send_message("✅ Distribuição pessoal salva.", ephemeral=True)
        await refresh_profile_message(interaction, self.source_message_id, profile)

class ProfileView(discord.ui.View):
    def __init__(self,owner_id): super().__init__(timeout=180);self.owner_id=owner_id
    @discord.ui.button(label="Configurar",emoji="⚙️",style=discord.ButtonStyle.primary,row=0)
    async def configure(self,interaction,button):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse botão não é seu.",ephemeral=True)
        modal=ProfileNameModal(self.owner_id, interaction.message.id); await interaction.response.send_modal(modal)
    @discord.ui.button(label="Distribuir pontos", emoji="📊", style=discord.ButtonStyle.secondary, row=0)
    async def distribute(self, interaction, button):
        if interaction.user.id != self.owner_id: return await interaction.response.send_message("Esse botão não é seu.", ephemeral=True)
        profile = gacha_profile(self.owner_id)
        if profile.get("skills_locked"):
            return await interaction.response.send_message("Seus atributos já foram definidos e não podem ser alterados.", ephemeral=True)
        modal=ProfileSkillsModal(self.owner_id); modal.source_message_id=interaction.message.id; await interaction.response.send_modal(modal)
    @discord.ui.button(label="Inventário",emoji="🎒",style=discord.ButtonStyle.secondary,row=0)
    async def inventory(self,interaction,button):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Esse botão não é seu.",ephemeral=True)
        profile=gacha_profile(self.owner_id); equipped=profile.get("equipped_style") or "Nenhum"
        gp="Sim" if profile.get("skip_roll_gamepass") else "Não"
        active="Ativa" if profile.get("skip_roll_gamepass") and profile.get("skip_roll_active") else "Desativada"
        lines=[f"**Giros:** {profile['spins']}",f"**Estilo equipado:** {equipped}",f"**Gamepass Pular Giro:** {gp} • {active}","**Estilos possuídos:**"]
        lines += [f"{RARITY_DATA[s['rarity']]['emoji']} {s['name']} — {s['rarity']}" for s in profile['style_collection']]
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
        self.add_item(discord.ui.Button(label="Gamepass: Pular Giro (liberação manual)",emoji="⏭️",style=discord.ButtonStyle.secondary,disabled=True))

@bot.command(name="roll-estilo")
async def roll_style_command(ctx):
    profile=gacha_profile(ctx.author.id)
    embed=discord.Embed(title="🎰 Gacha de estilos da F1",description=(f"**Giros disponíveis: {profile['spins']}**\nClique para girar. O estilo só entra no inventário após Aceitar.\n\n"+"\n".join(f"{RARITY_DATA[r]['emoji']} **{r}** — {RARITY_DATA[r]['chance']}% • {RARITY_DATA[r]['points']} pontos" for r in RARITY_DATA)),color=discord.Color.purple())
    await ctx.send(embed=embed,view=GachaRollView(ctx.author.id))

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
    profile=gacha_profile(ctx.author.id)
    embed=discord.Embed(title="🛒 Loja informativa — F1 Discord Racing",description=(f"**Seus giros:** {profile['spins']}\n\n**Pacotes de giros**\n1 giro — 5k sonhos\n5 giros — 25k sonhos\n10 giros — 50k sonhos\n25 giros — 125k sonhos\n\n**Gamepass: Pular Giro**\nPermite pular o loading do roll quando ativada pelo administrador.\n\n⚠️ **Pagamento diretamente com o administrador do servidor.** A loja não aceita pagamentos, não concede giros e não desconta sonhos automaticamente. Após pagamento externo, o administrador libera os itens manualmente."),color=discord.Color.gold())
    await ctx.send(embed=embed,view=ShopView())

@bot.command(name="colecao-estilos")
async def style_collection_command(ctx):
    profile=gacha_profile(ctx.author.id); collection=profile["style_collection"]
    if not collection: return await ctx.send("Sua coleção está vazia. Use `!roll-estilo` para tentar obter um estilo.")
    counts={}
    for style in collection: counts[(style["rarity"],style["name"])]=counts.get((style["rarity"],style["name"]),0)+1
    lines=[f"{RARITY_DATA[r]['emoji']} **{n}** — {r} ×{c}" for (r,n),c in sorted(counts.items(),key=lambda x:(list(RARITY_DATA).index(x[0][0]),x[0][1]))]
    await ctx.send(embed=discord.Embed(title="🏆 Coleção de estilos",description="\n".join(lines),color=discord.Color.blurple()))

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

@bot.tree.command(name="setar_estilo", description="Define diretamente o estilo equipado de um jogador (admin)")
@app_commands.describe(jogador="Pessoa que receberá o estilo", estilo="Nome exato do piloto/estilo")
@app_commands.checks.has_permissions(administrator=True)
async def setar_estilo(interaction: discord.Interaction, jogador: discord.Member, estilo: str):
    chosen = next((item for item in PILOT_STYLES if item["name"].casefold() == estilo.strip().casefold()), None)
    if chosen is None:
        return await interaction.response.send_message("Estilo não encontrado. Use o nome exato de um dos pilotos da coleção.", ephemeral=True)
    profile = gacha_profile(jogador.id)
    role, warning = await equip_style_consistently(interaction.guild, jogador, profile, dict(chosen))
    await send_admin_receipt(interaction.guild, interaction.user, jogador, "Setar estilo", f"Estilo atribuído: {chosen['name']} ({chosen['rarity']})")
    response = f"🏎️ Estilo **{chosen['name']}** setado para {jogador.mention}."
    if role: response += f" Cargo: {role.mention}."
    if warning: response += f"\n⚠️ {warning}"
    await interaction.response.send_message(response, ephemeral=True)

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

@bot.tree.command(name="equipar_estilo",description="Equipa um estilo que você possui")
@app_commands.describe(estilo="Nome exato do estilo no inventário")
async def equipar_estilo(interaction: discord.Interaction,estilo: str):
    profile=gacha_profile(interaction.user.id)
    if not any(s.get("name","").casefold()==estilo.casefold() for s in profile["style_collection"]):
        return await interaction.response.send_message("Você não possui esse estilo.",ephemeral=True)
    found=next(s for s in profile["style_collection"] if s["name"].casefold()==estilo.casefold())
    role, warning = await equip_style_consistently(interaction.guild, interaction.user, profile, found)
    note = f"🏎️ Estilo equipado: **{found['name']}** {role.mention if role else '(cargo ainda sem ID configurado)'}."
    if warning: note += f"\n⚠️ {warning}"
    await interaction.response.send_message(note, ephemeral=True)



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
            "lap_time": driver.last_lap_time,
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
            row = table.setdefault(uid, {"name": result["name"], "points": 0, "wins": 0, "seconds": 0, "thirds": 0, "fastest": 0, "races": 0})
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
    r = next((x for x in rows if x["name"] == (ctx.author.display_name)), rows[0])
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

@bot.command(name="comandos")
async def commands_list(ctx):
    embed = discord.Embed(title="📜 Comandos do F1 Discord Racing", color=discord.Color.blue())
    embed.description = (
        "`!f1` — cria um lobby; o host usa os botões do próprio painel para configurar, classificar e iniciar.\n"
        "`!perfil` — configura nome, idade, equipe, foto, estilo e inventário.\n`!roll-estilo` — roleta gacha de estilos de pilotos F1.\n`!roll-pendente` — recupera resultado aguardando confirmação.\n`!loja` — loja visual de giros (sonhos da Loritta; confirmação manual).\n`!colecao-estilos` — mostra estilos obtidos.\n`/adicionar_giros`, `/deletar_giros`, `/setar_estilo` e `/gamepass` — administração de giros/estilos.\n"
        "`!ajuda` — guia de funcionamento e explicação das estratégias.\n"
        "`!campeonato` / `!ranking` / `!estatisticas` — classificação e dados da temporada.\n"
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
        "**2) Perfil/crachá:** `!perfil` mostra estilo equipado, cargo, dados pessoais e botões Configurar/Inventário.\n**3) Gacha:** `!roll-estilo` permite gastar giros para obter estilos de pilotos. `!loja` mostra pacotes em sonhos; a compra é confirmada manualmente e o bot não desconta sonhos. `!colecao-estilos` lista os estilos recebidos. Os estilos têm raridades e pontos extras próprios. Nome aparece na corrida; equipe e pneu favorito são visuais, sem impacto na simulação. Perfil salvo é carregado no próximo lobby; os pontos ainda podem ser ajustados.\n"
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
        "• Erros e derrapagens são eventos probabilísticos; Controle, Frenagem, modo escolhido, chuva e desgaste influenciam o risco.\n\n"
        "**Botões de gestão:** Configurar corrida permite ao host escolher voltas, circuito, clima e prazo de decisão. Iniciar classificação e Iniciar corrida avançam o fluxo sem comandos separados."
    )
    embed.set_footer(text="As mecânicas são uma simulação simplificada e não reproduzem integralmente as regras oficiais da F1.")
    await ctx.send(embed=embed)


def build_profile_embed(profile, member, guild):
    equipped=profile.get("equipped_style")
    style=next((s for s in profile["style_collection"] if s["name"]==equipped),None)
    role_id=PILOT_ROLE_IDS.get(equipped) if equipped else None
    role=guild.get_role(role_id) if guild and role_id else None
    style_label=role.mention if role else (f"**{equipped}** (cargo não configurado)" if equipped else "Nenhum estilo equipado")
    desc=(f"**🏷️ Piloto:** {profile.get('name') or member.display_name}\n"
          f"**🎂 Idade:** {profile.get('age') or 'Não definida'}\n**🏢 Equipe:** {profile.get('team') or 'Não definida'}\n"
          f"**🏎️ Estilo equipado:** {style_label}\n")
    personal=profile.get("skills", dict(PROFILE_PRESETS["balanced"]["skills"]))
    bonuses=style.get("skills", {}) if style else {}
    desc += "\n**📊 Atributos pessoais (10 pontos)**\n"
    desc += " • ".join(f"{label}: {personal.get(key,0)}" for key,label,emoji in SKILL_FIELDS)
    desc += f"\n\n**✨ Habilidade especial:** {profile.get('ability') or 'Não definida'}\n_{ABILITY_CATALOG.get(profile.get('ability'), 'Habilidade passiva sorteada uma única vez.')}_"
    desc += "\n\n**🏆 Bônus do estilo**\n"
    style_values = {key: int(bonuses.get(source, 0)) if source else 0 for key, source in STYLE_SKILL_MAP.items()}
    desc += " • ".join(f"{label}: +{style_values.get(key,0)}" for key,label,emoji in SKILL_FIELDS) if style else "Nenhum estilo equipado."
    desc += "\n\n**⚙️ Atributos finais (pessoal + estilo)**\n"
    desc += " • ".join(f"{label}: {int(personal.get(key,0))+style_values.get(key,0)}" for key,label,emoji in SKILL_FIELDS)
    embed=discord.Embed(title="🏎️ Perfil do piloto",description=desc,color=discord.Color.orange())
    if profile.get("photo_url"): embed.set_image(url=profile["photo_url"])
    return embed

async def refresh_profile_message(interaction, message_id, profile):
    if not message_id or not interaction.channel or not interaction.guild:
        return
    try:
        message=await interaction.channel.fetch_message(message_id)
        await message.edit(embed=build_profile_embed(profile, interaction.user, interaction.guild), view=ProfileView(interaction.user.id))
    except discord.HTTPException:
        pass

@bot.command(name="perfil")
async def profile_command(ctx):
    profile=gacha_profile(ctx.author.id)
    await ctx.send(embed=build_profile_embed(profile, ctx.author, ctx.guild), view=ProfileView(ctx.author.id))

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
        _persistent_gacha_views_registered = True
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")
    except Exception as exc:
        print(f"Falha ao sincronizar slash commands: {exc}")
    print("Comandos: !f1, !perfil, !roll-estilo, !loja, !comandos, !ajuda, !f1status, !f1cancel")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Erro em comando {ctx.command}: {error}")
    await ctx.send("⚠️ Erro ao executar comando. Confira o terminal.")


if not TOKEN:
    raise RuntimeError("Defina DISCORD_TOKEN no arquivo .env")

bot.run(TOKEN)
