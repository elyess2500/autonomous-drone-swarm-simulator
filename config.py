"""
config.py - Central configuration for the Autonomous Drone Swarm Simulator.
All tunable parameters are defined here to keep the rest of the code clean.
"""

# ──────────────────────────────────────────────
# WINDOW & DISPLAY
# ──────────────────────────────────────────────
WINDOW_TITLE   = "Autonomous Drone Swarm Simulator"
SCREEN_WIDTH   = 1400
SCREEN_HEIGHT  = 850
TARGET_FPS     = 60

# ──────────────────────────────────────────────
# MAP / GRID
# ──────────────────────────────────────────────
CELL_SIZE      = 14          # pixels per grid cell
MAP_COLS       = 72          # grid columns
MAP_ROWS       = 52          # grid rows
MAP_PIXEL_W    = MAP_COLS * CELL_SIZE   # 1008
MAP_PIXEL_H    = MAP_ROWS * CELL_SIZE   # 728

MAP_OFFSET_X   = 10          # left margin inside window
MAP_OFFSET_Y   = 60          # top margin (leaves room for title bar)

# ──────────────────────────────────────────────
# TERRAIN GENERATION
# ──────────────────────────────────────────────
OBSTACLE_DENSITY      = 0.12   # fraction of cells that are obstacles
NOFLY_ZONE_COUNT      = 3      # number of no-fly zones
NOFLY_ZONE_RADIUS     = 4      # cells
THREAT_ZONE_COUNT     = 2
THREAT_ZONE_RADIUS    = 5
WIND_ZONE_COUNT       = 4
WIND_ZONE_RADIUS      = 6
MISSION_ZONE_COUNT    = 5      # search-and-rescue target zones
QUICK_DEMO_MODE       = False  # True = faster demo mission with fewer/easier survivors
DEMO_MISSION_ZONE_COUNT = 2
AUTONOMOUS_OFFLINE_MODE = True

# ──────────────────────────────────────────────
# BASE STATION
# ──────────────────────────────────────────────
BASE_COL       = 3
BASE_ROW       = 3
BASE_RADIUS_PX = 16            # visual radius in pixels
BASE_DOCKING_RADIUS_PX = BASE_RADIUS_PX + CELL_SIZE  # charging allowed only inside this radius

# ──────────────────────────────────────────────
# DRONE PARAMETERS
# ──────────────────────────────────────────────
NUM_DRONES            = 8
DRONE_SPEED           = 1.8            # pixels per frame (normal)
DRONE_SPEED_WIND      = 0.9            # reduced speed in wind zones
DRONE_RADIUS          = 6              # visual radius
DRONE_SENSOR_RADIUS   = 3             # cells revealed per scan step
DRONE_COMM_RANGE      = 180            # pixels communication range
DRONE_SCAN_INTERVAL   = 12            # frames between scan ticks
SURVIVOR_DETECTION_BONUS = 3           # cells beyond survivor radius
DEMO_SURVIVOR_DETECTION_BONUS = 8      # extra generous demo detection

# ──────────────────────────────────────────────
# BATTERY
# ──────────────────────────────────────────────
BATTERY_MAX           = 100.0
BATTERY_IDLE_DRAIN    = 0.008          # per frame while idle / charging
BATTERY_MOVE_DRAIN    = 0.030          # per frame while moving
BATTERY_SCAN_DRAIN    = 0.012          # per frame while scanning
BATTERY_LOW_THRESH    = 35.0           # trigger return-to-base
BATTERY_CRITICAL      = 10.0           # emergency alert
BATTERY_CHARGE_RATE   = 0.75           # per frame at base
BATTERY_RELAUNCH_THRESH = 85.0         # relaunch only after safe recharge
BATTERY_EMERGENCY_CHARGE_RATE = 2.0    # used when entire swarm is stalled
BATTERY_TASK_RESERVE = 18.0            # safety reserve after target + return estimate
BATTERY_PATH_INEFFICIENCY = 1.45       # multiplier for path detours/wind/avoidance

