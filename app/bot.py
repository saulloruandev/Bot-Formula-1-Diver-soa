import os
import json
import random
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, List, TypedDict
from pathlib import Path
from types import SimpleNamespace
from io import BytesIO

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

MIN_PLAYERS = 2
MAX_PLAYERS = 10
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

# Calendário expandido: 15 circuitos disponíveis no sorteio e na configuração do lobby.
CIRCUITS.update({
    "Bahrain": {"base_lap": 94.0, "corners": 0.24, "straights": 0.31, "braking": 0.22, "acceleration": 0.15, "control": 0.08, "segments": ["reta", "curva", "reta", "curva", "reta", "curva"]},
    "Jeddah": {"base_lap": 90.0, "corners": 0.20, "straights": 0.38, "braking": 0.15, "acceleration": 0.17, "control": 0.10, "segments": ["reta", "curva", "reta", "reta", "curva", "reta"]},
    "Melbourne": {"base_lap": 80.0, "corners": 0.30, "straights": 0.25, "braking": 0.17, "acceleration": 0.16, "control": 0.12, "segments": ["curva", "reta", "curva", "reta", "curva", "reta"]},
    "Suzuka": {"base_lap": 91.0, "corners": 0.39, "straights": 0.19, "braking": 0.14, "acceleration": 0.15, "control": 0.13, "segments": ["curva", "curva", "curva", "reta", "curva", "reta"]},
    "Shanghai": {"base_lap": 96.0, "corners": 0.28, "straights": 0.30, "braking": 0.18, "acceleration": 0.14, "control": 0.10, "segments": ["curva", "curva", "reta", "curva", "reta", "reta"]},
    "Miami": {"base_lap": 91.0, "corners": 0.25, "straights": 0.33, "braking": 0.18, "acceleration": 0.14, "control": 0.10, "segments": ["reta", "curva", "reta", "curva", "reta", "curva"]},
    "Monaco": {"base_lap": 74.0, "corners": 0.48, "straights": 0.10, "braking": 0.14, "acceleration": 0.12, "control": 0.20, "segments": ["curva", "curva", "curva", "curva", "reta", "curva"]},
    "Spa-Francorchamps": {"base_lap": 106.0, "corners": 0.31, "straights": 0.29, "braking": 0.15, "acceleration": 0.15, "control": 0.14, "segments": ["reta", "curva", "curva", "reta", "curva", "reta"]},
    "Zandvoort": {"base_lap": 73.0, "corners": 0.42, "straights": 0.14, "braking": 0.16, "acceleration": 0.12, "control": 0.20, "segments": ["curva", "curva", "curva", "reta", "curva", "curva"]},
    "Barcelona": {"base_lap": 91.0, "corners": 0.32, "straights": 0.25, "braking": 0.17, "acceleration": 0.14, "control": 0.16, "segments": ["reta", "curva", "curva", "reta", "curva", "reta"]},
    "Red Bull Ring": {"base_lap": 66.0, "corners": 0.20, "straights": 0.37, "braking": 0.20, "acceleration": 0.15, "control": 0.12, "segments": ["reta", "curva", "reta", "curva", "reta", "curva"]},
    "Yas Marina": {"base_lap": 88.0, "corners": 0.27, "straights": 0.31, "braking": 0.18, "acceleration": 0.14, "control": 0.14, "segments": ["reta", "curva", "reta", "curva", "reta", "curva"]},
})

CIRCUIT_IMAGE_SLUGS = {
    "Interlagos": "interlagos",
    "Monza": "monza",
    "Silverstone": "silverstone",
    "Bahrain": "bahrain",
    "Jeddah": "jeddah",
    "Melbourne": "melbourne",
    "Suzuka": "suzuka",
    "Shanghai": "shanghai",
    "Miami": "miami",
    "Monaco": "monaco",
    "Spa-Francorchamps": "spa-francorchamps",
    "Zandvoort": "zandvoort",
    "Barcelona": "barcelona",
    "Red Bull Ring": "red-bull-ring",
    "Yas Marina": "yas-marina"
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
    pit_repair: bool


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
    best_lap_number: Optional[int] = None
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
    tire_warning_lap: int = 0
    tire_changes_remaining: int = 1
    is_bot: bool = False
    overtakes_made: int = 0
    incidents: int = 0
    spins: int = 0
    severe_accidents: int = 0
    lap_times: List[float] = field(default_factory=list)

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
    pending_broadcasts: List[str] = field(default_factory=list)
    race_id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))
    mode: str = "casual"
    max_players: int = 10
    lobby_timeout_task: Optional[asyncio.Task] = None
    bot_counter: int = 0

    @property
    def full(self):
        return len(self.drivers) >= self.max_players

    @property
    def all_ready(self):
        return len(self.drivers) >= MIN_PLAYERS and all(d.ready for d in self.drivers.values())


races: Dict[str, Race] = {}

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
        if "ability_collection" in profile:
            profile.pop("ability_collection", None)
            changed = True
        equipped_name = profile.get("equipped_style")
        legacy_collection = profile.get("style_collection", [])
        if not equipped_name and isinstance(legacy_collection, list) and legacy_collection:
            equipped_name = next((item.get("name") for item in legacy_collection if isinstance(item, dict) and item.get("name")), None)
            if equipped_name:
                profile["equipped_style"] = equipped_name
                changed = True
        current = styles_by_name.get(str(equipped_name or "").casefold())
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
    if not target_id:
        return None, f"Não existe ID configurado em PILOT_ROLE_IDS para {style_name}."
    target_role = guild.get_role(int(target_id))
    if target_role is None:
        return None, f"O ID configurado para {style_name} ({target_id}) não corresponde a nenhum cargo deste servidor. Confira o ID em PILOT_ROLE_IDS."
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
    profile.pop("ability_collection", None)
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


def races_for_channel(channel_id: int):
    return [race for race in races.values() if race.channel_id == channel_id]

def race_for_channel(channel_id: int, mode=None, host_id=None):
    matches = races_for_channel(channel_id)
    if mode is not None:
        matches = [race for race in matches if race.mode == mode]
    if host_id is not None:
        matches = [race for race in matches if race.host_id == host_id]
    return matches[-1] if matches else None

def race_is_active(race: Race):
    return races.get(race.race_id) is race


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


CIRCUIT_MAP_POINTS = {
    "Interlagos": [(120,260),(95,210),(210,110),(330,95),(390,145),(330,205),(420,245),(560,220),(660,260),(610,320),(450,310),(390,275),(300,335),(190,320)],
    "Monza": [(150,100),(650,100),(680,155),(640,210),(560,200),(520,250),(640,300),(670,350),(500,350),(430,300),(320,315),(250,260),(170,280),(130,220),(190,180)],
    "Silverstone": [(160,110),(330,85),(410,130),(570,110),(670,180),(610,250),(680,310),(520,340),(410,290),(300,330),(190,270),(120,200)],
    "Bahrain": [(150,120),(270,90),(360,140),(500,105),(650,150),(620,240),(690,300),(550,340),(430,300),(330,345),(180,300),(120,220)],
    "Jeddah": [(130,100),(250,80),(310,135),(440,95),(500,145),(640,110),(680,190),(600,220),(690,280),(590,330),(470,285),(350,340),(260,285),(140,310),(100,220)],
    "Melbourne": [(180,90),(340,95),(430,130),(570,105),(660,180),(620,270),(500,315),(380,290),(300,345),(180,290),(120,200)],
    "Suzuka": [(120,160),(170,70),(300,75),(350,150),(400,230),(520,235),(590,160),(670,75),(720,170),(650,245),(590,315),(470,300),(400,240),(320,170),(230,220),(170,320),(110,280)],
    "Shanghai": [(150,100),(300,80),(420,130),(560,100),(660,190),(590,250),(680,320),(500,345),(400,290),(300,340),(170,280),(120,190)],
    "Miami": [(120,120),(280,90),(360,130),(520,90),(660,150),(630,240),(680,300),(520,335),(420,280),(300,330),(180,270),(100,210)],
    "Monaco": [(150,120),(270,100),(350,140),(470,120),(560,170),(530,220),(640,240),(610,300),(480,285),(410,330),(300,290),(230,330),(140,270),(190,210)],
    "Spa-Francorchamps": [(130,300),(100,220),(170,120),(280,85),(380,135),(500,95),(660,145),(620,230),(540,280),(430,250),(360,320),(230,340)],
    "Zandvoort": [(170,110),(270,55),(400,90),(430,160),(470,230),(590,210),(650,160),(710,230),(640,320),(540,330),(390,300),(300,345),(190,280),(120,200)],
    "Barcelona": [(140,110),(300,100),(380,145),(550,110),(660,180),(620,250),(680,315),(520,340),(430,285),(300,325),(180,280),(110,210)],
    "Red Bull Ring": [(150,310),(220,100),(350,140),(480,85),(660,150),(610,290),(470,330),(370,260),(250,340)],
    "Yas Marina": [(140,100),(280,85),(360,130),(500,100),(650,150),(620,220),(560,250),(650,310),(510,340),(390,290),(300,330),(170,280),(110,200)],
}


def build_circuit_preview_file(race):
    """Gera a prévia PNG do circuito para o Discord usando Pillow."""
    width, height = 800, 420
    image = Image.new("RGB", (width, height), (16, 27, 43))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        title_font = small_font = ImageFont.load_default()
    points = CIRCUIT_MAP_POINTS.get(race.circuit_name, CIRCUIT_MAP_POINTS["Interlagos"])
    path = [(int(x * 0.92 + 32), int(y * 0.88 + 20)) for x, y in points]
    path.append(path[0])
    draw.text((32, 20), race.circuit_name.upper(), font=title_font, fill=(245, 248, 255))
    draw.text((768, 28), "PRÉVIA ESQUEMÁTICA", font=small_font, fill=(143, 167, 189), anchor="ra")
    draw.line(path, fill=(3, 7, 12), width=44, joint="curve")
    draw.line(path, fill=(35, 194, 231), width=8, joint="curve")
    sx, sy = path[0]
    dx, dy = path[len(path) // 3]
    draw.ellipse((sx-10, sy-10, sx+10, sy+10), fill=(242, 11, 216), outline=(255,255,255), width=2)
    draw.ellipse((dx-8, dy-8, dx+8, dy+8), fill=(19, 201, 74), outline=(255,255,255), width=2)
    draw.text((32, 386), "Mapa ilustrativo • sem escala oficial", font=small_font, fill=(143, 167, 189))
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return discord.File(output, filename="circuit-preview.png")


def lobby_embed(race: Race, title=None, description=None):
    circuit = CIRCUITS[race.circuit_name]
    embed = discord.Embed(
        title=title or ("🏆 F1 Rank — Lobby oficial" if race.mode == "ranked" else "🏁 F1 Casual — Lobby"),
        description=description or (
            f"**{race.circuit_name}** • {race.total_laps} voltas\n"
            + ("Corrida oficial da temporada." if race.mode == "ranked" else "Corrida casual — não altera o campeonato.")
        ),
        color=discord.Color.gold() if race.mode == "ranked" else discord.Color.red(),
    )
    embed.add_field(
        name="🌦️ Condições",
        value=f"**Clima:** {race.weather_name}\n**Ambiente:** {race.ambient_temp}°C\n**Pista:** {race.track_temp}°C ({race.surface})",
        inline=True,
    )
    ready_count = sum(1 for driver in race.drivers.values() if driver.ready and not getattr(driver, "is_bot", False))
    embed.add_field(name="👥 Lobby", value=f"**Pilotos:** {len(race.drivers)}/{race.max_players}\n**Prontos:** {ready_count}\n**Mínimo:** {MIN_PLAYERS}", inline=True)
    if race.drivers:
        # Um field por piloto evita ultrapassar o limite de 1.024 caracteres
        # quando o lobby recebe vários jogadores, nomes longos ou estilos.
        for pos, driver in enumerate(race.drivers.values(), 1):
            tire_label = TIRES[driver.tire]["label"] if driver.tire else "Não escolhido"
            badge_bits = []
            if driver.team_name:
                badge_bits.append(f"🏢 {driver.team_name}")
            if driver.style_name:
                badge_bits.append(f"🎴 {driver.style_name}")
            if driver.favorite_tire:
                badge_bits.append(f"⭐ Favorito: {TIRES.get(driver.favorite_tire, {}).get('label', driver.favorite_tire)}")
            badge_line = ("\n└ " + " • ".join(badge_bits)) if badge_bits else ""
            driver_line = (
                f"{driver.user.mention} (**{driver_display_name(driver)}**) — {driver.lobby_status}\n"
                f"└ Pneus da corrida: {tire_label} • Pontos: {driver.total_skills}/{SKILL_POINTS}"
                f"{badge_line}"
            )
            # O conteúdo individual é limitado preventivamente, mesmo se o
            # jogador usar um nome de perfil muito comprido.
            if len(driver_line) > 450:
                driver_line = driver_line[:447] + "..."
            embed.add_field(
                name=f"🏎️ P{pos} — {driver_display_name(driver)[:220]}",
                value=driver_line or "Piloto inscrito.",
                inline=False,
            )
    else:
        embed.add_field(name="🏎️ Pilotos", value="Ninguém entrou ainda.", inline=False)
    embed.set_image(url="attachment://circuit-preview.png")
    embed.set_footer(text=f"{'Oficial • pontua na temporada' if race.mode == 'ranked' else 'Casual • ranking normal'} | 15 circuitos • até 10 pilotos • bots opcionais")
    return embed


async def refresh_lobby(race, view=None):
    """Atualiza sempre o embed completo e a view atual do lobby."""
    if not race.message:
        return
    if view is None:
        view = LobbyView(race)
    preview = build_circuit_preview_file(race)
    await race.message.edit(
        embed=lobby_embed(race),
        attachments=[preview],
        view=view,
    )


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
        race = self.race
        if not race_is_active(race) or race.started or self.user_id not in race.drivers:
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
        race = self.race
        if not race_is_active(race) or race.started or self.user_id not in race.drivers:
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


def car_setup_embed(driver, selected_attribute=None):
    embed = discord.Embed(
        title="⚙️ Configuração do carro",
        description=(
            "Escolha um atributo no primeiro menu e defina seus pontos no segundo. "
            "Você pode distribuir até **10 pontos no total**. Os nomes e valores atuais aparecem abaixo."
        ),
        color=discord.Color.blurple(),
    )
    for key, label, emoji in SKILL_FIELDS:
        value = getattr(driver, key)
        selected = " ◀ selecionado" if key == selected_attribute else ""
        embed.add_field(name=f"{emoji} {label}{selected}", value=f"**{value} ponto(s)**", inline=True)
    embed.add_field(
        name="📊 Total distribuído",
        value=f"**{driver.total_skills}/{SKILL_POINTS} pontos**",
        inline=False,
    )
    embed.set_footer(text="Para ficar pronto, distribua exatamente 10 pontos e escolha seus pneus.")
    return embed


class CarAttributeSelect(discord.ui.Select):
    def __init__(self, view):
        self.setup_view = view
        driver = view.race.drivers[view.user_id]
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                emoji=emoji,
                description=f"Atualmente: {getattr(driver, key)} ponto(s)",
            )
            for key, label, emoji in SKILL_FIELDS
        ]
        super().__init__(placeholder="1º — Escolha qual atributo configurar", options=options, row=0)

    async def callback(self, interaction):
        view = self.setup_view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("Essa configuração pertence a outro piloto.", ephemeral=True)
        if interaction.channel_id != view.race.channel_id or not race_is_active(view.race) or view.race.started:
            return await interaction.response.send_message("O lobby não está mais disponível.", ephemeral=True)
        driver = view.race.drivers.get(view.user_id)
        if driver is None:
            return await interaction.response.send_message("Você não está mais inscrito nesta corrida.", ephemeral=True)
        view.selected_attribute = self.values[0]
        view.points_select.refresh_options()
        await interaction.response.edit_message(
            embed=car_setup_embed(driver, view.selected_attribute),
            view=view,
        )


