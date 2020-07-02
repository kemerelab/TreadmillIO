
import sys, os, setproctitle, signal, time

import uvc
import skvideo.io
import logging

import multiprocessing
import queue
import csv
import numpy as np

import pyglet
from pyglet.gl import *
from pyglet.window import key


def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def set_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = True


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

    def run(self):
        t_write = 0
        try:
            while not check_shm(self._terminate_flag):
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
        print('Terminating Writer in exit')
        if (self._ts_file):
            self._ts_file.close()
        if (self._writer):
            self._writer.close()
        if self._done_flag:
            set_shm(self._done_flag)


class CameraInterface():
    def __init__(self, config, frame_queues, terminate_flag, done_flag):
        self._terminate_flag = terminate_flag
        self._done_flag = done_flag
        self._queues = frame_queues

        which_camera = config['CameraIndex']
        self.sy = config['ResY']
        self.sx = config['ResX']
        self.frame_rate = config['FrameRate']

        self.number_of_channels = 3 # TODO: Consider handling mono?

        logging.basicConfig(level=logging.INFO)


        dev_list = uvc.device_list()
        print('Available cameras (*** selected):')
        for idx, dev in enumerate(dev_list):
            if idx == which_camera:
                print('*** ', dev) # Highlight the selected camera in the list
            else:
                print('    ', dev)

        self._cap = uvc.Capture(dev_list[which_camera]["uid"])

        self._cap.bandwidth_factor = 4

        print('Available resolutions (*** selected):')
        for mode in self._cap.avaible_modes:
            if mode == (self.sx, self.sy, self.frame_rate):
                print("\n*** {} ***".format(mode))
            else:
                print("{}".format(mode), end=" ")
        self._cap.frame_mode = (self.sx, self.sy, self.frame_rate)

        print("\nCamera Controls (*** set as specified in CameraParams)")
        for c in self._cap.controls:
            if 'CameraParams' in config:
                if c.display_name in config['CameraParams']:
                    c.value = config['CameraParams'][c.display_name]
                    print("*** {}: {}".format(c.display_name, c.value))
                else:
                    print("    {}: {}".format(c.display_name, c.value))

    def run(self):
        try:
            while not check_shm(self._terminate_flag):
                frame = self._cap.get_frame_timeout(2/self.frame_rate)
                if frame:
                    for q in self._queues:
                        if not check_shm(self._terminate_flag):
                            q.put((frame.img, frame.timestamp))
        except KeyboardInterrupt:
            pass

        print('Terminating Capture in run()')
        if (self._cap):
            self._cap.close()
            self._cap = None

        if self._done_flag:
            set_shm(self._done_flag)
            self._done_flag = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('Terminating Capture')
        if (self._cap):
            self._cap.close()
        if self._done_flag:
            set_shm(self._done_flag)

    

class VideoDisplay(pyglet.window.Window):
    def __init__(self, config, frame_queue, quit_flag, no_escape=True):
        self._quit_flag = quit_flag
        self._frame_queue = frame_queue

        self.sy = config['ResY']
        self.sx = config['ResX']
        self.number_of_channels = 3 # TODO: Consider handling mono?

        super().__init__(visible=True, resizable=True)
        #super().__init__(width=self.sx, height=self.sy, visible=True)

        initial_texture = 128*np.ones((self.sy, self.sx, self.number_of_channels), dtype='uint8')
        self._img = pyglet.image.ImageData(self.sx,self.sy,'BGR',
            initial_texture.tobytes(),pitch=-self.sx*self.number_of_channels)
        
        self._tex = self._img.get_texture()
        self.alive = True

        self._no_escape = no_escape

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE:
            if not self._no_escape:
                print('Application Exited with Key Press')
                self.graceful_shutdown()
            

    def update(self, dt):
        if check_shm(self._quit_flag):
            self.graceful_shutdown()

    def on_draw(self):
        while not self._frame_queue.empty():
            (img, timestamp) = self._frame_queue.get()
            self._img.set_data('BGR', -self.sx * self.number_of_channels, img.tobytes())
        self.clear()
        self._tex = self._img.get_texture()
        glEnable(GL_TEXTURE_2D)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        if (self.width/self.height) > (self.sx/self.sy):
            new_width = float(self.height) * float(self.sx)/float(self.sy)
            new_height = float(self.height)
        else:
            new_width = float(self.width)
            new_height = float(self.width) * float(self.sy)/float(self.sx)
        self._tex.width = new_width
        self._tex.height = new_height
        x_offset = (self.width - new_width)/2
        y_offset = (self.height - new_height)/2
        self._tex.blit(x_offset, y_offset)

    def on_close(self):
        self.graceful_shutdown()

    def graceful_shutdown(self):
        print('Terminating gracefully.')
        if self._quit_flag:
            set_shm(self._quit_flag)
            self._quit_flag = None
        self.close()