# ──────────────────────────────────────────────
# PATHFINDING
# ──────────────────────────────────────────────
PATH_WAYPOINT_DIST    = CELL_SIZE * 1  # distance to consider waypoint reached
REROUTE_INTERVAL      = 120            # frames between forced reroute checks

# ──────────────────────────────────────────────
# COMMUNICATION
# ──────────────────────────────────────────────
COMM_SYNC_INTERVAL    = 30             # frames between data-sync broadcasts
SIGNAL_LOSS_FRAMES    = 180            # frames before drone is "lost"
LOST_COMM_RETARGET_INTERVAL = 60       # frames between lost-comm recovery target updates
LOST_COMM_TIMEOUT_FRAMES = 360         # force base-directed recovery after this many lost frames
OFFLINE_SCAN_PROGRESS_LIMIT = 200      # retained local scan/path events while disconnected
COMM_RELAY_FRACTION = 0.18             # fraction of swarm biased toward relay anchoring
COMM_MIN_RELAY_ANCHORS = 1             # minimum relay nodes held in large searches
COMM_MAX_RELAY_ANCHORS = 3             # cap relay anchors so explorers keep pushing outward
COMM_RELAY_SAFE_RANGE = 0.82           # relay spacing as fraction of radio range
COMM_WEAK_SIGNAL_QUALITY = 0.38        # below this, trigger mesh repair behavior
COMM_MIN_CONNECTED_RATIO = 0.65        # watchdog target for connected drones
COMM_FRONTIER_MAX_RISK = 24.0          # reject frontier bids above this comm risk
COMM_EXPLORER_OFFLINE_RISK_BONUS = 16.0 # extra bounded risk for battery-safe offline explorers
COMM_RELAXATION_RISK_BONUS = 20.0      # temporary risk allowance when coverage stalls
COMM_FRONTIER_RISK_WEIGHT = 0.9        # bid penalty for comm-risky frontiers
COMM_PATH_RISK_WEIGHT = 1.2            # A* cost penalty for paths outside mesh cover
COMM_MESH_REPAIR_INTERVAL = 45         # frames between relay/mesh repair passes
COMM_RELAY_ANCHOR_HOLD_FRAMES = 150    # minimum anchor hold duration before reassignment
COMM_RELAXATION_START_FRAMES = 240     # stalled frames before comm-risk constraints soften
COMM_RELAXATION_STEP = 0.16            # per-second relaxation increase while stalled
COMM_RELAXATION_DECAY = 0.05           # per-second relaxation decay while expanding
COMM_MAX_OFFLINE_EXPLORERS = 3         # controlled-risk explorers allowed to leave mesh

# ──────────────────────────────────────────────
# SWARM INTELLIGENCE
# ──────────────────────────────────────────────
SECTOR_ROWS           = 4
SECTOR_COLS           = 6
REBALANCE_INTERVAL    = 300            # frames between sector rebalancing

# ──────────────────────────────────────────────
# WEATHER / WIND
# ──────────────────────────────────────────────
WEATHER_CHANGE_INTERVAL = 900          # frames between weather shifts
WEATHER_TYPES = ["Clear", "Cloudy", "Windy", "Stormy"]
STORM_EXTRA_DRAIN = 0.015              # extra battery drain during storm

# ──────────────────────────────────────────────
# RANDOM FAILURES
# ──────────────────────────────────────────────
FAILURE_PROB_PER_FRAME = 0.00008       # per-drone per-frame failure chance
FAILURE_RECOVERY_FRAMES = 240          # frames to auto-recover

# ──────────────────────────────────────────────
# REPLAY
# ──────────────────────────────────────────────
REPLAY_RECORD_INTERVAL = 6             # frames between snapshot saves
REPLAY_MAX_FRAMES      = 18000         # ~5 min at 60 fps

# Reproducible AI variation. None keeps the existing "new random map on
# restart" behavior; set to an int to replay the same terrain and drone choices.
RANDOM_SEED           = None