class CarPointsSelect(discord.ui.Select):
    def __init__(self, view):
        self.setup_view = view
        options = [discord.SelectOption(label=f"{value} ponto(s)", value=str(value)) for value in range(SKILL_POINTS + 1)]
        super().__init__(placeholder="2º — Escolha quantos pontos atribuir", options=options, row=1)

    def refresh_options(self):
        view = self.setup_view
        driver = view.race.drivers[view.user_id]
        current = getattr(driver, view.selected_attribute) if view.selected_attribute else None
        self.options = [
            discord.SelectOption(
                label=f"{value} ponto(s)",
                value=str(value),
                default=value == current,
            )
            for value in range(SKILL_POINTS + 1)
        ]

    async def callback(self, interaction):
        view = self.setup_view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("Essa configuração pertence a outro piloto.", ephemeral=True)
        if interaction.channel_id != view.race.channel_id or not race_is_active(view.race) or view.race.started:
            return await interaction.response.send_message("O lobby não está mais disponível.", ephemeral=True)
        if not view.selected_attribute:
            return await interaction.response.send_message("Escolha primeiro o atributo que deseja configurar.", ephemeral=True)

        driver = view.race.drivers.get(view.user_id)
        if driver is None:
            return await interaction.response.send_message("Você não está mais inscrito nesta corrida.", ephemeral=True)
        attribute = view.selected_attribute
        new_value = int(self.values[0])
        old_value = getattr(driver, attribute)
        new_total = driver.total_skills - old_value + new_value
        if new_total > SKILL_POINTS:
            return await interaction.response.send_message(
                f"Você ficaria com {new_total}/{SKILL_POINTS} pontos. Reduza outro atributo antes.",
                ephemeral=True,
            )

        setattr(driver, attribute, new_value)
        if attribute == "speed":
            driver.straights = new_value
        elif attribute == "qualifying":
            driver.braking = new_value
        elif attribute == "engine":
            driver.acceleration = new_value
        driver.ready = False

        profile = gacha_profile(view.user_id)
        profile.setdefault("skills", {})[attribute] = new_value
        save_profiles()

        self.refresh_options()
        await interaction.response.edit_message(
            embed=car_setup_embed(driver, attribute),
            view=view,
        )


class CarSetupView(discord.ui.View):
    def __init__(self, race, user_id):
        super().__init__(timeout=180)
        self.race = race
        self.user_id = user_id
        self.selected_attribute = None
        self.attribute_select = CarAttributeSelect(self)
        self.points_select = CarPointsSelect(self)
        self.add_item(self.attribute_select)
        self.add_item(self.points_select)


class LobbyView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race

    def active(self, interaction):
        return interaction.channel_id == self.race.channel_id and race_is_active(self.race) and not self.race.started

    @discord.ui.button(label="Entrar na corrida", emoji="🏎️", style=discord.ButtonStyle.success, row=0)
    async def join(self, interaction, button):
        if not self.active(interaction):
            return await interaction.response.send_message("Lobby indisponível.", ephemeral=True)
        async with self.race.lock:
            if interaction.user.id in self.race.drivers:
                return await interaction.response.send_message("Você já está inscrito.", ephemeral=True)
            if self.race.full:
                return await interaction.response.send_message(f"Lobby cheio ({self.race.max_players} pilotos).", ephemeral=True)
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
        driver = self.race.drivers[interaction.user.id]
        await interaction.response.send_message(
            embed=car_setup_embed(driver),
            view=CarSetupView(self.race, interaction.user.id),
            ephemeral=True,
        )

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

    @discord.ui.button(label="Adicionar bots", emoji="🤖", style=discord.ButtonStyle.secondary, row=3)
    async def add_bots(self, interaction, button):
        if interaction.user.id != self.race.host_id:
            return await interaction.response.send_message("Somente o criador pode adicionar bots.", ephemeral=True)
        if not self.active(interaction):
            return await interaction.response.send_message("O lobby não está mais disponível.", ephemeral=True)
        await interaction.response.send_modal(AddBotsModal(self.race))

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
        if not self.active(interaction):
            return await interaction.response.send_message("Este lobby não está mais ativo.", ephemeral=True)
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
        skill_delta += 0.32
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


class PitTireSelect(discord.ui.Select):
    def __init__(self, decision_view, user_id):
        self.decision_view = decision_view
        self.user_id = user_id
        options = []
        for key, tire in TIRES.items():
            options.append(discord.SelectOption(
                label=f"{tire['label']} — só pneus",
                value=f"{key}|0",
                description="Troca os pneus e faz a manutenção básica.",
            ))
            options.append(discord.SelectOption(
                label=f"{tire['label']} + reparar asa",
                value=f"{key}|1",
                description="Repara mais 30% do dano; acrescenta 4s ao pit stop.",
            ))
        super().__init__(placeholder="Escolha pneus e serviço do pit stop", options=options, min_values=1, max_values=1)

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Esse menu pertence a outro piloto.", ephemeral=True)
        tire_key, repair_flag = self.values[0].split("|", 1)
        await self.decision_view.record_choice(
            interaction, "normal", pit=True, pit_tire=tire_key, pit_repair=repair_flag == "1"
        )


class PitTireView(discord.ui.View):
    def __init__(self, decision_view, user_id):
        super().__init__(timeout=60)
        self.add_item(PitTireSelect(decision_view, user_id))


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
            if race.safety_car_laps > 0:
                pit_button = discord.ui.Button(label="Pit Stop (Safety Car)", emoji="🛠️", style=discord.ButtonStyle.primary, row=2)
                async def open_sc_pit(interaction):
                    driver = race.drivers.get(interaction.user.id) if race_is_active(race) else None
                    if driver is None or driver.finished or driver.retired:
                        return await interaction.response.send_message("Você não é um piloto ativo nesta corrida.", ephemeral=True)
                    if driver.tire_changes_remaining <= 0:
                        return await interaction.response.send_message("Você já utilizou os 2 jogos de pneus disponíveis (jogo inicial + 1 troca).", ephemeral=True)
                    if driver.last_pit_lap == race.current_lap:
                        return await interaction.response.send_message("Você já fez um pit stop nesta volta.", ephemeral=True)
                    await interaction.response.send_message(
                        f"Safety Car ativo: escolha pneus e se deseja reparar a asa (+4s, até 30% de dano). Dano atual: {driver.car_damage:.0f}%.",
                        view=PitTireView(self, interaction.user.id), ephemeral=True
                    )
                pit_button.callback = open_sc_pit
                self.add_item(pit_button)
        else:
            self.add_action("Manter ritmo", "⚖️", "normal", row=0)
            self.add_action("Defender posição", "🛡️", "defensive", row=0)
            if self.any_driver_in_drs_window():
                self.add_action("DRS / Ultrapassar", "↗️", "normal", attack=True, row=1)
            self.add_action("Boost Mode", "⚡", "normal", boost=True, row=1)
            pit_button = discord.ui.Button(label="Pit Stop", emoji="🛠️", style=discord.ButtonStyle.primary, row=2)
            async def open_pit_menu(interaction):
                driver = race.drivers.get(interaction.user.id) if race_is_active(race) else None
                if driver is None or driver.finished or driver.retired:
                    return await interaction.response.send_message("Você não é um piloto ativo nesta corrida.", ephemeral=True)
                if driver.last_pit_lap == race.current_lap:
                    return await interaction.response.send_message("Você já fez um pit stop nesta volta.", ephemeral=True)
                if driver.tire_changes_remaining <= 0:
                    return await interaction.response.send_message("Você já utilizou os 2 jogos de pneus disponíveis (jogo inicial + 1 troca).", ephemeral=True)
                await interaction.response.send_message(
                    (f"Safety Car ativo: pit stop com perda reduzida. Escolha pneus e se deseja reparar a asa (+4s, até 30% de dano). Dano atual: {driver.car_damage:.0f}%."
                     if race.safety_car_laps > 0 else
                     f"Escolha pneus e se deseja reparar a asa (+4s, até 30% de dano). Dano atual: {driver.car_damage:.0f}%."),
                    view=PitTireView(self, interaction.user.id), ephemeral=True
                )
            pit_button.callback = open_pit_menu
            self.add_item(pit_button)

    def any_driver_in_drs_window(self):
        active = sorted([d for d in self.race.drivers.values() if not d.finished and not d.retired], key=lambda d: d.total_time)
        return any(active[i].total_time - active[i-1].total_time <= OVERTAKE_DETECTION_SECONDS for i in range(1, len(active)))

    def add_action(self, label, emoji, mode, attack=False, boost=False, line=None, pit=False, pit_tire=None, row=0):
        button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary if attack or pit else discord.ButtonStyle.secondary, row=row)
        async def callback(interaction):
            await self.record_choice(interaction, mode, attack=attack, boost=boost, line=line, pit=pit, pit_tire=pit_tire)
        button.callback = callback
        self.add_item(button)

    async def record_choice(self, interaction, mode, attack=False, boost=False, line=None, pit=False, pit_tire=None, pit_repair=False):
        race = self.race
        driver = race.drivers.get(interaction.user.id) if race_is_active(race) else None
        if interaction.channel_id != race.channel_id or not race.race_started or driver is None or driver.finished or driver.retired:
            return await interaction.response.send_message("Você não é um piloto ativo nesta corrida.", ephemeral=True)
        active = sorted([d for d in race.drivers.values() if not d.finished and not d.retired], key=lambda d: d.total_time)
        index = active.index(driver) if driver in active else 0
        gap = driver.total_time - active[index-1].total_time if index > 0 else None
        if attack and (race.current_segment_type != "reta" or gap is None or gap > OVERTAKE_DETECTION_SECONDS):
            return await interaction.response.send_message("DRS indisponível: precisa estar até 1,0s do carro à frente em uma reta.", ephemeral=True)
        if (boost or attack) and race.current_segment_type != "reta":
            return await interaction.response.send_message("Essa ação só está disponível em uma reta.", ephemeral=True)
        if pit and race.current_segment_type != "reta" and race.safety_car_laps <= 0:
            return await interaction.response.send_message("Pit stop fora de uma reta só é permitido durante o Safety Car.", ephemeral=True)
        if pit and driver.tire_changes_remaining <= 0:
            return await interaction.response.send_message("Você já utilizou os 2 jogos de pneus disponíveis (jogo inicial + 1 troca).", ephemeral=True)
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
                action["pit_repair"] = bool(pit_repair)
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
        return driver.effective_skill("straights") * 0.095 + driver.effective_skill("acceleration") * 0.065
    # Curva, frenagem e controle fazem diferença na zona técnica.
    return driver.effective_skill("curves") * 0.105 + driver.effective_skill("control") * 0.075


