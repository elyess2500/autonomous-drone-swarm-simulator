"""Route forecasts in abstract charge units; neither physics nor a guarantee.

Only terrain routes are cached. Current planned work geometry takes precedence.
Mixed-wind segments use the slower speed/higher rate for the whole segment.
Forecasts exclude future traffic, future weather and future communication detours.
"""
from collections import OrderedDict
from dataclasses import dataclass, asdict
import math
from core.experiment import settings as config
from core.battery import Battery
from core.geometry import segment_is_clear, swept_cells
from core.pathfinding import find_path, smooth_path
from core import map as terrain_model


_MAP_METHODS = tuple((name, getattr(terrain_model.Map, name)) for name in
                     ('in_bounds', 'is_passable', 'is_wind', 'cell_to_pixel'))


@dataclass(frozen=True)
class EnergyEstimate:
    outbound: float
    returning: float
    work: float
    uncertainty: float
    reserve: float

    @property
    def total(self):
        return self.outbound + self.returning + self.work + self.uncertainty + self.reserve

    def snapshot(self):
        return {k: v if math.isfinite(v) else None
                for k, v in dict(**asdict(self), total=self.total).items()}


def route_energy(world, start, route, activity, weather='Clear'):
    """Predict per-state drain over executable sparse waypoint geometry.

    One tick per zero-length waypoint, ceil(distance/speed) otherwise. A mixed
    segment's full length uses its worst wind speed/rate: deliberately an upper
    approximation, not exact execution timing at a wind boundary.
    """
    total = 0.0
    for cell in route:
        end = world.cell_to_pixel(*cell)
        scale = config.CELL_SIZE
        if not segment_is_clear(world, (start[0]/scale, start[1]/scale),
                                (end[0]/scale, end[1]/scale)):
            return math.inf
        windy = any(world.is_wind(*c) for c in swept_cells(start, end))
        speed = min(config.DRONE_SPEED, config.DRONE_SPEED_WIND) if windy else config.DRONE_SPEED
        if speed <= 0:
            return math.inf
        ticks = max(1, math.ceil(math.dist(start, end)/speed - 1e-12))
        total += ticks * Battery.drain_per_tick(activity, weather == 'Stormy', windy)
        start = end
    return total


