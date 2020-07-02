import os, setproctitle, signal, time

import skvideo.io
import logging

import multiprocessing
import queue
import csv
import numpy as np

def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def set_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = True

def unset_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = False


class VideoWriter():
    def __init__(self, config, frame_queue, terminate_flag, done_flag):
        self._terminate_flag = terminate_flag
        self._done_flag = done_flag
        self._frame_queue = frame_queue

        filename_header = config['FilenameHeader']
        log_directory = config['LogDirectory']
        if not os.path.isdir(log_directory):
            raise(ValueError('VideoWriter LogDirectory [{}] not found.'.format(log_directory)))

        video_filename = os.path.join(log_directory, '{}.mp4'.format(filename_header))
        self._writer = skvideo.io.FFmpegWriter(video_filename, outputdict={
            #'-vcodec': 'libx264', '-b': '300000000'
            '-vcodec': 'libx264', '-crf': '27', '-preset': 'veryfast'
        })

        timestamps_filename = os.path.join(log_directory, '{}_timestamps.csv'.format(filename_header))
        self._ts_file = open(timestamps_filename, 'w')
        self._ts_writer = csv.writer(self._ts_file, delimiter=',')

        self.alive = True

    def run(self):
        t_write = 0
        try:
            while not check_shm(self._terminate_flag) and self.alive:
                try:
                    t0 = time.time()
                    (img, timestamp) = self._frame_queue.get(0)
                    self._writer.writeFrame(img)
                    self._ts_writer.writerow([timestamp, time.clock_gettime_ns(time.CLOCK_MONOTONIC)])
                    t_write = time.time() - t0
                except queue.Empty:
                    time.sleep(max(1/30 - 1.5*t_write,0)) # approx time till next frame
        except KeyboardInterrupt:
            pass

        print('Terminating Writer in run loop')
        if (self._writer):
            self._writer.close()
            self._writer = None
        if (self._ts_file):
            self._ts_file.close()
            self._ts_file = None
        if self._done_flag:
            set_shm(self._done_flag)
            self._done_event = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if (self._ts_file):
            self._ts_file.close()
        if (self._writer):
            self._writer.close()
        if self._done_flag:
            set_shm(self._done_flag)
        print('Video writer exited')


def simple_handler(signal, frame):
    print('VideoWriter caught SIGINT. Passing it along as an exception.')
    raise(KeyboardInterrupt)

def start_writer(config, frame_queue, terminate_flag, done_flag):
    signal.signal(signal.SIGINT, simple_handler)

    multiprocessing.current_process().name = "Webcam/Writer"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with VideoWriter(config, frame_queue, terminate_flag, done_flag) as vwriter:
        unset_shm(done_flag) #  change our done state to False
        vwriter.run()
    return