def calculate_segment_time(driver, race, segment, action, opponent_gap=None, opponent=None):
    circuit = CIRCUITS[race.circuit_name]
    rain = WEATHER[race.weather_name]["rain"]
    mode = DRIVING_MODES[action["mode"]]
    base = segment_base_time(segment, circuit)

    skill_bonus = skill_segment_bonus(driver, segment)
    pit_penalty = 0.0
    event = ""
    if action.get("pit"):
        chosen_tire = action.get("pit_tire") or ("Wet" if rain > 0.65 else "Intermediate" if rain > 0.10 else "Medium")
        if chosen_tire not in TIRES:
            chosen_tire = "Medium"
        old_tire = driver.tire
        if driver.tire_changes_remaining <= 0:
            return base + 999.0, f"⚠️ {driver_display_name(driver)} não tem mais trocas de pneus disponíveis."
        driver.tire_changes_remaining -= 1
        driver.tire = chosen_tire
        driver.tire_wear = 0.0
        # Toda parada mantém a manutenção básica de 12%; o serviço opcional
        # simula a troca/reparo adicional da asa dianteira.
        driver.car_damage = max(0.0, driver.car_damage - 12.0)
        repair_penalty = 0.0
        repaired = 0.0
        if action.get("pit_repair") and driver.car_damage > 0:
            repaired = min(30.0, driver.car_damage)
            driver.car_damage = max(0.0, driver.car_damage - 30.0)
            repair_penalty = 4.0
        driver.pit_stops += 1
        driver.last_pit_lap = race.current_lap
        crew_loss = random.uniform(0.5, 2.5)
        if random.random() < 0.18:
            crew_loss += random.uniform(2.0, 5.0)
        base_pit_loss = 6.0 if race.safety_car_laps > 0 else 18.0
        pit_penalty = base_pit_loss + crew_loss + repair_penalty
        sc_label = " durante o Safety Car" if race.safety_car_laps > 0 else ""
        repair_label = f" Reparo adicional da asa: -{repaired:.0f}% dano (+{repair_penalty:.0f}s)." if repaired > 0 else ""
        event = (f"🛠️ PIT STOP{sc_label}: {driver_display_name(driver)} trocou "
                 f"{TIRES[old_tire]['label'] if old_tire in TIRES else 'pneus'} por {TIRES[chosen_tire]['label']}. "
                 f"Parada: {base_pit_loss:.0f}s + {crew_loss:.1f}s da equipe.{repair_label} Restam {driver.tire_changes_remaining} trocas de jogo.")
    if driver.ability == "Largada Explosiva" and race.current_lap == 1:
        skill_bonus += base * 0.006
    if driver.ability == "Última Volta" and race.current_lap == race.total_laps:
        skill_bonus += base * 0.006
    tire_mult = tire_weather_multiplier(driver.tire, rain)
    # O desgaste agora gera perda de ritmo progressiva e perceptível, não apenas um bônus quase invisível.
    tire_wear_penalty = (driver.tire_wear / 100.0) ** 1.5 * 1.20
    tire_loss = max(0.0, 1.0 - tire_mult) * (base * 0.12)
    weather_loss = rain * (base * 0.08)
    mismatch_loss = 0.0
    wrong_tire = False
    if rain > 0.65 and driver.tire != "Wet":
        mismatch_loss = base * 0.12
        wrong_tire = True
    elif 0.10 < rain <= 0.65 and driver.tire not in ("Intermediate", "Wet"):
        mismatch_loss = base * 0.07
        wrong_tire = True
    elif rain <= 0.10 and driver.tire in ("Intermediate", "Wet"):
        mismatch_loss = base * 0.10
        wrong_tire = True
    if wrong_tire and driver.tire_warning_lap != race.current_lap:
        driver.tire_warning_lap = race.current_lap
        event = (event + " " if event else "") + f"⚠️ {driver_display_name(driver)} está com pneus inadequados para a pista ({TIRES[driver.tire]['label']})."
    if driver.ability == "Rei da Chuva":
        weather_loss *= 0.82
    mode_adjustment = mode["pace"]
    line_risk = 0.0
    if segment == "curva":
        line = action.get("line")
        if line == "inside":
            mode_adjustment -= 0.055
            line_risk += 0.020
        elif line == "outside":
            mode_adjustment -= 0.030
        elif line == "defend":
            mode_adjustment += 0.005
            line_risk -= 0.018
        elif line == "safe":
            mode_adjustment += 0.035
            line_risk -= 0.035

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
    time = base - skill_bonus + tire_wear_penalty + tire_loss + weather_loss + mismatch_loss + mode_adjustment + energy_adjustment + random_error + base * damage_penalty + pit_penalty

    curve_intensity = 1.0 if segment == "curva" else 0.35
    risk = 0.010 + mode["risk"] + line_risk + rain * (0.075 if segment == "curva" else 0.035)
    if wrong_tire:
        risk += 0.055 if rain > 0.65 else 0.025
    risk += (driver.tire_wear / 100) * 0.16 + (driver.car_damage / 100) * 0.085
    risk += curve_intensity * max(0, 5 - driver.effective_skill("curves")) * 0.008
    risk += curve_intensity * max(0, 5 - driver.effective_skill("control")) * 0.009
    if driver.ability == "Mãos de Cirurgião":
        risk -= 0.015
    if driver.ability == "Sangue Frio" and action["mode"] == "aggressive":
        risk -= 0.012
    risk += max(0, -mode["pace"]) * 0.30  # agressividade/ação rápida
    risk = max(0.004, min(0.30, risk))

    if random.random() < risk:
        severity = random.random()
        if severity < 0.68:
            lost = base * random.uniform(0.05, 0.14)
            driver.incidents += 1
            driver.spins += 1
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(3, 9))
            event = (event + " " if event else "") + f"💥 Derrapagem/contato: +{driver.car_damage:.0f}% dano, perdeu tempo."
        elif severity < 0.96:
            lost = base * random.uniform(0.14, 0.30)
            driver.incidents += 1
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(12, 24))
            event = (event + " " if event else "") + f"🚧 Acidente moderado: dano do carro {driver.car_damage:.0f}%."
        else:
            lost = base * random.uniform(0.30, 0.55)
            driver.incidents += 1
            driver.severe_accidents += 1
            driver.car_damage = min(100.0, driver.car_damage + random.uniform(30, 45))
            event = (event + " " if event else "") + f"🛑 Acidente grave: dano do carro {driver.car_damage:.0f}%."
        time += lost
        driver.tire_wear = min(100.0, driver.tire_wear + 2.0)
        driver.events.append(event)
    else:
        driver.events.append("—")

    # Desgaste progride em cada segmento e afeta ritmo nos segmentos futuros.
    wear_increment = TIRES[driver.tire]["wear"] * (1.35 if segment == "reta" else 2.15)
    wear_increment *= max(0.65, 1.0 - driver.effective_skill("tyre_management") * 0.035)
    if driver.ability == "Mestre dos Pneus":
        wear_increment *= 0.82
    if driver.ability == "Pit Stop Perfeito" and race.current_lap == 1 and segment == "reta":
        wear_increment *= 0.85
    if action["mode"] == "aggressive":
        wear_increment *= 1.20
    if action["mode"] == "safe":
        wear_increment *= 0.85
    if rain > 0.50 and driver.tire == "Wet":
        wear_increment *= 0.85
    if wrong_tire:
        wear_increment *= 1.25
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
    position_lines = []
    condition_lines = []
    for pos, driver in enumerate(order, 1):
        gap = "Líder" if pos == 1 else f"+{driver.total_time - order[pos-2].total_time:.3f}s para P{pos-1}"
        status = " • ⛔ ABANDONOU" if driver.retired else ""
        position_lines.append(
            f"**P{pos} — {driver_display_name(driver)}**  `{format_time(driver.total_time)}`  · {gap}{status}"
        )
        condition_lines.append(
            f"**{driver_display_name(driver)}:** {TIRES[driver.tire]['label']} · "
            f"desgaste {driver.tire_wear:.0f}% · energia {driver.energy:.0f}% · dano {driver.car_damage:.0f}%"
        )
    embed = discord.Embed(
        title="🏎️ Painel da corrida",
        description=f"**{race.circuit_name}**  ·  Volta **{lap}/{race.total_laps}**  ·  {segment_label}",
        color=discord.Color.blue(),
    )
    embed.add_field(name="🏁 Classificação", value="\n".join(position_lines) or "Sem pilotos", inline=False)
    embed.add_field(name="🛞 Estado dos carros", value="\n".join(condition_lines) or "Sem dados", inline=False)
    embed.add_field(
        name="🌦️ Condições da pista",
        value=f"**{race.weather_name}** · {race.surface} · Ambiente {race.ambient_temp}°C · Pista {race.track_temp}°C",
        inline=False,
    )
    if race.safety_car_laps > 0:
        embed.add_field(
            name="🚨 JANELA DE PIT STOP DO SAFETY CAR",
            value="**É nesta janela que a parada custa menos tempo:** cerca de 6s + tempo da equipe, em vez dos 18s + equipe de um pit stop normal. A vantagem só vale enquanto o Safety Car estiver ativo; depois, a parada volta ao custo normal.",
            inline=False,
        )
    return embed


def add_transmission_field(embed, events):
    if not events:
        return
    event_text = "\n".join(f"• {event}" for event in events[-8:])
    if len(event_text) > 1000:
        event_text = event_text[:997] + "..."
    embed.add_field(name="📻 Rádio da corrida — acontecimentos", value=event_text, inline=False)




class QualifyingView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=None)
        self.race = race

    @discord.ui.button(label="Iniciar corrida", emoji="🚦", style=discord.ButtonStyle.success)
    async def begin_race(self, interaction, button):
        race = self.race
        if interaction.channel_id != race.channel_id or not race_is_active(race) or interaction.user.id != race.host_id:
            return await interaction.response.send_message("Somente o host desta corrida pode iniciar.", ephemeral=True)
        if not race.qualifying_done or race.race_started:
            return await interaction.response.send_message("A corrida ainda não está pronta para começar.", ephemeral=True)
        if race.lobby_timeout_task and not race.lobby_timeout_task.done():
            race.lobby_timeout_task.cancel()
        race.race_task = asyncio.create_task(run_race(race))
        await interaction.response.edit_message(content="🚦 Corrida iniciada! O painel será atualizado a cada trecho.", view=ClosedView())


class RemoveDriverSelect(discord.ui.Select):
    def __init__(self, race):
        self.race = race
        options = [discord.SelectOption(label=driver_display_name(driver)[:100], value=str(uid))
                   for uid, driver in list(race.drivers.items())[:25]]
        if not options:
            options = [discord.SelectOption(label="Nenhum piloto inscrito", value="none")]
        super().__init__(placeholder="Remover um piloto do lobby", options=options, min_values=1, max_values=1, row=4)

    async def callback(self, interaction):
        if interaction.user.id != self.race.host_id:
            return await interaction.response.send_message("Somente o criador pode remover pilotos.", ephemeral=True)
        if not race_is_active(self.race) or self.race.started:
            return await interaction.response.send_message("O lobby não aceita mais alterações.", ephemeral=True)
        if self.values[0] == "none":
            return await interaction.response.send_message("Não há pilotos para remover.", ephemeral=True)
        uid = int(self.values[0])
        removed = self.race.drivers.pop(uid, None)
        if removed:
            await interaction.response.send_message(f"🏁 {driver_display_name(removed)} foi removido do lobby.", ephemeral=True)
            await refresh_lobby(self.race, LobbyView(self.race))
        else:
            await interaction.response.send_message("Esse piloto não está mais no lobby.", ephemeral=True)