def start_camera(config, frame_queues, terminate_flag, done_flag):
    multiprocessing.current_process().name = "Camera"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with CameraInterface(config, frame_queues, terminate_flag, done_flag) as camera:
        camera.run()
    return

def start_writer(config, frame_queue, terminate_flag, done_flag):
    multiprocessing.current_process().name = "Writer"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with VideoWriter(config, frame_queue, terminate_flag, done_flag) as vwriter:
        vwriter.run()
    return

def RunCameraInterface(config, no_escape=True):
    # Initialize objects used to communicate between processes
    terminate_flag = multiprocessing.Value('b', False) # This is the global flag that is used to signal that the whole edice should collapse gracefully
    camera_process_finished = multiprocessing.Value('b', False) # This signals to the main process that the camera acquisition process has terminated
    
    visualization_frame_queue = multiprocessing.Queue() # This queue is filled by the camera acquisition process and emptied by the (visualization) primary process

    do_record = config.get('RecordVideo', False)
    if do_record:
        vwriter_process_finished = multiprocessing.Value('b', False) # This signals to the main process that the video writing process has terminated

        storage_frame_queue = multiprocessing.Queue() # This queue is filled by the camera acquisition process and emptied by the video writing process
        
        frame_queues = [visualization_frame_queue, storage_frame_queue]
    else:
        print('NOT RECORDING!!!')
        frame_queues = [visualization_frame_queue]

    camera_process = multiprocessing.Process(target=start_camera, args=(config, frame_queues, terminate_flag, camera_process_finished))
    camera_process.daemon = True
    camera_process.start()     # Launch the camera frame acquisition process

    if do_record:
        vwriter_process = multiprocessing.Process(target=start_writer, args=(config, storage_frame_queue, terminate_flag, vwriter_process_finished))
        vwriter_process.daemon = True
        vwriter_process.start()     # Launch the video writing process

    # Create the main pyglet window
    video_grabber = VideoDisplay(config, visualization_frame_queue, terminate_flag, no_escape)

    pyglet.clock.schedule_interval(video_grabber.update, 1/60.0)

    try:
        pyglet.app.run()
    except KeyboardInterrupt:
        print('Caught SIGINT')
        set_shm(terminate_flag)
        pass

    print('Pyglet run done.')

    # Wait for end of camera process
    while not check_shm(camera_process_finished):
        pass
    print('Finished waiting for camera')

    if do_record:
        # Wait for end of video process
        while not check_shm(vwriter_process_finished):
            pass
        print('Finished waiting for vwriter')
    
    for q in frame_queues:
        time.sleep(0.1) # give a second for the queue background process (thread?) to finish loading data
        while not q.empty():
            print('draining queue')
            q.get()
            time.sleep(0.1) # give a second for the queue background process (thread?) to finish loading data

    print('waiting for join')            
    camera_process.join()

    if do_record:
        vwriter_process.join()

    #### That's all folks!!!

def main():
    if len(sys.argv) > 1:
        camera = int(sys.argv[1])
    else:
        camera = 0
        print("Using camera ", camera)

    config = {
        'RecordVideo': True,
        'FilenameHeader': 'videodata',
        'LogDirectory': os.getcwd(),
        'CameraIndex': camera,
        'ResX': 640, 'ResY': 480, 'FrameRate': 30,
        'CameraParams': {
            'Power Line frequency': 2, # 60 Hz
            'Gain': 10
        }

    }

    RunCameraInterface(config)


if __name__ == '__main__':
    main()
