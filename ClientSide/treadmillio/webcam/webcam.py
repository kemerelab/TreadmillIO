import uvc
import logging
import pyglet
from pyglet.gl import *
from pyglet.window import key
import numpy as np
import sys
import time
from multiprocessing import Process, Pipe, Value, Queue, Event
import queue

import skvideo.io

class VideoWriter():
    def __init__(self, frame_queue, terminate_event, done_event):
        self._terminate_event = terminate_event
        self._done_event = done_event
        self._frame_queue = frame_queue

        filename = 'test.mp4'
        self._writer = skvideo.io.FFmpegWriter(filename, outputdict={
            '-vcodec': 'libx264', '-b': '300000000'
        })

    def run(self):
        while not self._terminate_event.is_set():
            (img, timestamp) = self._frame_queue.get()
            self._writer.writeFrame(img)

        print('Stopped running in VideoWriter. When will exit be called?')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('Terminating VideoWriter')
        if (self._writer):
            self._writer.close()

        self._done_event.set()


class CameraInterface():
    def __init__(self, image_format, frame_queues, terminate_event, done_event):
        logging.basicConfig(level=logging.INFO)
        self._terminate_event = terminate_event
        self._done_event = done_event

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

    def run(self):
        while not self._terminate_event.is_set():
            frame = self._cap.get_frame_timeout(0)
            if not frame:
                raise(ValueError("Got a none despite no timeout."))
            else:
                for q in self._queues:
                    if not self._terminate_event.is_set():
                        q.put((frame.img, frame.timestamp))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        print('Terminating Capture')
        if (self._cap):
            self._cap.close()

        self._done_event.set()

    

class VideoDisplay(pyglet.window.Window):
    def __init__(self, image_format, frame_queue, quit_event):
        self._quit_event = quit_event
        self._frame_queue = frame_queue

        self.sy, self.sx, self.number_of_channels = image_format # (720, 1280, 3)
        super().__init__(visible=True)
        #super().__init__(width=self.sx, height=self.sy,visible=True)

        initial_texture = np.zeros((self.sy, self.sx, self.number_of_channels), dtype='uint8')
        self._img = pyglet.image.ImageData(self.sx,self.sy,'BGR',
            initial_texture.tobytes(),pitch=-self.sx*self.number_of_channels)
        
        self.alive = True

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE:
            print('Application Exited with Key Press')
            self.alive = False
            #self.quit_event.set()

    def on_draw(self):
        self.render()

    def on_close(self):
        self.alive = False

    def render(self):
        self.clear()
        #self.bg.draw()
        self._img.blit(0,0)
        self.flip()

    def run(self):
        while self.alive:
            # pyglet.clock.tick()

            if not self._frame_queue.empty():
                (img, timestamp) = self._frame_queue.get()
                self._img.set_data('BGR', -self.sx * self.number_of_channels, img.tobytes())

            self.render()

            event = self.dispatch_events()

            if self._quit_event.is_set():
                self.alive = False

        if not self._quit_event.is_set():
            self._quit_event.set()

def start_camera(image_format, frame_queues, terminate_event, done_event):
    with CameraInterface(image_format, frame_queues, terminate_event, done_event) as camera:
        camera.run()
    return

def start_writer(frame_queue, terminate_event, done_event):
    with VideoWriter(frame_queue, terminate_event, done_event) as vwriter:
        vwriter.run()
    return


if __name__ == '__main__':
    visualization_frame_queue = Queue()
    storage_frame_queue = Queue()

    frame_queues = [visualization_frame_queue, storage_frame_queue]

    terminate_event = Event()
    camera_process_finished = Event()
    vwriter_process_finished = Event()

    video_grabber = VideoDisplay((720, 1280, 3), visualization_frame_queue, terminate_event)

    camera_process = Process(target=start_camera, args=((720, 1280, 3), frame_queues, terminate_event, camera_process_finished))
    camera_process.daemon = True
    camera_process.start()     # Launch the sound process

    vwriter_process = Process(target=start_writer, args=(storage_frame_queue, terminate_event, vwriter_process_finished))
    vwriter_process.daemon = True
    vwriter_process.start()     # Launch the sound process


    video_grabber.run()

    camera_process_finished.wait()
    vwriter_process_finished.wait()

    for q in frame_queues:
        while not q.empty():
            q.get()
            
    camera_process.join()
    vwriter_process.join()
    