class AddBotsModal(discord.ui.Modal, title="Adicionar pilotos controlados pelo bot"):
    def __init__(self, race):
        super().__init__()
        self.race = race
        self.amount = discord.ui.TextInput(label="Quantidade de bots para adicionar", placeholder="Ex.: 3", min_length=1, max_length=2)
        self.add_item(self.amount)
    async def on_submit(self, interaction):
        if interaction.user.id != self.race.host_id or not race_is_active(self.race) or self.race.started:
            return await interaction.response.send_message("Somente o criador pode alterar este lobby antes da classificação.", ephemeral=True)
        try: amount = int(self.amount.value)
        except ValueError: return await interaction.response.send_message("Informe um número inteiro.", ephemeral=True)
        if amount < 1: return await interaction.response.send_message("Informe pelo menos 1 bot.", ephemeral=True)
        async with self.race.lock:
            if not race_is_active(self.race) or self.race.started:
                return await interaction.response.send_message("O lobby não aceita mais alterações.", ephemeral=True)
            amount = min(amount, self.race.max_players - len(self.race.drivers))
            if amount <= 0:
                return await interaction.response.send_message("O lobby já está cheio.", ephemeral=True)
            added = []
            for _ in range(amount):
                self.race.bot_counter += 1
                bot_id = -self.race.bot_counter
                driver = create_bot_driver(self.race, bot_id)
                self.race.drivers[bot_id] = driver
                added.append(driver.race_name)
            # Atualiza a mensagem pública antes de confirmar ao host: se o Discord
            # rejeitar a edição, o callback não informa que a lista foi atualizada.
            await refresh_lobby(self.race, LobbyView(self.race))
        await interaction.response.send_message(
            f"🤖 Adicionei {len(added)} piloto(s): {', '.join(added)}. Eles já entram configurados e prontos.",
            ephemeral=True,
        )

BOT_PILOT_NAMES = ["Charles Leclerc", "Lewis Hamilton", "Max Verstappen", "Lando Norris", "Oscar Piastri", "Fernando Alonso", "Carlos Sainz", "George Russell", "Kimi Antonelli", "Pierre Gasly", "Esteban Ocon", "Alex Albon", "Nico Hülkenberg", "Yuki Tsunoda", "Oliver Bearman", "Ayrton Senna", "Michael Schumacher", "Sebastian Vettel", "Daniel Ricciardo", "Valtteri Bottas"]

def create_bot_driver(race, bot_id):
    name = random.choice(BOT_PILOT_NAMES); style = roll_style(); skills = {key: 0 for key, _, _ in SKILL_FIELDS}; remaining = SKILL_POINTS
    for index, (key, _, _) in enumerate(SKILL_FIELDS):
        points = remaining if index == len(SKILL_FIELDS) - 1 else random.randint(0, remaining)
        skills[key] = points; remaining -= points
    rain = WEATHER[race.weather_name]["rain"]; tire = "Wet" if rain > 0.65 else "Intermediate" if rain > 0.10 else random.choice(("Soft", "Medium", "Hard"))
    fake_user = SimpleNamespace(id=bot_id, display_name=name, mention=f"🤖 {name}", display_avatar=SimpleNamespace(url=f"https://cdn.discordapp.com/embed/avatars/{abs(bot_id) % 6}.png"))
    bonuses = style.get("skills", {})
    return Driver(user=fake_user, race_name=name, team_name=random.choice(("Ferrari", "Mercedes", "McLaren", "Red Bull", "Aston Martin", "Williams")), tyre_management=skills["tyre_management"], curves=skills["curves"], speed=skills["speed"], qualifying=skills["qualifying"], engine=skills["engine"], control=skills["control"], straights=skills["speed"], braking=skills["qualifying"], acceleration=skills["engine"], ability=random.choice(list(ABILITY_CATALOG)), tire=tire, ready=True, style_name=style["name"], style_tyre_management=int(bonuses.get("tyre_management", 0)), style_curves=int(bonuses.get("curves", 0)), style_straights=int(bonuses.get("straights", 0)), style_braking=int(bonuses.get("braking", 0)), style_acceleration=int(bonuses.get("acceleration", 0)), style_control=int(bonuses.get("control", 0)), is_bot=True)

def bot_race_decision(driver, race, segment, active):
    if driver.tire_changes_remaining > 0 and driver.last_pit_lap != race.current_lap and (segment == "reta" or race.safety_car_laps > 0) and (driver.tire_wear >= 62 or (race.safety_car_laps > 0 and driver.tire_wear >= 35)):
        rain = WEATHER[race.weather_name]["rain"]; tire = "Wet" if rain > 0.65 else "Intermediate" if rain > 0.10 else random.choice(("Medium", "Hard"))
        return {"mode": "normal", "attack": False, "boost": False, "pit": True, "pit_tire": tire}
    if segment == "curva":
        return {"mode": random.choices(("normal", "defensive", "safe", "aggressive"), weights=(45,20,25,10))[0], "attack": False, "boost": False, "line": random.choice(("inside","outside","safe"))}
    ordered = sorted(active, key=lambda item: item.total_time); index = ordered.index(driver)
    gap = driver.total_time - ordered[index-1].total_time if index > 0 else None
    return {"mode": random.choices(("normal","defensive","aggressive"), weights=(60,15,25))[0], "attack": gap is not None and gap <= OVERTAKE_DETECTION_SECONDS and random.random() < .55, "boost": driver.energy > 35 and random.random() < .18}


class LobbyConfigView(discord.ui.View):
    def __init__(self, race):
        super().__init__(timeout=120)
        self.race = race
        self.add_item(LapsSelect(race))
        self.add_item(CircuitSelect(race))
        self.add_item(WeatherSelect(race))
        self.add_item(DecisionTimeSelect(race))
        self.add_item(RemoveDriverSelect(race))


class LobbyConfigSelect(discord.ui.Select):
    def __init__(self, race, options, placeholder):
        self.race = race
        super().__init__(options=options, placeholder=placeholder, min_values=1, max_values=1)

    async def host_check(self, interaction):
        if interaction.channel_id != self.race.channel_id or not race_is_active(self.race):
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
    add_transmission_field(embed, events)
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
        await flush_race_broadcasts(race)


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
    add_transmission_field(embed, events)
    return embed


EVENT_ASSET_DIR = Path(__file__).parent / "assets" / "eventos"
EVENT_LINKS_FILE = EVENT_ASSET_DIR / "links.json"
EVENT_IMAGE_RULES = {
    "ultrapassagem": ("ultrapassagem", "↗️"),
    "ultrapassou": ("ultrapassagem", "↗️"),
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
    # Enfileira o acontecimento para ele ser publicado abaixo do painel mais recente.
    race.pending_broadcasts.append(message)


async def flush_race_broadcasts(race):
    while race.pending_broadcasts:
        message = race.pending_broadcasts.pop(0)
        lower = message.lower()
        emoji = "📻"
        event_folder = None
        for keyword, (folder_name, event_emoji) in EVENT_IMAGE_RULES.items():
            if keyword.lower() in lower:
                event_folder, emoji = folder_name, event_emoji
                break
        try:
            embed = discord.Embed(description=message, color=discord.Color.orange())
            if event_folder:
                folder = EVENT_ASSET_DIR / event_folder
                image_mapping = event_image_links()
                links_key = event_folder
                if event_folder == "clima":
                    weather_image_keys = {
                        "sol": "clima_sol",
                        "parcialmente nublado": "clima_parcialmente_nublado",
                        "nublado": "clima_nublado",
                        "chuva leve": "clima_chuva_leve",
                        "chuva forte": "clima_chuva_forte",
                    }
                    message_lower = message.lower()
                    links_key = next((key for label, key in weather_image_keys.items() if label in message_lower), "clima")
                    if links_key.startswith("clima_"):
                        folder = folder / links_key.removeprefix("clima_")
                local_images = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}] if folder.exists() else []
                links = image_mapping.get(links_key, image_mapping.get(event_folder, []))
                if isinstance(links, str):
                    links = [links]
                links = [url for url in links if isinstance(url, str) and url.startswith(("https://", "http://"))]
                # Sorteia entre arquivos locais e URLs, em vez de sempre priorizar a primeira fonte.
                image_options = [("local", asset) for asset in local_images] + [("url", url) for url in links]
                if image_options:
                    image_type, selected_image = random.choice(image_options)
                    if image_type == "local":
                        file = discord.File(selected_image, filename=selected_image.name)
                        embed.set_image(url=f"attachment://{selected_image.name}")
                        await race.channel.send(content=emoji, embed=embed, file=file)
                    else:
                        embed.set_image(url=selected_image)
                        await race.channel.send(content=emoji, embed=embed)
                else:
                    await race.channel.send(content=f"{emoji} {message}")
            else:
                await race.channel.send(content=f"{emoji} {message}")
        except (discord.HTTPException, OSError):
            continue

