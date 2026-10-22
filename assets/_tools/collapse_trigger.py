"""Timed/grouped release of collapse structures.

Convention: a collapsible body is named collapse_<group>_<index> and carries a
freejoint plus an equality weld with the same name (or weld_<body name>).
Releasing a group sets data.eq_active[eq_id] = 0 so gravity takes over.
"""
import mujoco


class CollapseTrigger:
    def __init__(self, model, data, schedule=None):
        self.model = model
        self.data = data
        self.schedule = schedule or {}
        self.groups = {}
        self.released = set()
        self._scan()

    def _scan(self):
        for body_id in range(self.model.nbody):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            if not name or not name.startswith("collapse_"):
                continue
            parts = name.split("_")
            group = parts[1] if len(parts) > 1 else "default"
            eq_id = self._find_weld(name)
            self.groups.setdefault(group, []).append((body_id, eq_id))

    def _find_weld(self, body_name):
        for eq_id in range(self.model.neq):
            eq_name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_EQUALITY, eq_id)
            if eq_name in (body_name, f"weld_{body_name}"):
                return eq_id
        return -1

    def release(self, group):
        count = 0
        for _, eq_id in self.groups.get(group, []):
            if eq_id >= 0:
                self.data.eq_active[eq_id] = 0
                count += 1
        return count

    def step(self):
        t = self.data.time
        fired = []
        for group, times in self.schedule.items():
            for i, t0 in enumerate(times):
                key = (group, i)
                if key not in self.released and t >= t0:
                    self.release(group)
                    self.released.add(key)
                    fired.append((group, t0))
        return fired
