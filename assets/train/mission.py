"""任务分配（多机器人 / 异构）+ 指标层。

设计原则：**分配算法可插拔**。
  - 输入：任务表、机器人表、代价矩阵（由 nav_grid.NavGrid 的 A* 生成）
  - 分配器：实现 `Dispatcher.assign()` 的一个类（贪心 / 拍卖 / DRL / LLM 都能塞）
  - 输出：指标（完成时间 / 完成率 / 总里程 / 负载均衡）

    python mission.py --dispatchers greedy,naive,marginal       # 对比不同分配器
    python mission.py --go2-slope 10 --g1-slope 5               # 改能力约束

注意：H1–H7 的 site 坐标都在建筑内部，A* 会自动吸附到外围可停车点，
所以「代价」是从机器人起点到**停车点**的路径长度。
"""
import argparse
import itertools
import math
import os
import random
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nav_grid import NavGrid, SITES  # noqa: E402


# ---------------------------------------------------------------- 数据结构
@dataclass
class Task:
    name: str
    pos: tuple
    service: float = 30.0          # 作业耗时（秒），到达后停留
    need_manip: bool = False       # 是否必须「能操作」的机器人（G1）
    priority: int = 1              # 1 普通 / 2 高


@dataclass
class Agent:
    name: str
    kind: str                      # go2 / g1
    start: tuple
    max_slope: float               # 可通行坡度上限（度）
    speed: float                   # 平均速度（m/s）
    can_manip: bool = False


@dataclass
class Result:
    name: str
    assignment: dict = field(default_factory=dict)
    makespan: float = float("inf")
    total_travel: float = 0.0
    done: int = 0
    total: int = 0
    balance: float = 0.0           # 里程标准差 / 均值（越小越均衡）
    unreachable: list = field(default_factory=list)


# ---------------------------------------------------------------- 代价模型
class CostModel:
    """把 NavGrid 的 A* 包装成「任意两点、按机器人能力」的代价查询，带缓存。"""

    def __init__(self, grid: NavGrid):
        self.g = grid
        self.cache = {}

    def cost(self, a: Agent, p0, p1):
        key = (round(p0[0], 2), round(p0[1], 2), round(p1[0], 2), round(p1[1], 2), a.max_slope)
        if key in self.cache:
            return self.cache[key]
        r, msg = self.g.plan(p0, p1, max_slope=a.max_slope,
                             slope_soft=min(a.max_slope, 10.0))
        if r is None:
            val = dict(length=float("inf"), travel=float("inf"), ok=False, why=msg)
        else:
            val = dict(length=r["length"], travel=r["length"] / a.speed, ok=True,
                       max_slope=r["max_slope"], sustained=r["sustained"], why="")
        self.cache[key] = val
        return val


# ---------------------------------------------------------------- 分配器接口
class Dispatcher:
    name = "base"

    def assign(self, agents, tasks, cm: CostModel) -> dict:
        """返回 {agent_name: [task_name, ...]}（按执行顺序）。"""
        raise NotImplementedError


class GreedyDispatcher(Dispatcher):
    """贪心：按优先级取任务，交给「当前最省时」的机器人（能力约束硬过滤）。"""

    name = "greedy"

    def assign(self, agents, tasks, cm):
        order = sorted(tasks, key=lambda t: (-t.priority, t.name))
        pos = {a.name: a.start for a in agents}
        load = {a.name: 0.0 for a in agents}
        out = {a.name: [] for a in agents}
        for t in order:
            best, best_cost = None, float("inf")
            for a in agents:
                if t.need_manip and not a.can_manip:
                    continue
                c = cm.cost(a, pos[a.name], t.pos)
                if not c["ok"]:
                    continue
                score = load[a.name] + c["travel"]
                if score < best_cost:
                    best, best_cost = a, score
            if best is None:
                continue
            c = cm.cost(best, pos[best.name], t.pos)
            out[best.name].append(t.name)
            pos[best.name] = t.pos
            load[best.name] += c["travel"] + t.service
        return out


class MarginalDispatcher(Dispatcher):
    """边际代价最小化（再粗糙版的「拍卖」）：每轮把「最贵的任务」分给边际代价最小的机器人。"""

    name = "marginal"

    def assign(self, agents, tasks, cm):
        remaining = list(tasks)
        pos = {a.name: a.start for a in agents}
        out = {a.name: [] for a in agents}
        while remaining:
            best = None
            for a in agents:
                for t in remaining:
                    if t.need_manip and not a.can_manip:
                        continue
                    c = cm.cost(a, pos[a.name], t.pos)
                    if not c["ok"]:
                        continue
                    if best is None or c["travel"] < best[2]:
                        best = (a, t, c["travel"])
            if best is None:
                break
            a, t, _ = best
            out[a.name].append(t.name)
            pos[a.name] = t.pos
            remaining.remove(t)
        return out


