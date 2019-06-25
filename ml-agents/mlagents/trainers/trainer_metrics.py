# # Unity ML-Agents Toolkit
import logging
import csv
from time import time, perf_counter

from contextlib import contextmanager
from typing import Any, Dict
import json

LOGGER = logging.getLogger("mlagents.trainers")
FIELD_NAMES = [
    "Brain name",
    "Time to update policy",
    "Time since start of training",
    "Time for last experience collection",
    "Number of experiences used for training",
    "Mean return",
]


class TrainerMetrics:
    """
        Helper class to track, write training metrics. Tracks time since object
        of this class is initialized.
    """

    def __init__(self, path: str, brain_name: str):
        """
        :str path: Fully qualified path where CSV is stored.
        :str brain_name: Identifier for the Brain which we are training
        """
        self.path = path
        self.brain_name = brain_name
        self.rows = []
        self.time_start_experience_collection = None
        self.time_training_start = time()
        self.last_buffer_length = None
        self.last_mean_return = None
        self.time_policy_update_start = None
        self.delta_last_experience_collection = None
        self.delta_policy_update = None

    def start_experience_collection_timer(self):
        """
        Inform Metrics class that experience collection is starting. Intended to be idempotent
        """
        if self.time_start_experience_collection is None:
            self.time_start_experience_collection = time()

    def end_experience_collection_timer(self):
        """
        Inform Metrics class that experience collection is done.
        """
        if self.time_start_experience_collection:
            curr_delta = time() - self.time_start_experience_collection
            if self.delta_last_experience_collection is None:
                self.delta_last_experience_collection = curr_delta
            else:
                self.delta_last_experience_collection += curr_delta
        self.time_start_experience_collection = None

    def add_delta_step(self, delta: float):
        """
        Inform Metrics class about time to step in environment.
        """
        if self.delta_last_experience_collection:
            self.delta_last_experience_collection += delta
        else:
            self.delta_last_experience_collection = delta

    def start_policy_update_timer(self, number_experiences: int, mean_return: float):
        """
        Inform Metrics class that policy update has started.
        :int number_experiences: Number of experiences in Buffer at this point.
        :float mean_return: Return averaged across all cumulative returns since last policy update
        """
        self.last_buffer_length = number_experiences
        self.last_mean_return = mean_return
        self.time_policy_update_start = time()

    def _add_row(self, delta_train_start):
        row = [self.brain_name]
        row.extend(
            format(c, ".3f") if isinstance(c, float) else c
            for c in [
                self.delta_policy_update,
                delta_train_start,
                self.delta_last_experience_collection,
                self.last_buffer_length,
                self.last_mean_return,
            ]
        )
        self.delta_last_experience_collection = None
        self.rows.append(row)

    def end_policy_update(self):
        """
        Inform Metrics class that policy update has started.
        """
        if self.time_policy_update_start:
            self.delta_policy_update = time() - self.time_policy_update_start
        else:
            self.delta_policy_update = 0
        delta_train_start = time() - self.time_training_start
        LOGGER.debug(
            " Policy Update Training Metrics for {}: "
            "\n\t\tTime to update Policy: {:0.3f} s \n"
            "\t\tTime elapsed since training: {:0.3f} s \n"
            "\t\tTime for experience collection: {:0.3f} s \n"
            "\t\tBuffer Length: {} \n"
            "\t\tReturns : {:0.3f}\n".format(
                self.brain_name,
                self.delta_policy_update,
                delta_train_start,
                self.delta_last_experience_collection,
                self.last_buffer_length,
                self.last_mean_return,
            )
        )
        self._add_row(delta_train_start)

    def write_training_metrics(self):
        """
        Write Training Metrics to CSV
        """
        with open(self.path, "w") as file:
            writer = csv.writer(file)
            writer.writerow(FIELD_NAMES)
            for row in self.rows:
                writer.writerow(row)

        json_path = self.path.replace('csv', 'hierarchy.json')
        with open(json_path, 'w') as file:
            json.dump(get_timer_tree(), file, indent=2)


class TimerNode:
    __slots__ = ["children", "_start_time", "total", "count"]

    def __init__(self):
        self.children: Dict[str, 'TimerNode'] = {}
        self._start_time: float = -1.0
        self.total: float = 0.0
        self.count: int = 0

    def _start(self):
        assert not self._is_running(), "calling start() on an already-running timer"
        self._start_time = perf_counter()

    def _end(self):
        assert self._is_running(), "calling _end on a stopped timer"
        elapsed = perf_counter() - self._start_time
        self.total += elapsed
        self.count += 1
        self._start_time = -1.0

    def _is_running(self):
        return self._start_time != -1.0


class TimerStack:
    __slots__ = ["root", "stack"]

    def __init__(self):
        self.root = TimerNode()
        self.root._start()
        self.stack = [self.root]

    def push(self, name):
        current: TimerNode = self.stack[-1]
        next_timer = current.children.get(name)
        if next_timer is None:
            next_timer = TimerNode()
            current.children[name] = next_timer
        self.stack.append(next_timer)
        return next_timer

    def pop(self):
        self.stack.pop()

    def get_timing_tree(self, node: TimerNode = None) -> Dict[str, Any]:
        if node is None:
            self.root._end()
            node = self.root

        res = {
            "total": node.total,
            "count": node.count,
        }

        child_total = 0.0
        if node.children:
            res["children"] = []
            for child_name, child_node in node.children.items():
                child_res = {"name": child_name, **self.get_timing_tree(child_node)}
                res["children"].append(child_res)
                child_total += child_res["total"]

        # "self" time is total time minus all time spent on children
        res["self"] = max(0.0, node.total - child_total)

        return res


_global_timer_stack = TimerStack()


@contextmanager
def hierarchical_timer(name, timer_stack=_global_timer_stack):
    next_timer: TimerNode = timer_stack.push(name)
    next_timer._start()
    yield next_timer
    next_timer._end()
    timer_stack.pop()

def get_timer_tree(timer_stack=_global_timer_stack):
    return timer_stack.get_timing_tree()