# 0.0 = almost deterministic legacy behavior, 1.0 = stronger path/queue
# diversity. Kept modest so drones still look purposeful.
AI_RANDOMNESS         = 0.35

# Decentralized frontier negotiation. Drones compute bids locally; the swarm
# resolves competing claims so the existing single-process simulator stays stable.
FRONTIER_REFRESH_INTERVAL = 45
TASK_NEGOTIATION_INTERVAL = 90
MAX_FRONTIERS             = 48
FRONTIER_CLUSTER_RADIUS   = 2
FRONTIER_INFO_RADIUS      = 4
FRONTIER_MIN_BID          = 1.0
EXPLORATION_STALL_FRAMES  = 600
EXPLORATION_MIN_GROWTH_PER_MIN = 0.035 # below this, loosen comm constraints
FRONTIER_EXPANSION_WEIGHT = 1.1        # reward frontiers that extend search radius
FRONTIER_DIRECTION_WEIGHT = 6.0        # give drones reproducible direction preferences
FRONTIER_SPREAD_RADIUS = 11            # discourage multiple drones choosing one corridor
FRONTIER_SPREAD_PENALTY = 2.0          # penalty per crowded frontier cell
FRONTIER_WORK_CELL_LIMIT = 20          # local scan packet size around assigned frontiers

# Reservation-table collision avoidance. Reservations are soft constraints:
# pathfinding strongly avoids them but can still pass through narrow corridors.
RESERVATION_HORIZON       = 24
RESERVATION_CELL_PENALTY  = 10.0
RESERVATION_EDGE_PENALTY  = 7.0

# Stuck recovery.
STUCK_PROGRESS_EPS        = 1.2
STUCK_WARN_FRAMES         = 90
STUCK_REROUTE_FRAMES      = 150
STUCK_REASSIGN_FRAMES     = 260

# Analytics/export paths.
METRICS_LOG_DIR           = "logs"
REPLAY_EXPORT_DIR         = "replays"

# ──────────────────────────────────────────────
# COLORS  (R, G, B)
# ──────────────────────────────────────────────
C_BG               = (10,  12,  20)
C_GRID             = (20,  28,  40)
C_FOG              = (8,   10,  18)
C_SCANNED          = (18,  28,  45)
C_OBSTACLE         = (60,  65,  80)
C_NOFLY            = (120, 30,  30)
C_THREAT           = (140, 60,  10)
C_WIND             = (20,  60,  110)
C_MISSION_ZONE     = (20,  100, 60)
C_BASE             = (255, 210, 50)
C_PATH             = (0,   160, 220)
C_COMM_LINK        = (0,   200, 120)
C_SENSOR_RING      = (0,   180, 255)
C_HEATMAP_LOW      = (0,   50,  120)
C_HEATMAP_HIGH     = (220, 30,  30)

# Drone state colors
C_STATE_IDLE       = (160, 160, 200)
C_STATE_SCANNING   = (0,   220, 180)
C_STATE_RETURNING  = (255, 180, 0)
C_STATE_CHARGING   = (0,   255, 80)
C_STATE_AVOIDING   = (255, 100, 0)
C_STATE_LOST       = (200, 0,   50)
C_STATE_FAILED     = (100, 0,   0)
C_STATE_STRANDED   = (170, 80,  20)

# UI
C_UI_BG            = (14,  18,  30)
C_UI_PANEL         = (20,  26,  42)
C_UI_BORDER        = (40,  55,  85)
C_UI_TEXT          = (200, 210, 230)
C_UI_ACCENT        = (0,   190, 255)
C_UI_WARN          = (255, 180, 0)
C_UI_DANGER        = (255, 60,  60)
C_UI_OK            = (0,   220, 120)

# ──────────────────────────────────────────────
# FONTS
# ──────────────────────────────────────────────
FONT_MONO_SM  = 11
FONT_MONO_MD  = 13
FONT_MONO_LG  = 16
FONT_TITLE    = 20