async def build_podium_file(order):
    """Monta uma arte de pódio com as fotos cadastradas ou avatares do Discord."""
    podium_drivers = [driver for driver in order if not driver.retired][:3]
    if not podium_drivers:
        return None

    width, height = 1200, 680
    canvas = Image.new("RGB", (width, height), (13, 20, 34))
    pixels = canvas.load()
    for y in range(height):
        blend = y / max(1, height - 1)
        color = (int(13 + 10 * blend), int(20 + 12 * blend), int(34 + 22 * blend))
        for x in range(width):
            pixels[x, y] = color

    draw = ImageDraw.Draw(canvas)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        time_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
        fallback_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except OSError:
        title_font = name_font = time_font = fallback_font = ImageFont.load_default()

    draw.text((width // 2, 58), "PÓDIO", font=title_font, fill=(245, 248, 255), anchor="mm")

    layout = {
        1: (455, 300, 290, 275, (242, 190, 65)),
        2: (145, 375, 290, 200, (190, 205, 222)),
        3: (765, 420, 290, 155, (190, 125, 78)),
    }

    async def download_photo(driver):
        profile = USER_PROFILES.get(str(driver.user.id), {})
        urls = [profile.get("photo_url"), str(driver.user.display_avatar.url)]
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls:
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.read()
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    continue
        return None

    photos = await asyncio.gather(*(download_photo(driver) for driver in podium_drivers))
    for position, (driver, photo_data) in enumerate(zip(podium_drivers, photos), 1):
        x, y, box_width, box_height, accent = layout[position]
        center = x + box_width // 2
        avatar_size = 150
        avatar_y = y - 175
        draw.ellipse((center - avatar_size // 2 - 7, avatar_y - 7,
                      center + avatar_size // 2 + 7, avatar_y + avatar_size + 7),
                     fill=accent)
        if photo_data:
            try:
                avatar = Image.open(BytesIO(photo_data)).convert("RGB")
                avatar = ImageOps.fit(avatar, (avatar_size, avatar_size), method=Image.Resampling.LANCZOS)
            except (OSError, ValueError):
                avatar = None
        else:
            avatar = None
        if avatar is None:
            avatar = Image.new("RGB", (avatar_size, avatar_size), (48, 62, 82))
            avatar_draw = ImageDraw.Draw(avatar)
            initials = "".join(part[0] for part in driver_display_name(driver).split()[:2]).upper() or "F1"
            avatar_draw.text((avatar_size // 2, avatar_size // 2), initials, font=fallback_font,
                             fill=(255, 255, 255), anchor="mm")
        mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
        canvas.paste(avatar, (center - avatar_size // 2, avatar_y), mask)

        draw.rounded_rectangle((x, y, x + box_width, y + box_height), radius=24,
                               fill=(28, 40, 59), outline=accent, width=5)
        name = driver_display_name(driver)
        if len(name) > 21:
            name = name[:20] + "…"
        draw.text((center, y + 76), name, font=name_font, fill=(248, 250, 255), anchor="mm")
        draw.text((center, y + 132), format_time(driver.total_time), font=time_font,
                  fill=(225, 233, 245), anchor="mm")

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    output.seek(0)
    return discord.File(output, filename="podio-f1.png")


def race_award_data(order, fastest):
    humans = [driver for driver in order if not getattr(driver, "is_bot", False)]
    if not humans:
        return None
    metrics = []
    for final_position, driver in enumerate(order, 1):
        if getattr(driver, "is_bot", False):
            continue
        grid_position = driver.grid_position or final_position
        positions_gained = grid_position - final_position
        lap_spread = 0.0
        if len(driver.lap_times) > 1:
            mean = sum(driver.lap_times) / len(driver.lap_times)
            lap_spread = (sum((value - mean) ** 2 for value in driver.lap_times) / len(driver.lap_times)) ** 0.5
        consistency_bonus = max(0.0, 3.0 - lap_spread)
        best_score = (
            driver.overtakes_made * 2.5
            + positions_gained * 2.0
            + (2.0 if fastest and fastest.user.id == driver.user.id else 0.0)
            + consistency_bonus
            + (1.0 if not driver.retired else 0.0)
            - driver.incidents * 2.5
            - driver.severe_accidents * 3.0
            - (5.0 if driver.retired else 0.0)
        )
        positions_lost = max(0, final_position - grid_position)
        worst_score = (
            driver.incidents * 3.0
            + driver.spins * 2.0
            + driver.severe_accidents * 5.0
            + positions_lost * 1.5
            + max(0.0, lap_spread - 2.0) * 0.8
            + (6.0 if driver.retired else 0.0)
            - driver.overtakes_made * 0.5
        )
        metrics.append({
            "driver": driver,
            "position": final_position,
            "grid": grid_position,
            "gained": positions_gained,
            "spread": lap_spread,
            "best_score": best_score,
            "worst_score": worst_score,
        })
    best = max(metrics, key=lambda item: (item["best_score"], item["gained"], item["driver"].overtakes_made))
    worst = max(metrics, key=lambda item: (item["worst_score"], item["driver"].incidents, item["driver"].severe_accidents))
    return {"best": best, "worst": worst}


def race_award_embed(award_data, award_type):
    item = award_data[award_type]
    driver = item["driver"]
    is_best = award_type == "best"
    title = "🌟 MELHOR PILOTO DA CORRIDA" if is_best else "🫣 PILOTO DO CAOS"
    color = discord.Color.gold() if is_best else discord.Color.red()
    movement = f"+{item['gained']} posições" if item["gained"] > 0 else f"{item['gained']} posições" if item["gained"] < 0 else "manteve a posição"
    description = (
        f"**{driver_display_name(driver)}**\n"
        f"Resultado: **P{item['position']}** (largou em P{item['grid']})\n"
        f"Ultrapassagens: **{driver.overtakes_made}**\n"
        f"Movimentação no grid: **{movement}**\n"
        f"Incidentes: **{driver.incidents}** • Derrapagens: **{driver.spins}** • Acidentes graves: **{driver.severe_accidents}**\n"
        f"Consistência das voltas: **{item['spread']:.2f}s** de variação média\n\n"
        + (
            "Pontuação considera ultrapassagens, posições recuperadas, volta rápida, regularidade e incidentes."
            if is_best else
            "Destaque humorístico calculado por incidentes, derrapagens, danos, posições perdidas e abandono."
        )
    )
    embed = discord.Embed(title=title, description=description, color=color)
    profile = USER_PROFILES.get(str(driver.user.id), {})
    photo = profile.get("photo_url") or str(driver.user.display_avatar.url)
    if isinstance(photo, str) and photo.startswith(("https://", "http://")):
        embed.set_image(url=photo)
    embed.set_footer(text="Use as setas para alternar entre as duas premiações.")
    return embed


class RaceAwardsView(discord.ui.View):
    def __init__(self, award_data):
        super().__init__(timeout=300)
        self.award_data = award_data

    async def change_page(self, interaction, page):
        key = "best" if page == 0 else "worst"
        await interaction.response.edit_message(embed=race_award_embed(self.award_data, key), view=self)

    @discord.ui.button(label="Melhor piloto", emoji="⬅️", style=discord.ButtonStyle.success)
    async def best(self, interaction, button):
        await self.change_page(interaction, 0)

    @discord.ui.button(label="Pior piloto", emoji="➡️", style=discord.ButtonStyle.danger)
    async def worst(self, interaction, button):
        await self.change_page(interaction, 1)


async def run_race(race):
    race.race_started = True
    if race.lobby_timeout_task and not race.lobby_timeout_task.done():
        race.lobby_timeout_task.cancel()
    grid = sorted(race.drivers.values(), key=lambda d: d.grid_position or 99)
    for rank, driver in enumerate(grid):
        driver.total_time = rank * 0.25
        driver.distance = float(rank)
    circuit = CIRCUITS[race.circuit_name]
    segments = circuit.get("segments") or ["reta", "curva"]
    resume_segment_index = 1
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
        safety_car_triggered_this_lap = False
        for segment_index in range(resume_segment_index, len(segments) + 1):
            segment = segments[segment_index - 1]
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
                for driver in active:
                    if driver.is_bot:
                        driver.chosen_action = bot_race_decision(driver, race, segment, active)
            segment_title = f"{segment.upper()} {segment_index}/{len(segments)}"
            race.current_decision_label = f"Volta {lap}/{race.total_laps} • {segment_title}"
            await update_race_panel(race, active, segment_title, lap_events, show_decision=True)
            lap_events.clear()
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
            for index, driver in enumerate(pre_order):
                if index == 0 or driver.retired:
                    continue
                action = driver.chosen_action or {}
                target = pre_order[index - 1]
                prior_gap = gaps.get(driver.user.id)
                if action.get("attack") and prior_gap is not None and prior_gap <= OVERTAKE_DETECTION_SECONDS:
                    chance = 0.18 + driver.effective_skill("straights") * 0.035 + driver.effective_skill("acceleration") * 0.025 + driver.effective_skill("control") * 0.015
                    if driver.ability in ("Ultrapassador Nato", "Especialista em DRS"):
                        chance += 0.065
                    chance -= target.effective_skill("control") * 0.018
                    if target.ability == "Defensor Nato":
                        chance -= 0.060
                    chance = max(0.08, min(0.68, chance))
                    gap_after_segment = driver.total_time - target.total_time
                    if random.random() < chance and 0 < gap_after_segment <= 0.65:
                        driver.total_time = target.total_time - 0.02
                    elif gap_after_segment > 0:
                        lap_events.append(f"🚥 {driver_display_name(driver)} tentou ultrapassar {driver_display_name(target)} na volta {lap}, mas não conseguiu.")

            # Compara a ordem antes e depois do trecho para narrar também ultrapassagens naturais.
            updated_order = sorted([d for d in active if not d.retired], key=lambda d: d.total_time)
            old_positions = {driver.user.id: index for index, driver in enumerate(pre_order)}
            new_positions = {driver.user.id: index for index, driver in enumerate(updated_order)}
            for driver in updated_order:
                old_position = old_positions.get(driver.user.id)
                new_position = new_positions.get(driver.user.id)
                if old_position is None or new_position is None or new_position >= old_position:
                    continue
                passed = [
                    other for other in pre_order
                    if old_positions.get(other.user.id, 99) < old_position
                    and new_positions.get(other.user.id, -1) > new_position
                ]
                if passed:
                    names = ", ".join(driver_display_name(other) for other in passed)
                    overtake_event = (
                        f"↗️ **{driver_display_name(driver)} ultrapassou {names}** "
                        f"na volta {lap}, trecho {segment_index}/{len(segments)}!"
                    )
                    driver.overtakes_made += len(passed)
                    lap_events.append(overtake_event)
                    await publish_important_event(race, overtake_event)
            # Safety Car é reservado a incidentes realmente graves; derrapagens e
            # acidentes moderados não neutralizam a prova.
            severe_incident = any("acidente grave" in event.lower() or "abandono" in event.lower() for event in lap_events)
            still_running = [d for d in race.drivers.values() if not d.retired]
            sc_chance = 0.32 if race.total_laps >= 10 else 0.20 if race.total_laps <= 5 else 0.26
            if severe_incident and len(still_running) > 1 and race.safety_car_laps == 0 and random.random() < sc_chance:
                race.safety_car_laps = 1
                safety_car_triggered_this_lap = True
                resume_segment_index = segment_index
                safety_event = f"🚨 SAFETY CAR! O pelotão avançará para a volta {lap + 1}, trecho {segment_index}/{len(segments)}. A próxima decisão será sob Safety Car, com pit stop de perda reduzida."
                lap_events.append(safety_event)
                await publish_important_event(race, safety_event)
            if race.safety_car_laps > 0 and len(still_running) > 1:
                ordered = sorted(still_running, key=lambda d: d.total_time)
                leader_time = ordered[0].total_time
                for position, driver in enumerate(ordered):
                    driver.total_time = leader_time + position * 0.45
            if race.message:
                panel_embed = standings_embed(race, lap, segment_title, lap_events)
                add_transmission_field(panel_embed, lap_events)
                await race.message.edit(embed=panel_embed, view=ClosedView())
            await flush_race_broadcasts(race)
            lap_events.clear()
            if safety_car_triggered_this_lap:
                # Pula o restante da volta atual e retoma no mesmo setor na próxima volta.
                break
            if race.safety_car_laps > 0:
                race.safety_car_laps = 0
                resume_segment_index = 1
            still_active = [d for d in race.drivers.values() if not d.finished and not d.retired]
            if len(still_active) == 1:
                still_active[0].finished = True
                race.early_finish = True
                winner_event = f"🏁 Corrida encerrada antecipadamente: {driver_display_name(still_active[0])} é o vencedor, único piloto restante na pista!"
                lap_events.append(winner_event)
                await publish_important_event(race, winner_event)
                if race.message:
                    panel_embed = standings_embed(race, lap, "FIM ANTECIPADO", lap_events)
                    add_transmission_field(panel_embed, lap_events)
                    await race.message.edit(embed=panel_embed, view=ClosedView())
                await flush_race_broadcasts(race)
                break
        # A volta interrompida pelo Safety Car não conta como volta rápida.
        if not safety_car_triggered_this_lap:
            for driver in race.drivers.values():
                if not driver.finished and not driver.retired:
                    driver.last_lap_time = driver.total_time - lap_start_times.get(driver.user.id, driver.total_time)
                    minimum_valid_lap = circuit["base_lap"] * 0.55
                    if minimum_valid_lap <= driver.last_lap_time:
                        driver.lap_times.append(driver.last_lap_time)
                        if driver.last_lap_time < (driver.best_lap_time or float("inf")):
                            driver.best_lap_time = driver.last_lap_time
                            driver.best_lap_number = lap
        if race.safety_car_laps > 0 and not safety_car_triggered_this_lap:
            race.safety_car_laps = 0
            resume_segment_index = 1
        await asyncio.sleep(0.5)
    final_order = current_order(race)
    for driver in final_order:
        if not driver.retired:
            driver.finished = True
    fastest = min((d for d in final_order if d.best_lap_time is not None and not d.retired), key=lambda d: d.best_lap_time, default=None)
    if fastest:
        await publish_important_event(race, f"⏱️ Volta mais rápida: {driver_display_name(fastest)} — {format_time(fastest.best_lap_time)} (volta {fastest.best_lap_number})")
    if race.mode == "ranked":
        await register_championship_result(race, final_order, fastest)
    else:
        register_normal_result(race, final_order)
    human_drivers = [driver for driver in final_order if not getattr(driver, "is_bot", False)]
    bot_count = len(final_order) - len(human_drivers)
    points_allowed = len(human_drivers) >= 3 and bot_count <= len(human_drivers)
    if race.mode == "ranked":
        points_allowed = points_allowed and season_for(race.guild_id) is not None
        points_multiplier = 0.50 if race.total_laps <= 3 else 0.75 if race.total_laps <= 5 else 1.0
    podium_lines = []
    for position, driver in enumerate(final_order, 1):
        if getattr(driver, "is_bot", False):
            points_label = "• 🤖 IA"
        elif not points_allowed:
            points_label = "• sem pontuação nesta corrida"
        elif driver.retired:
            points_label = "• 0 pts"
        elif race.mode == "ranked":
            earned = CHAMPIONSHIP_POINTS.get(position, 0) * points_multiplier
            if fastest and fastest.user.id == driver.user.id and position <= 3:
                earned += 1 * points_multiplier
            points_label = f"• **{round(earned, 2):g} pts**"
        else:
            earned = NORMAL_RANKING_POINTS.get(position, 0)
            points_label = f"• **{earned} pts**"
        line = f"**P{position} — {driver_display_name(driver)}** — `{format_time(driver.total_time)}` {points_label}"
        if driver.best_lap_time:
            line += f" • VR: {format_time(driver.best_lap_time)} (V{driver.best_lap_number})"
        if driver.retired:
            line += " • Abandonou"
        podium_lines.append(line)
    podium = "\n".join(podium_lines)
    title = "🏁 VITÓRIA ANTECIPADA" if race.early_finish else "🏆 FIM DE CORRIDA — RESULTADO FINAL"
    embed = discord.Embed(title=title, description=podium or "Corrida encerrada sem pilotos classificados.", color=discord.Color.gold())
    embed.set_footer(text=f"{race.circuit_name} • {race.current_lap}/{race.total_laps} voltas • corrida concluída")
    podium_file = await build_podium_file(final_order)
    if podium_file:
        embed.set_image(url="attachment://podio-f1.png")
    if race.message:
        await race.message.edit(embed=embed, view=ClosedView(), attachments=[podium_file] if podium_file else [])
    else:
        if podium_file:
            await race.channel.send(embed=embed, file=podium_file)
        else:
            await race.channel.send(embed=embed)
    await flush_race_broadcasts(race)
    awards = race_award_data(final_order, fastest)
    if awards:
        await race.channel.send(embed=race_award_embed(awards, "best"), view=RaceAwardsView(awards))
    if race.lobby_timeout_task and not race.lobby_timeout_task.done():
        race.lobby_timeout_task.cancel()
    races.pop(race.race_id, None)




class ProfileNameModal(discord.ui.Modal, title="Configurar perfil de piloto"):
    def __init__(self, owner_id, source_message_id=None):
        super().__init__()
        self.owner_id = owner_id
        self.source_message_id = source_message_id
        profile = gacha_profile(owner_id)
        self.pilot_name = discord.ui.TextInput(
            label="Nome exibido",
            default=str(profile.get("name") or "")[:32],
            max_length=32,
            required=True,
        )
        self.age = discord.ui.TextInput(
            label="Idade",
            placeholder="Ex.: 22",
            default=str(profile.get("age") or "")[:3],
            max_length=3,
            required=False,
        )
        self.team_name = discord.ui.TextInput(
            label="Equipe",
            default=str(profile.get("team") or "")[:32],
            max_length=32,
            required=False,
        )
        self.photo_url = discord.ui.TextInput(
            label="URL da foto do piloto",
            placeholder="https://...",
            default=str(profile.get("photo_url") or "")[:300],
            max_length=300,
            required=False,
        )
        self.add_item(self.pilot_name)
        self.add_item(self.age)
        self.add_item(self.team_name)
        self.add_item(self.photo_url)
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
    def __init__(self, owner_id, race=None):
        super().__init__()
        self.owner_id = owner_id
        self.source_message_id = None
        self.race = race
        skills = gacha_profile(owner_id)["skills"]
        self.tyres = discord.ui.TextInput(label="Gerenciamento de pneus", placeholder="0 a 10 pontos", default=str(skills.get("tyre_management", 0)), max_length=2)
        self.curves = discord.ui.TextInput(label="Curvas", placeholder="0 a 10 pontos", default=str(skills.get("curves", 0)), max_length=2)
        self.speed = discord.ui.TextInput(label="Velocidade", placeholder="0 a 10 pontos", default=str(skills.get("speed", 0)), max_length=2)
        self.qualifying = discord.ui.TextInput(label="Classificação", placeholder="0 a 10 pontos", default=str(skills.get("qualifying", 0)), max_length=2)
        self.engine = discord.ui.TextInput(label="Motor", placeholder="0 a 10 pontos", default=str(skills.get("engine", 0)), max_length=2)
        for item in (self.tyres, self.curves, self.speed, self.qualifying, self.engine):
            self.add_item(item)

    async def on_submit(self, interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse formulário não é seu.", ephemeral=True)
        try:
            values = [int(item.value.strip()) for item in (self.tyres, self.curves, self.speed, self.qualifying, self.engine)]
        except ValueError:
            return await interaction.response.send_message("Preencha os cinco campos com números inteiros de 0 a 10.", ephemeral=True)
        if any(value < 0 or value > SKILL_POINTS for value in values) or sum(values) > SKILL_POINTS:
            return await interaction.response.send_message(f"Os cinco valores devem ficar entre 0 e {SKILL_POINTS} e não podem ultrapassar {SKILL_POINTS} pontos somados. Reabra a distribuição e tente novamente.", ephemeral=True)
        partial = {field[0]: value for field, value in zip(SKILL_FIELDS[:5], values)}
        await interaction.response.send_message(
            "Os cinco primeiros atributos foram preenchidos. Clique abaixo para informar Controle e salvar a distribuição.",
            view=ProfileControlSkillView(self.owner_id, self.source_message_id, self.race, partial),
            ephemeral=True,
        )


class ProfileControlSkillView(discord.ui.View):
    def __init__(self, owner_id, source_message_id, race, partial):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.source_message_id = source_message_id
        self.race = race
        self.partial = partial

    @discord.ui.button(label="Definir Controle", emoji="🎯", style=discord.ButtonStyle.primary)
    async def define_control(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Essa distribuição pertence a outro piloto.", ephemeral=True)
        await interaction.response.send_modal(ProfileControlSkillModal(
            self.owner_id, self.source_message_id, self.race, self.partial
        ))


class ProfileControlSkillModal(discord.ui.Modal, title="Finalizar distribuição"):
    def __init__(self, owner_id, source_message_id, race, partial):
        super().__init__()
        self.owner_id = owner_id
        self.source_message_id = source_message_id
        self.race = race
        self.partial = partial
        profile = gacha_profile(owner_id)
        self.control = discord.ui.TextInput(
            label="Controle",
            placeholder="Informe os pontos de Controle",
            default=str(profile["skills"].get("control", 0)),
            max_length=2,
        )
        self.add_item(self.control)

    async def on_submit(self, interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Esse formulário não é seu.", ephemeral=True)
        try:
            control_value = int(self.control.value.strip())
        except ValueError:
            return await interaction.response.send_message("Controle deve ser um número inteiro de 0 a 10.", ephemeral=True)
        if not 0 <= control_value <= SKILL_POINTS:
            return await interaction.response.send_message("Controle deve ficar entre 0 e 10.", ephemeral=True)
        skills = dict(self.partial)
        skills["control"] = control_value
        if sum(skills.values()) != SKILL_POINTS:
            return await interaction.response.send_message(
                f"A distribuição precisa somar exatamente {SKILL_POINTS} pontos. Sua soma atual é {sum(skills.values())}. Reabra Distribuir pontos para ajustar os campos.",
                ephemeral=True,
            )
        profile = gacha_profile(self.owner_id)
        profile["skills"] = skills
        profile["skills_locked"] = True
        save_profiles()
        if self.race and self.owner_id in self.race.drivers and not self.race.started:
            driver = self.race.drivers[self.owner_id]
            for key, value in skills.items():
                setattr(driver, key, value)
            driver.straights = skills["speed"]
            driver.braking = skills["qualifying"]
            driver.acceleration = skills["engine"]
            driver.ready = False
        await interaction.response.send_message(
            "Distribuição salva! Os seis atributos foram identificados individualmente e somam 10 pontos.",
            ephemeral=True,
        )
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
            lines.append(f"**P{result['position']} — {race_data.get('circuit', 'Circuito')}**{status}{fastest}\n_{season_name} • {race_data.get('date', 'Data não registrada')[:10]}_")
        embed = discord.Embed(title="📜 Histórico de corridas", description="\n\n".join(lines), color=discord.Color.gold())
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
        active_style = profile.get('equipped_style_data')
        lines=[
            f"**🎲 Giros de estilo:** {profile['spins']}",
            f"**✨ Giros de habilidade:** {profile.get('ability_spins', 0)}",
            f"**🧠 Habilidade equipada:** {profile.get('ability') or 'Nenhuma'}",
            f"**🏎️ Estilo ativo:** {active_style['name']} — {active_style['rarity']}" if active_style else "**🏎️ Estilo ativo:** Nenhum",
            f"**⏭️ Gamepass Pular Giro:** {gp} • {active}",
        ]
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
        skill_lines = "\n".join(
            f"{emoji} **{label}:** {self.style_data.get('skills', {}).get(STYLE_SKILL_MAP.get(key), 0)}"
            for key, label, emoji in SKILL_FIELDS
        )
        result_embed = discord.Embed(
            title=f"{rarity['emoji']} CARTA DE ESTILO: {self.style_data['name']}",
            description=f"**{self.style_data['rarity']}** • {self.style_data.get('trait','')}\n\n{skill_lines}\n\n"
                        + ("Este é seu único estilo ativo. Um próximo estilo aceito substituirá este."
                           if accept else "Resultado recusado. A carta fica no histórico da conversa, mas seu estilo ativo não muda."),
            color=rarity["color"],
        )
        style_url = style_image_url(self.style_data["name"])
        if style_url:
            result_embed.set_image(url=style_url)
        roll_tag = interaction.message.content or f"Roll de estilo • <@{self.owner_id}>"
        await interaction.response.edit_message(content=roll_tag + "\n" + msg, embed=result_embed, view=GachaRollView(self.owner_id))
        # A carta sorteada não é apagada: o novo painel é enviado abaixo dela.
        panel_embed = discord.Embed(title="🎰 Gacha de estilos da F1", description=(
            f"**Giros disponíveis: {profile['spins']}**\nAo aceitar, o novo estilo substitui o atual.\n\n" +
            "\n".join(f"{RARITY_DATA[r]['emoji']} **{r}** — {RARITY_DATA[r]['chance']}% • {RARITY_DATA[r]['points']} pontos" for r in RARITY_DATA)
        ), color=discord.Color.purple())
        try:
            await interaction.channel.send(content=roll_tag, embed=panel_embed, view=GachaRollView(self.owner_id))
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
    is_new_profile = str(ctx.author.id) not in USER_PROFILES
    profile = gacha_profile(ctx.author.id)
    starter_style = profile.get("equipped_style_data")
    description = (
        f"**Giros disponíveis: {profile['spins']}**\n"
        + (f"🎁 **Estilo inicial gratuito:** {starter_style['name']} ({starter_style['rarity']})\n\n" if is_new_profile and starter_style else
           f"**Estilo atual:** {starter_style['name']} ({starter_style['rarity']})\n\n" if starter_style else "")
        + "Clique para girar. Ao aceitar um novo estilo, ele substitui o atual.\n\n"
        + "\n".join(f"{RARITY_DATA[r]['emoji']} **{r}** — {RARITY_DATA[r]['chance']}% • {RARITY_DATA[r]['points']} pontos" for r in RARITY_DATA)
    )
    embed = discord.Embed(title="🎰 Gacha de estilos da F1", description=description, color=discord.Color.purple())
    if starter_style:
        image_url = style_image_url(starter_style["name"])
        if image_url:
            embed.set_image(url=image_url)
    if is_new_profile:
        role, warning = await sync_pilot_role(ctx.guild, ctx.author, starter_style["name"])
        if warning:
            embed.add_field(name="Aviso de cargo", value=warning, inline=False)
    await ctx.send(content=f"🎟️ **Roll de estilo #{ctx.message.id}** • solicitado por {ctx.author.mention}", embed=embed, view=GachaRollView(ctx.author.id))

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
            profile.pop("ability_collection", None)
            message = f"✨ Habilidade **{self.ability_name}** equipada com sucesso!"
        else:
            message = f"🗑️ Habilidade **{self.ability_name}** recusada. Sua habilidade anterior foi mantida."
        profile.pop("pending_ability_roll", None)
        save_profiles()
        embed = discord.Embed(title="✨ Resultado do giro de habilidade", description=f"**{self.ability_name}**\n{ABILITY_CATALOG[self.ability_name]}", color=discord.Color.gold())
        roll_tag = interaction.message.content or f"Roll de habilidade • <@{self.owner_id}>"
        await interaction.response.edit_message(content=roll_tag + "\n" + message, embed=embed, view=None)

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
        await interaction.response.edit_message(content=interaction.message.content, embed=discord.Embed(title="✨ GIRANDO HABILIDADE...", description="A roleta está sorteando sua habilidade especial...", color=discord.Color.dark_grey()), view=None)
        await asyncio.sleep(2)
        result = discord.Embed(title=f"✨ HABILIDADE SORTEADA: {ability_name}", description=f"{ABILITY_CATALOG[ability_name]}\n\nDeseja equipar esta habilidade?", color=discord.Color.gold())
        try:
            await interaction.message.edit(content=interaction.message.content, embed=result, view=AbilityRollConfirmView(self.owner_id, ability_name))
        except discord.HTTPException:
            pass


@bot.command(name="roll-habilidade")
async def roll_ability_command(ctx):
    profile = gacha_profile(ctx.author.id)
    embed = discord.Embed(title="✨ Roleta de habilidades especiais", description=f"**Giros disponíveis:** {profile.get('ability_spins', 0)}\n**Custo:** 25.000 sonhos por giro\n\nClique para sortear uma habilidade. Você poderá equipar ou recusar o resultado.", color=discord.Color.gold())
    await ctx.send(content=f"🎟️ **Roll de habilidade #{ctx.message.id}** • solicitado por {ctx.author.mention}", embed=embed, view=AbilityRollView(ctx.author.id))


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

@bot.tree.command(name="diagnosticar_cargos_estilo", description="Verifica os IDs e a hierarquia dos cargos de estilo (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def diagnosticar_cargos_estilo(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
    guild = interaction.guild
    bot_member = guild.me
    missing = []
    above_bot = []
    found_lines = []
    for style_name, role_id in PILOT_ROLE_IDS.items():
        role = guild.get_role(int(role_id)) if role_id else None
        if role is None:
            missing.append(f"• **{style_name}** — ID {role_id} não encontrado")
            continue
        found_lines.append(f"• **{style_name}** → {role.mention} ({role.name})")
        if bot_member and role >= bot_member.top_role:
            above_bot.append(f"• {role.mention} — acima/no mesmo nível do cargo do bot")
    description = (
        f"**IDs configurados:** {len(PILOT_ROLE_IDS)}\n"
        f"**Cargos encontrados:** {len(found_lines)}\n"
        f"**IDs não encontrados:** {len(missing)}\n"
        f"**Cargos fora da hierarquia do bot:** {len(above_bot)}\n"
        f"**Permissão Gerenciar cargos:** {'Sim' if bot_member and bot_member.guild_permissions.manage_roles else 'Não'}"
    )
    if missing:
        description += "\n\n**IDs que não correspondem a cargos:**\n" + "\n".join(missing[:20])
    if above_bot:
        description += "\n\n**Cargos que o bot não consegue gerenciar:**\n" + "\n".join(above_bot[:20])
    if found_lines:
        description += "\n\n**Mapeamento encontrado (estilo → cargo real):**\n" + "\n".join(found_lines)
    if not missing and not above_bot and bot_member and bot_member.guild_permissions.manage_roles:
        description += "\n\nTodos os IDs foram encontrados e estão abaixo do cargo do bot. Se alguém ainda não recebe o cargo, use /sincronizar_estilo para corrigir o membro."
    embed = discord.Embed(title="🔎 Diagnóstico dos cargos de estilo", description=description[:4000], color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


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

NORMAL_RANKING_FILE = Path(__file__).with_name("ranking_normal.json")
NORMAL_RANKING_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

def load_normal_ranking():
    try:
        if NORMAL_RANKING_FILE.exists():
            data = json.loads(NORMAL_RANKING_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("players", {})
                data.setdefault("races", [])
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"players": {}, "races": []}

NORMAL_RANKING = load_normal_ranking()

def save_normal_ranking():
    NORMAL_RANKING_FILE.write_text(
        json.dumps(NORMAL_RANKING, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def normal_ranking_table(guild_id):
    rows = [
        row for row in NORMAL_RANKING.get("players", {}).values()
        if str(row.get("guild_id")) == str(guild_id)
    ]
    return sorted(
        rows,
        key=lambda row: (row.get("points", 0), row.get("wins", 0), row.get("podiums", 0), row.get("races", 0)),
        reverse=True,
    )

def register_normal_result(race, order):
    human_drivers = [driver for driver in order if not getattr(driver, "is_bot", False)]
    bot_count = len(order) - len(human_drivers)
    if race.mode != "casual" or race.race_id in NORMAL_RANKING.get("races", []):
        return
    if len(human_drivers) < 3 or bot_count > len(human_drivers):
        return
    players = NORMAL_RANKING.setdefault("players", {})
    for position, driver in enumerate(order, 1):
        if getattr(driver, "is_bot", False):
            continue
        key = f"{race.guild_id}:{driver.user.id}"
        row = players.setdefault(key, {
            "guild_id": str(race.guild_id),
            "user_id": str(driver.user.id),
            "name": driver_display_name(driver),
            "points": 0,
            "wins": 0,
            "podiums": 0,
            "races": 0,
        })
        row["name"] = driver_display_name(driver)
        row["races"] = row.get("races", 0) + 1
        if not driver.retired:
            row["points"] = row.get("points", 0) + NORMAL_RANKING_POINTS.get(position, 0)
            if position == 1:
                row["wins"] = row.get("wins", 0) + 1
            if position <= 3:
                row["podiums"] = row.get("podiums", 0) + 1
    NORMAL_RANKING.setdefault("races", []).append(race.race_id)
    save_normal_ranking()

def save_championship():
    CHAMPIONSHIP_FILE.write_text(json.dumps(CHAMPIONSHIP, ensure_ascii=False, indent=2), encoding="utf-8")

def season_for(guild_id):
    season_id = CHAMPIONSHIP.get("active", {}).get(str(guild_id))
    return CHAMPIONSHIP.get("seasons", {}).get(season_id) if season_id else None

async def register_championship_result(race, order, fastest):
    if race.mode != "ranked":
        return
    human_drivers = [driver for driver in order if not getattr(driver, "is_bot", False)]
    bot_count = len(order) - len(human_drivers)
    if len(human_drivers) < 3 or bot_count > len(human_drivers):
        return
    season = season_for(race.guild_id)
    if not season:
        return
    race_id = race.race_id
    if any(item.get("race_id") == race_id for item in season.get("races", [])):
        return
    results = []
    for position, driver in enumerate(order, 1):
        if getattr(driver, "is_bot", False):
            continue
        results.append({
            "user_id": str(driver.user.id),
            "name": driver_display_name(driver),
            "position": position,
            "retired": bool(driver.retired),
            "fastest_lap": bool(fastest and fastest.user.id == driver.user.id),
            "lap_time": driver.best_lap_time,
            "lap_number": driver.best_lap_number,
        })
    # Provas curtas valem menos pontos para evitar farm de etapas rápidas.
    points_multiplier = 0.50 if race.total_laps <= 3 else 0.75 if race.total_laps <= 5 else 1.0
    season.setdefault("races", []).append({
        "race_id": race_id, "circuit": race.circuit_name,
        "date": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "total_laps": race.total_laps,
        "points_multiplier": points_multiplier,
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
                multiplier = float(race_data.get("points_multiplier", 1.0))
                row["points"] += round(CHAMPIONSHIP_POINTS.get(pos, 0) * multiplier, 2)
                row["wins"] += pos == 1
                row["seconds"] += pos == 2
                row["thirds"] += pos == 3
                if result.get("fastest_lap") and pos <= 3:
                    row["points"] += round(1 * float(race_data.get("points_multiplier", 1.0)), 2)
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


@bot.command(name="rankingnormal")
async def normal_ranking_command(ctx):
    if not ctx.guild:
        return await ctx.send("O ranking normal só está disponível dentro de um servidor.")
    rows = normal_ranking_table(ctx.guild.id)
    if not rows:
        return await ctx.send("Ainda não há corridas casuais registradas neste servidor.")
    lines = [
        f"**P{position} — {row['name']}** • {row.get('points', 0)} pts • "
        f"{row.get('races', 0)} partidas • {row.get('wins', 0)} vitória(s)"
        for position, row in enumerate(rows[:20], 1)
    ]
    own = next((row for row in rows if row["user_id"] == str(ctx.author.id)), None)
    description = "\n".join(lines)
    if own:
        own_position = next(i for i, row in enumerate(rows, 1) if row["user_id"] == str(ctx.author.id))
        description += (
            f"\n\n**Sua posição:** P{own_position} • {own.get('points', 0)} pontos • "
            f"{own.get('races', 0)} partidas jogadas."
        )
    embed = discord.Embed(title="🏁 Ranking das corridas casuais", description=description, color=discord.Color.blue())
    embed.set_footer(text="Somente corridas !f1 contam neste ranking. Corridas oficiais ficam no !ranking.")
    await ctx.send(embed=embed)

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

SYSTEM_PAGES = ("corrida", "acoes", "pneus", "pilotagem", "estilos", "habilidades", "novidades")

def system_embed(page):
    if page == "corrida":
        description = (
            "**1. Criar e entrar**\n"
            "• `!f1`: cria uma corrida casual. `!f1rank`: cria uma etapa oficial e exige temporada ativa.\n"
            "• **Entrar na corrida** coloca você no lobby. **Configurar carro** distribui seus 10 pontos pessoais e permite escolher os pneus. **Estou pronto** confirma que terminou a configuração.\n"
            "• O host usa **Configurar lobby** para escolher voltas, circuito, clima e tempo de decisão. **Adicionar bots** preenche vagas com pilotos controlados pelo bot.\n"
            "• **Iniciar classificação** calcula o grid. Na tela seguinte, somente o host usa **Iniciar corrida**. A posição no grid influencia a largada.\n\n"
            "**2. Como funciona uma corrida**\n"
            "• Cada volta é dividida em 6 trechos. O painel mostra posição, tempo, pneus, desgaste, energia, dano e clima.\n"
            "• Em cada trecho, todos escolhem uma ação. As escolhas ficam escondidas até a rodada de decisões terminar; quem não escolher a tempo recebe automaticamente **Seguro**.\n"
            "• A palavra **rodada** nas imagens significa um *spin*: o carro perde aderência/controle e gira ou sai da linha, não é uma volta da corrida.\n\n"
            "**3. Pit Stop e Safety Car**\n"
            "• O botão **Pit Stop** abre um menu privado para escolher o novo composto. A parada normal custa aproximadamente 18s + tempo da equipe. Fazer uma parada sem necessidade pode fazer você perder posições.\n"
            "• Cada piloto começa com um jogo e tem direito a apenas uma troca. Não é possível fazer várias paradas para trocar pneus.\n"
            "• Quando o Safety Car está ativo, aparece **Pit Stop (Safety Car)** nas curvas e a parada custa cerca de 6s + equipe. Essa redução vale somente durante essa janela; depois, volta ao custo normal.\n"
            "• Durante o Safety Car, o pelotão é aproximado. Por isso, parar nessa janela pode custar menos posições do que parar em ritmo normal."
        )
        return discord.Embed(title="🏁 Guia para começar uma corrida", description=description, color=discord.Color.green())
    if page == "acoes":
        description = (
            "**Botões em retas**\n"
            "• **Manter ritmo:** opção equilibrada, sem gastar energia.\n"
            "• **Defender posição:** prioriza proteger sua colocação, sacrificando um pouco de ritmo.\n"
            "• **DRS / Ultrapassar:** só aparece quando há um adversário até 1 segundo à frente. Gasta 12 de energia e tenta a ultrapassagem; não é garantido.\n"
            "• **Boost Mode:** gasta 15 de energia para ganhar ritmo naquele trecho.\n"
            "• **Pit Stop:** abre a escolha de pneus. Use quando o desgaste estiver prejudicando seu tempo ou quando o clima exigir outro composto.\n\n"
            "**Botões em curvas**\n"
            "• **Por dentro:** linha mais curta e rápida, mas com maior risco de contato.\n"
            "• **Por fora:** linha mais longa, com risco menor.\n"
            "• **Defender a linha:** tenta impedir a ultrapassagem e protege posição, com pequena perda de ritmo.\n"
            "• **Traçado seguro:** sacrifica mais tempo para reduzir o risco de erro.\n"
            "• **Pit Stop (Safety Car):** aparece nas curvas somente enquanto o Safety Car está ativo. É a oportunidade de parar com perda reduzida.\n\n"
            "**Como decidir?**\n"
            "Não use Boost/DRS em toda reta sem pensar na energia. Evite parar com pneus ainda bons, pois uma parada normal custa bastante tempo. Se o desgaste estiver alto, compare o tempo que você pode recuperar com o tempo perdido no box."
        )
        return discord.Embed(title="🎮 O que cada botão faz", description=description, color=discord.Color.blue())
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
        skill_lines = [f"{emoji} **{label}** — atributo pessoal; os 10 pontos podem ser redistribuídos pelo perfil ou no lobby." for key, label, emoji in SKILL_FIELDS]
        description = "**Atributos**\n" + "\n".join(skill_lines)
        description += "\n\n**Modos de pilotagem**\n" + "\n".join(mode_lines)
        description += "\n\n**Ações adicionais**\n• Overtake Mode: tenta ultrapassar quando há adversário elegível à frente.\n• Boost Mode: usa energia para buscar ritmo extra.\n• Decisões são privadas até todos os pilotos confirmarem."
        return discord.Embed(title="🏎️ Atributos e pilotagem", description=description, color=discord.Color.blue())
    description = (
        "**Modalidades de corrida**\n"
        "• `!f1`: corrida casual com até 10 pilotos, lobbies simultâneos e ranking independente.\n"
        "• `!f1rank`: corrida oficial com até 10 pilotos; exige temporada ativa e registra pontos no campeonato.\n"
        "• Lobbies sem corrida iniciada expiram após 10 minutos. Administradores podem usar `!f1cancel @criador`.\n\n"
        "**Rankings**\n"
        "• `!rankingnormal`: pontos e partidas das corridas casuais.\n"
        "• `!ranking` e `!campeonato`: classificação da temporada oficial.\n\n"
        "**Piloto e simulação**\n"
        "• Seis atributos e 10 pontos redistribuíveis pelo perfil ou lobby.\n"
        "• Estilo e habilidade únicos equipados; um novo estilo aceito substitui o anterior.\n"
        "• Pneus, clima, desgaste, energia, pit stops e decisões influenciam a corrida. Cada piloto tem 2 jogos de pneus no total; pit stop sob Safety Car custa menos tempo e a neutralização dura mais uma volta completa.\n"
        "• Adicione bots pelo lobby: eles têm nomes de pilotos conhecidos, estilos aleatórios e tomam decisões automaticamente. Corridas com menos de 3 humanos ou bots em maioria não pontuam.\n"
        "• São 15 circuitos, cada um com uma prévia esquemática no lobby.\n"
        "• O pódio destaca foto, nome, tempo final e a volta mais rápida válida com o número da volta."
    )
    return discord.Embed(title="🆕 Novidades e sistemas", description=description, color=discord.Color.green())

class SystemView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    async def show(self, interaction, page):
        await interaction.response.edit_message(embed=system_embed(page), view=self)
    @discord.ui.button(label="Começar corrida", emoji="🏁", style=discord.ButtonStyle.primary, row=0)
    async def race_guide(self, interaction, button): await self.show(interaction, "corrida")
    @discord.ui.button(label="Botões da corrida", emoji="🎮", style=discord.ButtonStyle.success, row=0)
    async def actions(self, interaction, button): await self.show(interaction, "acoes")
    @discord.ui.button(label="Pneus e clima", emoji="🛞", style=discord.ButtonStyle.secondary, row=1)
    async def tires(self, interaction, button): await self.show(interaction, "pneus")
    @discord.ui.button(label="Atributos", emoji="🏎️", style=discord.ButtonStyle.secondary, row=1)
    async def driving(self, interaction, button): await self.show(interaction, "pilotagem")
    @discord.ui.button(label="Estilos", emoji="🎭", style=discord.ButtonStyle.secondary, row=2)
    async def styles(self, interaction, button): await self.show(interaction, "estilos")
    @discord.ui.button(label="Habilidades", emoji="✨", style=discord.ButtonStyle.secondary, row=2)
    async def abilities(self, interaction, button): await self.show(interaction, "habilidades")
    @discord.ui.button(label="Novidades", emoji="🆕", style=discord.ButtonStyle.secondary, row=3)
    async def news(self, interaction, button): await self.show(interaction, "novidades")

@bot.command(name="sistema")
async def system_command(ctx):
    await ctx.send(embed=system_embed("corrida"), view=SystemView())


@bot.command(name="comandos")
async def commands_list(ctx):
    embed = discord.Embed(title="📜 Comandos do F1 Discord Racing", color=discord.Color.blue())
    embed.description = (
        "**CORRIDAS**\n"
        "`!f1` — cria uma corrida casual com até 10 pilotos; não altera o campeonato.\n"
        "`!f1rank` — cria uma corrida oficial com até 10 pilotos; exige temporada ativa e soma pontos no campeonato.\n"
        "`!f1status [@criador]` — consulta os lobbies ativos neste canal ou o lobby de um criador específico.\n"
        "`!f1cancel` — o criador cancela a própria corrida. Administradores podem usar `!f1cancel @criador`.\n"
        "`!rankingnormal` — ranking de pontos e partidas das corridas casuais.\n"
        "`!ranking` / `!campeonato` — classificação da temporada oficial.\n\n"
        "**PILOTO E PERFIL**\n"
        "`!perfil [@membro]` — consulta perfil, atributos, estilo e habilidade.\n"
        "`!roll-estilo` — roleta de estilos; aceitar um novo substitui o estilo ativo.\n"
        "`!roll-habilidade` — roleta de habilidades especiais.\n"
        "`!transferir-giros @membro quantidade` — transfere giros de estilo.\n"
        "`!loja` / `!colecao-estilos` — loja e consulta do estilo atual.\n"
        "`!roll-pendente` / `!habilidade-pendente` — recupera resultados pendentes.\n"
        "`/adicionar_giros`, `/adicionar_giros_habilidade`, `/deletar_giros`, `/setar_estilo` e `/gamepass` — administração.\n\n"
        "**TEMPORADA E INFORMAÇÕES**\n"
        "`!iniciartemporada`, `!finalizartemporada`, `!resetcampeonato` — gestão da temporada (administradores).\n"
        "`!temporada`, `!resultado`, `!estatisticas` — dados da temporada.\n"
        "`!ajuda` — guia completo de como jogar.\n"
        "`!sistema` — painel interativo de atributos, pneus, estilos e habilidades."
    )
    await ctx.send(embed=embed)


@bot.command(name="ajuda")
async def help_f1(ctx):
    pages = [
        discord.Embed(
            title="📘 Guia de corrida — Começando",
            description=(
                "**Tipos de corrida**\n"
                "• !f1: corrida casual; resultados entram no !rankingnormal.\n"
                "• !f1rank: corrida oficial; exige uma temporada ativa e pontua no campeonato.\n"
                "• Os lobbies aceitam até 10 pilotos e podem incluir bots. O host configura voltas, circuito, clima e tempo de decisão.\n"
                "• É possível manter vários lobbies ativos. Eles expiram após 10 minutos sem iniciar. O criador usa !f1cancel; administradores podem usar !f1cancel @criador.\n\n"
                "**Entrar e preparar o carro**\n"
                "1. Clique em Entrar na corrida.\n"
                "2. Use Configurar carro para distribuir exatamente 10 pontos entre Gerenciamento de pneus, Curvas, Velocidade, Classificação, Motor e Controle.\n"
                "3. Escolha um composto em Escolher pneus e depois clique em Estou pronto.\n"
                "4. O host inicia a classificação e, em seguida, a corrida. A classificação define o grid de largada.\n\n"
                "**Durante a corrida**\n"
                "• Cada volta tem seis trechos de reta e curva. Em cada trecho, escolha uma ação no painel.\n"
                "• As decisões ficam ocultas até a etapa terminar. Se o tempo acabar, o bot escolhe Seguro automaticamente.\n"
                "• Consulte !sistema para ver o passo a passo dos botões."
            ),
            color=discord.Color.green(),
        ),
        discord.Embed(
            title="🎮 Guia de corrida — Pilotagem e carro",
            description=(
                "**Ações nas retas**\n"
                "• Manter ritmo: ritmo equilibrado e pequena recuperação de energia.\n"
                "• Defender posição: protege sua colocação, sacrificando um pouco de ritmo.\n"
                "• DRS / Ultrapassar: tenta passar o carro à frente quando está até 1 segundo dele; consome 12 de energia e não garante a manobra.\n"
                "• Boost Mode: consome 15 de energia para ganhar ritmo naquele trecho.\n\n"
                "**Ações nas curvas**\n"
                "• Por dentro: linha mais curta e rápida, mas com maior risco de contato.\n"
                "• Por fora: linha mais longa e com risco menor.\n"
                "• Defender a linha: protege posição, com pequena perda de ritmo.\n"
                "• Traçado seguro: sacrifica tempo para reduzir o risco de erro.\n\n"
                "**Pneus, clima e pit stop**\n"
                "• Soft é rápido e desgasta mais; Medium equilibra; Hard dura mais. Intermediate serve para pista úmida e Wet para chuva forte.\n"
                "• O desgaste afeta o tempo dos trechos. Gerenciamento de pneus reduz o desgaste.\n"
                "• Cada piloto tem o jogo inicial e uma troca de pneus. O pit stop normal custa cerca de 18s + equipe; parar cedo pode fazer perder posições.\n"
                "• Durante a janela do Safety Car, a parada cai para cerca de 6s + equipe. A vantagem termina quando a janela acaba.\n"
                "• O dano do carro aumenta o tempo dos trechos. No pit stop, escolha também reparar a asa: recupera até 30% de dano adicional e acrescenta 4 segundos à parada.\n"
                "• Mudanças de clima, derrapagens, acidentes e estouros de pneu são probabilísticos."
            ),
            color=discord.Color.blue(),
        ),
        discord.Embed(
            title="🏆 Guia de corrida — Pontuação e perfil",
            description=(
                "**Rankings**\n"
                "• Casual: 10, 8, 6, 5, 4, 3, 2 e 1 ponto(s) para as oito primeiras posições. Consulte !rankingnormal.\n"
                "• Oficial: 1º = 10, 2º = 7, 3º = 5, 4º = 3 e 5º = 1 ponto; +1 pela volta mais rápida se terminar no top 3.\n"
                "• Provas oficiais de até 3 voltas valem 50%; até 5 voltas, 75%; provas maiores, 100%. Abandono não pontua.\n"
                "• Corridas com menos de 3 jogadores humanos ou com bots em maioria não pontuam. Bots nunca recebem pontos.\n\n"
                "**Atributos**\n"
                "• Gerenciamento de pneus reduz desgaste. Curvas melhora trechos técnicos. Velocidade favorece retas. Classificação melhora o grid. Motor ajuda na aceleração. Controle melhora disputas e reduz erros.\n\n"
                "**Perfil e estilos**\n"
                "• !perfil mostra seu piloto. Em Configurar, altere nome, idade, equipe e foto. Em Distribuir pontos, os seis atributos devem somar exatamente 10.\n"
                "• Estilos e habilidades são únicos/equipados. Ao aceitar um novo estilo, ele substitui o anterior. Use !roll-estilo e !roll-habilidade para obter novos resultados.\n"
                "• !sistema abre o guia interativo completo; !comandos lista os comandos disponíveis."
            ),
            color=discord.Color.gold(),
        ),
    ]
    pages[0].set_footer(text="Página 1/3 • Começando")
    pages[1].set_footer(text="Página 2/3 • Pilotagem")
    pages[2].set_footer(text="Página 3/3 • Pontuação e perfil")
    try:
        await ctx.send(embeds=pages)
    except discord.HTTPException:
        await ctx.send("Não consegui enviar o guia em embeds. Use !sistema para abrir o guia interativo.")




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


async def expire_race_lobby(race):
    try:
        await asyncio.sleep(600)
        if not race_is_active(race) or race.race_started:
            return
        races.pop(race.race_id, None)
        if race.message:
            await race.message.edit(
                embed=lobby_embed(
                    race,
                    title="⌛ Lobby encerrado por inatividade",
                    description="A classificação e a corrida não foram iniciadas em até 10 minutos.",
                ),
                view=ClosedView(),
            )
        await race.channel.send("⌛ O lobby do criador <@" + str(race.host_id) + "> foi encerrado após 10 minutos sem iniciar a corrida.")
    except asyncio.CancelledError:
        return
    except discord.HTTPException:
        return


async def create_race_lobby(ctx, mode):
    guild_id = ctx.guild.id if ctx.guild else 0
    if mode == "ranked" and not season_for(guild_id):
        return await ctx.send("🏆 Não existe temporada ativa. Um administrador precisa usar !iniciartemporada nome antes de criar uma corrida oficial.")
    circuit_name = random.choice(list(CIRCUITS.keys()))
    weather_name = random.choice(list(WEATHER.keys()))
    weather = WEATHER[weather_name]
    race = Race(
        channel=ctx.channel,
        channel_id=ctx.channel.id,
        guild_id=guild_id,
        host_id=ctx.author.id,
        circuit_name=circuit_name,
        weather_name=weather_name,
        ambient_temp=random.randint(*weather["ambient"]),
        track_temp=random.randint(*weather["track"]),
        surface=weather["surface"],
        mode=mode,
        max_players=10,
    )
    races[race.race_id] = race
    preview = build_circuit_preview_file(race)
    race.message = await ctx.send(embed=lobby_embed(race), file=preview, view=LobbyView(race))
    race.lobby_timeout_task = asyncio.create_task(expire_race_lobby(race))


@bot.command(name="f1")
async def create_race(ctx):
    await create_race_lobby(ctx, "casual")


@bot.command(name="f1rank")
async def create_ranked_race(ctx):
    await create_race_lobby(ctx, "ranked")


@bot.command(name="f1status")
async def status_command(ctx, membro: Optional[discord.Member] = None):
    active = races_for_channel(ctx.channel.id)
    if membro:
        active = [race for race in active if race.host_id == membro.id]
    if not active:
        return await ctx.send("Não há lobby/corrida ativa correspondente neste canal.")
    if len(active) > 1:
        lines = [
            f"**{'🏆 Oficial' if race.mode == 'ranked' else '🏁 Casual'}** — criador <@{race.host_id}> • "
            f"{len(race.drivers)}/{race.max_players} pilotos • "
            f"{'corrida em andamento' if race.race_started else 'aguardando início'}"
            for race in active
        ]
        return await ctx.send(embed=discord.Embed(
            title="📋 Lobbies ativos neste canal",
            description="\n".join(lines) + "\n\nUse !f1status @criador para atualizar um painel específico.",
            color=discord.Color.blurple(),
        ))
    race = active[0]
    if race.race_started:
        embed = standings_embed(race, race.current_lap, f"segmento {race.current_segment}", [])
    elif race.qualifying_done:
        embed = qualifying_embed(race)
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


async def cancel_race_instance(race, reason):
    if race.lobby_timeout_task and not race.lobby_timeout_task.done():
        race.lobby_timeout_task.cancel()
    if race.race_task and not race.race_task.done():
        race.race_task.cancel()
    races.pop(race.race_id, None)
    if race.message:
        try:
            await race.message.edit(
                embed=lobby_embed(race, title="🛑 Corrida cancelada", description=reason),
                view=ClosedView(),
            )
        except discord.HTTPException:
            pass


@bot.command(name="f1cancel")
async def cancel_command(ctx, membro: Optional[discord.Member] = None):
    is_admin = bool(ctx.guild and ctx.author.guild_permissions.administrator)
    if membro:
        if not is_admin:
            return await ctx.send("Somente administradores podem cancelar a corrida de outro criador.")
        race = next(
            (
                active_race for active_race in reversed(list(races.values()))
                if active_race.guild_id == ctx.guild.id and active_race.host_id == membro.id
            ),
            None,
        )
        if not race:
            return await ctx.send(f"Não encontrei uma corrida ativa criada por {membro.mention} neste servidor.")
        await cancel_race_instance(race, f"Cancelada por um administrador a pedido da equipe. Criador: {membro.mention}.")
        return await ctx.send(f"🛑 Corrida criada por {membro.mention} cancelada pelo administrador.")
    race = race_for_channel(ctx.channel.id, host_id=ctx.author.id)
    if not race and is_admin:
        active = races_for_channel(ctx.channel.id)
        if len(active) == 1:
            race = active[0]
        elif len(active) > 1:
            return await ctx.send("Há vários lobbies ativos. Para escolher um, use !f1cancel @criador.")
    if not race:
        return await ctx.send("Não encontrei uma corrida sua neste canal. Administradores podem usar !f1cancel @criador.")
    await cancel_race_instance(race, f"Cancelada pelo criador <@{ctx.author.id}>.")
    await ctx.send("🛑 Sua corrida foi cancelada.")


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
