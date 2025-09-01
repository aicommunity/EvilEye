from abc import ABC
import multiprocessing as mp


class MpControl(ABC):
    def __init__(self, max_input_size=None):
        self.workers_list = []
        if max_input_size:
            self.input_queue = mp.Queue(maxsize=max_input_size)
        else:
            self.input_queue = mp.Queue()

        self.output_queue = mp.Queue()
        self.queue_timeout = None
        self.processes = []

    def add_worker(self, worker_class):
        worker = worker_class(self.input_queue, self.output_queue)
        self.workers_list.append(worker)
        return worker

    def put(self, data):
        self.input_queue.put(data)

    def get(self):
        return self.output_queue.get()

    def start(self):
        for i in range(len(self.workers_list)):
            p = mp.Process(target=self.workers_list[i],
                           daemon=True)
            p.start()
            self.processes.append(p)

    def stop(self):
        for i in range(len(self.processes)):
            if self.processes[i].is_alive():
                self.processes[i].join()