class NaiveDispatcher(Dispatcher):
    """基线：随机把任务均分给机器人（不看代价，只做能力过滤）—— 用来证明「不看代价会差多少」。"""

    name = "naive"

    def assign(self, agents, tasks, cm):
        rng = random.Random(0)
        out = {a.name: [] for a in agents}
        for t in tasks:
            cand = [a for a in agents if (not t.need_manip) or a.can_manip]
            if not cand:
                continue
            rng.choice(cand)
            # 优先塞给任务数最少的候选，避免极端不均
            a = min(cand, key=lambda x: len(out[x.name]))
            out[a.name].append(t.name)
        return out


# ---------------------------------------------------------------- 指标
def evaluate(res: Result, agents, tasks, cm):
    tmap = {t.name: t for t in tasks}
    travels, makespans = [], []
    reached, unreachable = set(), []
    for a in agents:
        route = res.assignment.get(a.name, [])
        pos, tt, tv = a.start, 0.0, 0.0
        for name in route:
            t = tmap[name]
            c = cm.cost(a, pos, t.pos)
            if not c["ok"]:            # 分配了但到不了 → 计为不可达，不推进位置
                unreachable.append("%s@%s" % (name, a.name))
                continue
            tv += c["length"]
            tt += c["travel"] + t.service
            pos = t.pos
            reached.add(name)
        travels.append(tv)
        makespans.append(tt)
    res.unreachable = unreachable
    res.makespan = max(makespans) if makespans else 0.0
    res.total_travel = sum(travels)
    res.done = len(reached)
    res.total = len(tasks)
    mu = sum(travels) / len(travels) if travels else 0.0
    if mu > 0:
        var = sum((x - mu) ** 2 for x in travels) / len(travels)
        res.balance = math.sqrt(var) / mu
    return res


DISPATCHERS = {d.name: d for d in (GreedyDispatcher(), MarginalDispatcher(), NaiveDispatcher())}


def build_world(args):
    tasks = [
        Task("H1", SITES["H1"], service=40, need_manip=True, priority=2),   # 需操作（救人）
        Task("H2", SITES["H2"], service=30),
        Task("H3", SITES["H3"], service=30),
        Task("H4", SITES["H4"], service=30),
        Task("H5", SITES["H5"], service=30),
        Task("H6", SITES["H6"], service=40, need_manip=True, priority=2),   # 需操作
        Task("H7", SITES["H7"], service=20),
    ]
    agents = [
        Agent("go2", "go2", (1.0, -20.0), max_slope=args.go2_slope, speed=0.35, can_manip=False),
        Agent("g1", "g1", (0.0, -17.5), max_slope=args.g1_slope, speed=0.25, can_manip=True),
    ]
    return tasks, agents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dispatchers", default="greedy,marginal,naive")
    ap.add_argument("--go2-slope", type=float, default=15.0)
    ap.add_argument("--g1-slope", type=float, default=10.0)
    ap.add_argument("--res", type=float, default=1.0)
    ap.add_argument("--radius", type=float, default=0.35)
    a = ap.parse_args()

    grid = NavGrid(res=a.res, robot_radius=a.radius)
    cm = CostModel(grid)
    tasks, agents = build_world(a)

    print("栅格 %dx%d，障碍 %.1f%%，坡度中位 %.1f°"
          % (grid.n, grid.n, 100 * grid.blocked.mean(), float(__import__("numpy").median(grid.slope))))
    print("机器人：%s" % ", ".join("%s(坡度≤%.0f°, %.2f m/s, 可操作=%s)"
                                   % (x.name, x.max_slope, x.speed, x.can_manip) for x in agents))
    print()

    # 先打印「机器人 × 任务」可达性（这是异构约束的直接体现）
    print("可达性 / 单程路径长（m）：")
    print("  %-10s %8s %8s" % ("task", "go2", "g1"))
    for t in tasks:
        row = []
        for ag in agents:
            c = cm.cost(ag, ag.start, t.pos)
            row.append("%.1f" % c["length"] if c["ok"] else "×")
        flag = " [需操作]" if t.need_manip else ""
        print("  %-10s %8s %8s%s" % (t.name, row[0], row[1], flag))
    print()

    print("%-9s %7s %7s %8s %8s %8s %8s  %s"
          % ("分配器", "完成", "不可达", "总里程", "完工时间", "负载均衡", "完成率", "分配方案"))
    for name in a.dispatchers.split(","):
        d = DISPATCHERS.get(name.strip())
        if d is None:
            print("  未知分配器:", name)
            continue
        res = Result(name=d.name, assignment=d.assign(agents, tasks, cm))
        evaluate(res, agents, tasks, cm)
        plan = "; ".join("%s:%s" % (k, "→".join(v) if v else "-")
                         for k, v in res.assignment.items())
        ms = "—" if math.isinf(res.makespan) else "%.0fs" % res.makespan
        print("%-9s %3d/%-3d %7d %7.1fm %8s %8.2f %7.0f%%  %s"
              % (res.name, res.done, res.total, len(res.unreachable),
                 res.total_travel, ms, res.balance,
                 100.0 * res.done / res.total, plan))


if __name__ == "__main__":
    main()
