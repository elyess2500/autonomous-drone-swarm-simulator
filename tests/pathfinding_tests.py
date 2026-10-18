"""A* oracle checks and its explicit result/legacy-list contracts."""
import heapq
import math
import random

import pytest

import core.pathfinding as pf


class Grid:
    def __init__(self, n=10, blocked=()):
        self.n, self.blocked = n, set(blocked)

    def in_bounds(self, x, y):
        return 0 <= x < self.n and 0 <= y < self.n

    def is_passable(self, x, y):
        return self.in_bounds(x, y) and (x, y) not in self.blocked


AUDIT_BLOCKED = [(0,7),(0,9),(1,5),(1,8),(1,9),(3,3),(3,7),(4,1),
                 (4,3),(6,3),(6,5),(7,3),(7,5),(8,5),(9,1),(9,3)]
AUDIT_OCCUPIED = [(3,1),(4,4),(7,2),(8,0),(9,2)]


def edge_cost(a, b, occupied=(), bias=None, randomness=0):
    penalty = 8.0 if b in occupied else 0.0
    for c in occupied:
        d = abs(b[0]-c[0]) + abs(b[1]-c[1])
        penalty += 3.0 if d == 1 else 1.25 if d == 2 else 0.0
    direction = b[0]-a[0], b[1]-a[1]
    return math.dist(a,b) + penalty*(0.6+randomness) + (bias or {}).get(direction,0)


def dijkstra(grid, start, goal, occupied=(), bias=None, diagonal=True, randomness=0):
    dist = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        cost, node = heapq.heappop(heap)
        if cost != dist[node]:
            continue
        if node == goal:
            return cost
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if (dx,dy) == (0,0) or (not diagonal and dx and dy):
                    continue
                nxt = node[0]+dx, node[1]+dy
                if not grid.is_passable(*nxt):
                    continue
                if dx and dy and (not grid.is_passable(node[0]+dx,node[1]) or
                                  not grid.is_passable(node[0],node[1]+dy)):
                    continue
                new = cost + edge_cost(node,nxt,occupied,bias,randomness)
                if new < dist.get(nxt,math.inf):
                    dist[nxt] = new
                    heapq.heappush(heap,(new,nxt))
    return math.inf


def test_audit_stale_priority_counterexample():
    grid = Grid(blocked=AUDIT_BLOCKED)
    path = pf.find_path(grid,0,0,9,9,other_drone_positions=AUDIT_OCCUPIED)
    cost = sum(edge_cost(a,b,AUDIT_OCCUPIED) for a,b in zip(path,path[1:]))
    # Same saved map/costs; the oracle now also enforces Step 1's corner policy.
    assert cost == pytest.approx(dijkstra(grid,(0,0),(9,9),AUDIT_OCCUPIED))


def test_stale_priority_with_strict_corner_policy():
    blocked = [(0,5),(0,7),(1,1),(1,9),(2,0),(4,1),(4,3),(5,6),(5,9),
               (6,0),(7,0),(7,5),(8,3),(8,6),(8,8),(9,2),(9,8)]
    occupied = [(2,6),(6,3),(9,0)]
    grid = Grid(blocked=blocked)
    path = pf.find_path(grid,0,0,9,9,other_drone_positions=occupied)
    cost = sum(edge_cost(a,b,occupied) for a,b in zip(path,path[1:]))
    assert cost == pytest.approx(dijkstra(grid,(0,0),(9,9),occupied))


@pytest.mark.parametrize("diagonal", [False, True])
@pytest.mark.parametrize("variation", [0.0, 0.35])
def test_generated_maps_match_independent_dijkstra(diagonal, variation):
    rng = random.Random(761)
    directions = [(dx,dy) for dx in (-1,0,1) for dy in (-1,0,1) if dx or dy]
    bias = {direction: -0.04*variation*direction[0] for direction in directions}
    for _ in range(40):
        cells = [(x,y) for x in range(10) for y in range(10) if (x,y) not in ((0,0),(9,9))]
        blocked = {c for c in cells if rng.random() < .2}
        occupied = {c for c in cells if c not in blocked and rng.random() < .08}
        grid = Grid(blocked=blocked)
        path = pf.find_path(grid,0,0,9,9,allow_diagonal=diagonal,
                            other_drone_positions=list(occupied),direction_bias=bias,
                            randomness=variation,ai_seed=17)
        expected = dijkstra(grid,(0,0),(9,9),occupied,bias,diagonal,variation)
        actual = sum(edge_cost(a,b,occupied,bias,variation) for a,b in zip(path,path[1:])) if path else math.inf
        assert actual == pytest.approx(expected)


def test_explicit_result_and_legacy_compatibility():
    grid = Grid()
    result = pf.find_path_result(grid,0,0,3,3)
    assert result.status == "found"
    assert result.path == pf.find_path(grid,0,0,3,3)
    assert result.requested_goal == result.resolved_goal == (3,3)
    assert result.cost == pytest.approx(3*math.sqrt(2))
    assert result.expanded > 0


@pytest.mark.parametrize("start,goal,budget", [((-1,0),(3,3),10),((0,0),(10,3),10),
                                              ((0.5,0),(3,3),10),((0,0),(3,3),-1)])
def test_invalid_inputs_are_distinct(start, goal, budget):
    result = pf.find_path_result(Grid(),*start,*goal,max_iterations=budget)
    assert result.status == "invalid_input"
    assert not result.path


def test_unreachable_budget_and_fallback_results():
    separated = Grid(5,[(2,y) for y in range(5)])
    assert pf.find_path_result(separated,0,0,4,4).status == "unreachable"
    assert pf.find_path_result(Grid(),0,0,9,9,max_iterations=1).status == "budget_exhausted"
    same = pf.find_path_result(Grid(),1,1,1,1,max_iterations=0)
    assert same.status == "found" and same.cost == 0 and same.expanded == 0
    fallback = pf.find_path_result(Grid(blocked=[(3,3)]),0,0,3,3)
    assert fallback.status == "found"
    assert fallback.requested_goal == (3,3) and fallback.resolved_goal == (3,4)
    assert fallback.path[-1] == fallback.resolved_goal
    assert pf.find_path_result(Grid(blocked=[(0,0)]),0,0,3,3).status == "invalid_input"
    solid = Grid(20,[(x,y) for x in range(20) for y in range(20) if (x,y)!=(0,0)])
    no_fallback = pf.find_path_result(solid,0,0,19,19)
    assert no_fallback.status == "unreachable" and no_fallback.resolved_goal is None


def test_cost_validation_and_seeded_ties():
    for kwargs in [dict(direction_bias={(1,0):-1}),dict(randomness=float('nan')),
                   dict(comm_risk_weight=-1)]:
        assert pf.find_path_result(Grid(),0,0,3,3,**kwargs).status == "invalid_input"
    a = pf.find_path_result(Grid(),0,0,7,4,randomness=.35,ai_seed=42)
    b = pf.find_path_result(Grid(),0,0,7,4,randomness=.35,ai_seed=42)
    assert a == b
