import uvc
import logging
import pyglet
from pyglet.gl import *
from pyglet.window import key
import numpy as np
import time
import multiprocessing
#from multiprocessing import Process, Pipe, Value, Queue, Event, current_process
import queue
import setproctitle
import signal
import skvideo.io

def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def set_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = True


class VideoWriter():
    def __init__(self, frame_queue, terminate_flag, done_flag):
        self._terminate_flag = terminate_flag
        self._done_flag = done_flag
        self._frame_queue = frame_queue

        filename = 'test.mp4'
        self._writer = skvideo.io.FFmpegWriter(filename, outputdict={
            #'-vcodec': 'libx264', '-b': '300000000'
            '-vcodec': 'libx264', '-crf': '27', '-preset': 'veryfast'
        })

    def run(self):
        t_write = 0
        try:
            while not check_shm(self._terminate_flag):
                try:
                    t0 = time.time()
                    (img, timestamp) = self._frame_queue.get(0)
                    self._writer.writeFrame(img)
                    t_write = time.time() - t0
                except queue.Empty:
                    time.sleep(max(1/30 - 1.5*t_write,0)) # approx time till next frame
        except KeyboardInterrupt:
            pass

        print('Terminating Writer in run loop')
        if (self._writer):
            self._writer.close()
            self._writer = None
        if self._done_flag:
            set_shm(self._done_flag)
            self._done_event = None


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('Terminating Writer in exit')
        if (self._writer):
            self._writer.close()
        if self._done_flag:
            set_shm(self._done_flag)


class CameraInterface():
    def __init__(self, image_format, frame_queues, terminate_flag, done_flag):
        logging.basicConfig(level=logging.INFO)
        self._terminate_flag = terminate_flag
        self._done_flag = done_flag

        self._queues = frame_queues

        dev_list = uvc.device_list()
        for dev in dev_list:
            print(dev)
            print(dev["uid"])

        self._cap = uvc.Capture(dev_list[0]["uid"])
        print(self._cap.avaible_modes)
        for c in self._cap.controls:
            print(c.display_name)

        self.sy, self.sx, self.number_of_channels = image_format # (720, 1280, 3)
        self._cap.frame_mode = (self.sx, self.sy, 30)
        self.frame_rate = 30

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
    def __init__(self, image_format, frame_queue, quit_flag):
        self._quit_flag = quit_flag
        self._frame_queue = frame_queue

        self.sy, self.sx, self.number_of_channels = image_format # (720, 1280, 3)
        super().__init__(visible=True, resizable=True)
        #super().__init__(width=self.sx, height=self.sy,visible=True)

        initial_texture = 128*np.ones((self.sy, self.sx, self.number_of_channels), dtype='uint8')
        self._img = pyglet.image.ImageData(self.sx,self.sy,'BGR',
            initial_texture.tobytes(),pitch=-self.sx*self.number_of_channels)
        
        self._tex = self._img.get_texture()
        self.alive = True

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE:
            print('Application Exited with Key Press')
            self.graceful_shutdown()

    def update(self, dt):
        pass

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


def start_camera(image_format, frame_queues, terminate_flag, done_flag):
    multiprocessing.current_process().name = "Camera"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with CameraInterface(image_format, frame_queues, terminate_flag, done_flag) as camera:
        camera.run()
    return

def start_writer(frame_queue, terminate_flag, done_flag):
    multiprocessing.current_process().name = "Writer"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with VideoWriter(frame_queue, terminate_flag, done_flag) as vwriter:
        vwriter.run()
    return

if __name__ == '__main__':
    visualization_frame_queue = multiprocessing.Queue()
    storage_frame_queue = multiprocessing.Queue()

    frame_queues = [visualization_frame_queue, storage_frame_queue]

    terminate_flag = multiprocessing.Value('b', False)
    camera_process_finished = multiprocessing.Value('b', False)
    vwriter_process_finished = multiprocessing.Value('b', False)

    video_grabber = VideoDisplay((480, 640, 3), visualization_frame_queue, terminate_flag)
    #signal.signal(signal.SIGINT, video_grabber.handle_sigint)

    camera_process = multiprocessing.Process(target=start_camera, args=((480, 640, 3), frame_queues, terminate_flag, camera_process_finished))
    camera_process.daemon = True
    camera_process.start()     # Launch the sound process

    vwriter_process = multiprocessing.Process(target=start_writer, args=(storage_frame_queue, terminate_flag, vwriter_process_finished))
    vwriter_process.daemon = True
    vwriter_process.start()     # Launch the sound process

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
    # Wait for end of video process
    while not check_shm(vwriter_process_finished):
        pass
    print('Finished waiting for vwriter')
    
    for q in frame_queues:
        while not q.empty():
            print('draining queue')
            q.get()
            time.sleep(0.1)

    print('waiting for join')            
    camera_process.join()
    vwriter_process.join()
    