class EnergyPolicy:
    """Per-agent bounded route reuse and detached decision diagnostics.

    Query mode neither fills the cache nor increments diagnostics/events. Only
    policy assessment searches pass through the existing counted planner hook.
    Terrain bytes detect direct grid edits as well as normal immutable terrain.
    """
    def __init__(self, drone):
        self.drone = drone
        self.routes = OrderedDict()
        self.terrain = None
        self.checks = self.rejections = self.searches = 0
        self.last = None
        self._cost_context = None
        self._cost_cache = OrderedDict()

    def _route_cost(self, world, start, route, activity, weather, record):
        """Memoize only pure geometry/drain, preserving every policy assessment.

        FIFO bound: 1024 results per agent. Exact geometry/activity/weather keys
        live within a terrain/config context. Battery, work, reserve and decision
        side effects remain outside. Queries may read but never mutate this cache.
        Custom map geometry bypasses it because its hidden inputs are unknown.
        """
        if (type(world) is not terrain_model.Map or any(
                getattr(getattr(world, name), '__func__', None) is not method
                for name, method in _MAP_METHODS)):
            return route_energy(world, start, route, activity, weather)
        context = (world, world.rows, world.cols, world.grid.shape,
                   world.grid.dtype.str, world.grid.tobytes(),
                   terrain_model.CELL_OBSTACLE, terrain_model.CELL_NOFLY,
                   terrain_model.CELL_WIND, config.CELL_SIZE,
                   config.DRONE_SPEED, config.DRONE_SPEED_WIND,
                   config.BATTERY_MOVE_DRAIN, config.BATTERY_SCAN_DRAIN,
                   config.BATTERY_IDLE_DRAIN, config.STORM_EXTRA_DRAIN,
                   route_energy, segment_is_clear, swept_cells, Battery.drain_per_tick)
        key = (tuple(start), tuple(route), activity, weather)
        if context == self._cost_context:
            if key in self._cost_cache:
                return self._cost_cache[key]
        elif record:
            self._cost_cache.clear()
            self._cost_context = context
        result = route_energy(world, start, route, activity, weather)
        if record:
            self._cost_cache[key] = result
            if len(self._cost_cache) > 1024:
                self._cost_cache.popitem(last=False)
        return result

    def snapshot(self):
        import copy
        return dict(version=1, checks=self.checks, rejections=self.rejections,
                    route_searches=self.searches, last=copy.deepcopy(self.last),
                    ready_at_base=getattr(self.drone, '_ready_at_base', False))

    def route(self, start, end, record):
        d = self.drone
        terrain = d.game_map.grid.tobytes()
        key = (start, end, d.ai_seed, tuple(sorted(d.direction_bias.items())),
               d._smooth_max_segment, config.AI_RANDOMNESS)
        if terrain == self.terrain and key in self.routes:
            return self.routes[key]
        if record and terrain != self.terrain:
            self.routes.clear()
            self.terrain = terrain
        if record:
            self.searches += 1
        search = d._search_path if record else find_path
        raw = search(d.game_map, *start, *end, ai_seed=d.ai_seed,
                     drone_id=d.drone_id, direction_bias=d.direction_bias,
                     randomness=config.AI_RANDOMNESS)
        # The planner's compatibility fallback does not prove this goal reachable.
        route = tuple(smooth_path(d.game_map, raw, d._smooth_max_segment)) if raw and raw[-1] == end else ()
        if record:
            self.routes[key] = route
            if len(self.routes) > 512:
                self.routes.popitem(last=False)
        return route

    def estimate(self, target=None, *, record=False, hold_ticks=None, from_cell=None):
        d = self.drone
        world = d.game_map
        weather = getattr(d, '_energy_weather', 'Clear')
        start = (d.px, d.py)
        origin = d.cell
        if from_cell is not None:
            origin = tuple(from_cell)
            start = world.cell_to_pixel(*origin)
        outbound = work = 0.0
        if target is not None:
            target = tuple(target)
            route = self.execution_route(target, record)
            outbound = self._route_cost(world, start, route, 'scanning', weather, record) if route else math.inf
            start = world.cell_to_pixel(*target)
            origin = target
            ticks = config.DRONE_SCAN_INTERVAL if hold_ticks is None else hold_ticks
            work = ticks * Battery.drain_per_tick('scanning' if hold_ticks is None else 'idle',
                                                  weather == 'Stormy', world.is_wind(*target))
        # Conservatively price travel to the lane and then the base center even
        # when execution can dock earlier inside the shared physical disk.
        if math.dist(start, d.base_px) <= config.BASE_DOCKING_RADIUS_PX:
            returning = 0.0
        else:
            lane = tuple(d.base_target_cell)
            route = (self.execution_route(lane, record) if target is None and from_cell is None
                     else self.route(origin, lane, record))
            returning = self._route_cost(world, start, route, 'returning', weather, record) if route else math.inf
            center = (config.BASE_COL, config.BASE_ROW)
            if lane != center:
                tail = self.route(lane, center, record)
                returning += self._route_cost(world, world.cell_to_pixel(*lane), tail, 'returning', weather, record) if tail else math.inf
        predicted = outbound + returning + work
        uncertainty = predicted * max(0.0, config.BATTERY_PATH_INEFFICIENCY - 1) if math.isfinite(predicted) else math.inf
        result = EnergyEstimate(outbound, returning, work, uncertainty, config.BATTERY_TASK_RESERVE)
        if record:
            self.checks += 1
            feasible = math.isfinite(result.total) and d.battery.level >= result.total
            self.last = dict(target=list(target) if target else None, weather=weather,
                             battery=d.battery.level, feasible=feasible,
                             margin=d.battery.level-result.total if math.isfinite(result.total) else None,
                             reason='route unavailable' if not math.isfinite(result.total) else
                                    ('reserve deficit' if not feasible else 'feasible'),
                             estimate=result.snapshot())
            if not feasible:
                self.rejections += 1
        return result

    def execution_route(self, target, record):
        d = self.drone
        yielding = getattr(d, '_yield_target', None)
        if yielding is not None:
            # Execution clears the old path and replans on sidestep arrival.
            tail = self.route(tuple(yielding), target, record)
            return (tuple(yielding),) + tail if tail else ()
        if d.has_path() and d.path[-1] == target:
            return tuple(d.path[d.waypoint_idx:])
        return self.route(d.cell, target, record)
