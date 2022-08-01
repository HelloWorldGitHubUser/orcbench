import numpy as np
import json
import uuid

from .orcglobals import MODELS, MODEL_DIR

mods = [x for x in range(0, MODELS) if x not in [17, 7]]


loaded_models = []


class Job:
    def __init__(self, model, num_functions, ids=None):
        assert num_functions != 0
        self.model = model
        self.f = num_functions
        self.ids = ids
        self.rand = np.random.default_rng(np.random.randint(0, 2 ** 32))

        if ids is None:
            self.ids = [uuid.uuid1().hex for _ in range(0, num_functions)]

        self.run_times = {id: self.model.sample_cpu() for id in self.ids}
        self.memory = {id: self.model.sample_mbs() for id in self.ids}

    def run_trace(self, run_for):
        cur_time = 0
        # noise = model.noise()
        trace = []
        # Lets lookst at if we create an ecdf from scratch by looking at the
        # upper and lower bounds of the ecdf of each cluster.
        while cur_time < run_for:
            samples = np.array(self.model.sample(10000))
            cur_time += samples[0]
            i = 1
            while i < len(samples):
                time = samples[i]
                i += 1
                if np.isinf(time) or time < 0:
                    continue

                events = self.f
                ids = self.ids.copy()
                self.rand.shuffle(ids)
                for v in sorted(self.rand.uniform(cur_time, cur_time + time, events)):
                    id = ids[0]
                    ids.pop(0)
                    trace.append((v, id, self.model.name))
                #                    trace.append((v, id, self.model.name,
                #                        self.run_times[id], self.memory[id]))

                cur_time += time

                if cur_time >= run_for:
                    break
        return [t for t in trace if t[0] < run_for]


def check_ready():
    for i in mods:
        model_name = f"{i}-model"
        model_path = MODEL_DIR / model_name
        if not model_path.exists():
            return False

    return True


def load_models():
    for i in mods:
        model_name = f"{i}-model"
        model_path = MODEL_DIR / model_name
        with open(model_path, "rb") as f:
            loaded_models.append(Model(model_name, json.load(f)))

    print("Model Functions: ", sum([x.weight for x in loaded_models]))

    return loaded_models


def _sample(inverse_ecdf, num, rand):
    samples = []
    for _ in range(0, num):
        p = rand.integers(0, high=len(inverse_ecdf) - 1)
        samples.append(1 / inverse_ecdf[p])
    return samples


def python_function_template(runtime):
    program = """
    import time
    import mmap
    def lambda():
        t = time.time()
        # Busy wait so we consume cpu
        while (time.time() - t) < {0}:
            pass
    """.format(
        runtime
    )

    return program


def create_function(model, language="python"):
    mbs = model.sample_mbs()
    runtime = model.sample_cpu()

    if language == "python":
        program = python_function_template(runtime)
    else:
        program = ""

    return program


class Model:
    def __init__(self, model_name, model_dict):
        self.name = model_name
        self.inverse_invocation_ecdf = model_dict["inverse_ecdf"]
        self.inverse_memory_ecdf = model_dict["mbs"]
        self.inverse_cpu_ecdf = model_dict["cpu"]
        self.weight = model_dict["num_functions"]
        self.rand = np.random.default_rng(np.random.randint(0, 2 ** 32))

    def sample(self, num=1):
        return _sample(self.inverse_invocation_ecdf, num, self.rand)

    def sample_mbs(self, num=1):
        return _sample(self.inverse_memory_ecdf, num, self.rand)

    def sample_cpu(self, num=1):
        return _sample(self.inverse_cpu_ecdf, num, self.rand)


def get_jobs(n, scale, seed):
    if not check_ready():
        return None

    np.random.seed(seed)

    models = load_models()

    job_map = {}
    for m in models:
        jobs = []
        num_functions = int(m.weight * scale)
        if num_functions == 0:
            continue
        groups = int(num_functions / n)
        extra = num_functions % n
        j = [Job(m, n) for _ in range(0, groups)]
        jobs.extend(j)
        if extra != 0:
            jobs.append(Job(m, extra))
        job_map[m.name] = jobs

    return job_map
