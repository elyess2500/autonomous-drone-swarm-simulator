"""
core/communication.py - Simulated inter-drone radio communication.

Features
--------
- Range-based connection matrix
- Relay routing through intermediate drones
- Signal-loss countdown & reconnection
- Shared exploration-map synchronisation
- Alert broadcast
"""

import math
import numpy as np
import config


class CommNode:
    """
    Communication state for a single drone.

    Each drone owns one CommNode.  The Swarm's CommManager wires them together.
    """

    def __init__(self, drone_id: int):
        self.drone_id         = drone_id
        self.connected_ids: set[int] = set()   # directly in-range peers
        self.relay_ids: set[int]     = set()   # reachable via relay
        self.frames_since_contact    = 0       # frames without any base contact
        self.signal_quality          = 1.0     # 0.0–1.0

        # Outgoing data queue (exploration diffs, alerts)
        self.outbox: list[dict] = []

    @property
    def is_connected(self) -> bool:
        """True if this drone has any path back to the base node."""
        return -1 in self.connected_ids or -1 in self.relay_ids

    @property
    def is_lost(self) -> bool:
        return self.frames_since_contact >= config.SIGNAL_LOSS_FRAMES

    def tick_disconnected(self):
        self.frames_since_contact += 1

    def reset_contact(self):
        self.frames_since_contact = 0

    def queue_message(self, msg_type: str, payload):
        self.outbox.append({"type": msg_type, "payload": payload, "from": self.drone_id})

    def flush_outbox(self) -> list[dict]:
        msgs = list(self.outbox)
        self.outbox.clear()
        return msgs


