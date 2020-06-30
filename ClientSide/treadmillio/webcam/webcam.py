import uvc
import logging
import pyglet
from pyglet.gl import *
from pyglet.window import key
import numpy as np
import sys
import time
from multiprocessing import Process, Pipe, Value, Queue
import queue



class VideoGrabber(pyglet.window.Window):
    def __init__(self, control_queue):
        self.control_queue = control_queue

        self.sy, self.sx, self.number_of_channels = (720, 1280, 3)
        super().__init__(visible=True)
        #super().__init__(width=self.sx, height=self.sy,visible=True)

        initial_texture = np.zeros((self.sy, self.sx, self.number_of_channels), dtype='uint8')
        self._img = pyglet.image.ImageData(self.sx,self.sy,'BGR',
            initial_texture.tobytes(),pitch=self.sx*self.number_of_channels)
        
        self.alive = True

        logging.basicConfig(level=logging.INFO)

        dev_list = uvc.device_list()
        for dev in dev_list:
            print(dev)
            print(dev["uid"])

        self._cap = uvc.Capture(dev_list[0]["uid"])
        print(self._cap.avaible_modes)

        self._cap.frame_mode = (self.sx, self.sy, 30)

    def poll_camera(self):
        frame = self._cap.get_frame_timeout(-1)
        if frame:
           # print(frame.timestamp)
           self._img.set_data('BGR', self.sx * self.number_of_channels, frame.img.tobytes())

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE:
            print('Application Exited with Key Press')
            self.alive = False

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
            try:
                event = self.control_queue.get(block=False)
                if (event == "STOP"):
                    self.alive = False
            except queue.Empty:
                continue

            self.poll_camera()
            self.render()

            event = self.dispatch_events()

        print('Ending event loop')
        self._cap.close()

def delay_and_join(control_queue):
    time.sleep(10)
    print('Returning')
    control_queue.put("STOP")
    return

if __name__ == '__main__':
    control_queue = Queue()

    video_grabber = VideoGrabber(control_queue)
    test_talking_process = Process(target=delay_and_join, args=(control_queue,))
    test_talking_process.daemon = True
    test_talking_process.start()     # Launch the sound process

    video_grabber.run()
    test_talking_process.join()
    