class CommManager:
    """
    Manages the inter-drone communication graph.

    Call `update(drones)` every few frames to rebuild connections.
    The base station is treated as node -1 at a fixed world position.
    """

    def __init__(self):
        self._range2 = config.DRONE_COMM_RANGE ** 2
        # Base position in pixels (world coords)
        bx = config.BASE_COL * config.CELL_SIZE + config.CELL_SIZE // 2
        by = config.BASE_ROW * config.CELL_SIZE + config.CELL_SIZE // 2
        self.base_px = (bx, by)

        # Current direct-link pairs for drawing
        self.active_links: list[tuple[int, int]] = []  # (drone_id_a, drone_id_b)
        self.relay_links:  list[tuple[int, int]] = []

        # Per-drone incoming messages this frame
        self._inbox: dict[int, list[dict]] = {}
        self.direct_graph: dict[int, set[int]] = {}
        self.reachable_ids: set[int] = set()
        self.disconnected_clusters: list[set[int]] = []
        self.weak_drone_ids: set[int] = set()
        self.connected_ratio: float = 1.0

    # ──────────────────────────────────────────
    # Main update
    # ──────────────────────────────────────────

    def update(self, drones: list):
        """
        Rebuild direct links, relay paths, and connection counters.
        Should be called every COMM_SYNC_INTERVAL frames (or every frame cheaply).
        """
        self.active_links.clear()
        self.relay_links.clear()
        self._inbox = {d.drone_id: [] for d in drones}

        # 1. Build direct-link matrix
        direct: dict[int, set[int]] = {}  # drone_id → set of directly connected drone_ids
        # Use sentinel id -1 for base station
        BASE = -1

        for d in drones:
            direct[d.drone_id] = set()
            # Check base
            dx = d.px - self.base_px[0]
            dy = d.py - self.base_px[1]
            if dx * dx + dy * dy <= self._range2:
                direct[d.drone_id].add(BASE)

        for i, da in enumerate(drones):
            for db in drones[i + 1:]:
                dx = da.px - db.px
                dy = da.py - db.py
                if dx * dx + dy * dy <= self._range2:
                    direct[da.drone_id].add(db.drone_id)
                    direct[db.drone_id].add(da.drone_id)
                    self.active_links.append((da.drone_id, db.drone_id))

        # 2. BFS from base to find all reachable drones via relay
        reachable: set = {BASE}
        queue = [BASE]
        parent: dict = {}

        # Build full adjacency including base
        adj: dict[int | str, set] = {BASE: set()}
        for d in drones:
            adj[d.drone_id] = direct[d.drone_id]
            if BASE in direct[d.drone_id]:
                adj[BASE].add(d.drone_id)

        head = 0
        while head < len(queue):
            node = queue[head]; head += 1
            for nb in adj.get(node, set()):
                if nb not in reachable:
                    reachable.add(nb)
                    parent[nb] = node
                    queue.append(nb)

        self.direct_graph = {d_id: set(peers) for d_id, peers in direct.items()}
        self.reachable_ids = {node for node in reachable if node != BASE}
        self.connected_ratio = len(self.reachable_ids) / max(1, len(drones))

        # 3. Update CommNodes
        for d in drones:
            node = d.comm

            node.connected_ids = direct[d.drone_id]

            # Relay-reachable = all reachable minus direct
            if d.drone_id in reachable:
                node.relay_ids = reachable - direct[d.drone_id] - {d.drone_id}
                node.reset_contact()
                # Signal quality decreases with distance to base
                dx = d.px - self.base_px[0]
                dy = d.py - self.base_px[1]
                dist = math.sqrt(dx * dx + dy * dy)
                node.signal_quality = max(0.1, 1.0 - dist / (config.DRONE_COMM_RANGE * 3))
            else:
                node.relay_ids = set()
                node.tick_disconnected()
                node.signal_quality = 0.0

        self.weak_drone_ids = {
            d.drone_id for d in drones
            if d.comm.signal_quality <= config.COMM_WEAK_SIGNAL_QUALITY or
            d.comm.frames_since_contact > 0
        }
        self.disconnected_clusters = self._build_disconnected_clusters(drones, reachable, direct, BASE)

        # 4. Relay links for visualisation
        for d_id, par in parent.items():
            if d_id != BASE and par != BASE:
                self.relay_links.append((d_id, par))

    def _build_disconnected_clusters(self, drones, reachable, direct, base_id):
        disconnected = {
            d.drone_id for d in drones
            if d.drone_id not in reachable
        }
        clusters: list[set[int]] = []
        seen: set[int] = set()
        for start in disconnected:
            if start in seen:
                continue
            stack = [start]
            cluster = set()
            seen.add(start)
            while stack:
                node = stack.pop()
                cluster.add(node)
                for nb in direct.get(node, set()):
                    if nb == base_id or nb not in disconnected or nb in seen:
                        continue
                    seen.add(nb)
                    stack.append(nb)
            clusters.append(cluster)
        return clusters

    def connectivity_snapshot(self, drones: list) -> dict:
        return {
            "connected": len(self.reachable_ids),
            "total": len(drones),
            "connected_ratio": self.connected_ratio,
            "weak": sorted(self.weak_drone_ids),
            "disconnected_clusters": [sorted(cluster) for cluster in self.disconnected_clusters],
            "active_links": list(self.active_links),
            "relay_links": list(self.relay_links),
        }

    # ──────────────────────────────────────────
    # Message passing
    # ──────────────────────────────────────────

    def broadcast(self, drones: list):
        """
        Flush each drone's outbox and deliver messages to all connected peers.
        Also synchronise fog-of-war arrays between connected drones.
        """
        # Collect all outgoing messages
        all_msgs: list[dict] = []
        for d in drones:
            all_msgs.extend(d.comm.flush_outbox())

        # Deliver to reachable drones
        for msg in all_msgs:
            src = msg["from"]
            for d in drones:
                if d.drone_id == src:
                    continue
                if src in d.comm.connected_ids or src in d.comm.relay_ids:
                    self._inbox[d.drone_id].append(msg)

        # Fog sync: merge explored cells among connected cluster
        # Group drones by connectivity cluster
        self._sync_fog(drones)

    def _sync_fog(self, drones):
        """
        For every pair of connected drones, OR their fog arrays together
        to simulate shared mapping data.
        """
        for i, da in enumerate(drones):
            for db in drones[i + 1:]:
                if (da.drone_id in db.comm.connected_ids or
                        da.drone_id in db.comm.relay_ids):
                    # Merge exploration
                    merged = da.map_known | db.map_known
                    da.map_known = merged.copy()
                    db.map_known = merged.copy()

    def get_inbox(self, drone_id: int) -> list[dict]:
        return self._inbox.get(drone_id, [])
