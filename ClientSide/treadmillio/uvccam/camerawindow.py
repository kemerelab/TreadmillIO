import setproctitle, signal
import multiprocessing
import queue
import numpy as np

def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def set_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = True


def simple_handler(signal, frame):
    # print('Caught SIGINT and passed it on as an exception')
    raise(KeyboardInterrupt)

def start_window(config, visualization_frame_queue, quit_flag, done_flag, no_escape):
    signal.signal(signal.SIGINT, simple_handler)
    multiprocessing.current_process().name = "python3 USBCamera/pyglet_view"

    import pyglet
    from pyglet.window import key

    class CameraWindow(pyglet.window.Window):
        def __init__(self, config, frame_queue, quit_flag, no_escape=True):
            self._quit_flag = quit_flag # used to let this process signal everyone else to exit
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

            self._no_escape = no_escape

        def on_key_press(self, symbol, modifiers):
            if symbol == key.ESCAPE:
                if not self._no_escape:
                    print('Application Exited with Key Press')
                    if self._quit_flag:
                        set_shm(self._quit_flag)
                        self._quit_flag = None
                    self.graceful_shutdown()
                

        def update(self, dt):
            if self._quit_flag and check_shm(self._quit_flag):
                self.graceful_shutdown()

        def on_draw(self):
            while not self._frame_queue.empty():
                (img, timestamp) = self._frame_queue.get()
                self._img.set_data('BGR', -self.sx * self.number_of_channels, img.tobytes())
            self.clear()
            self._tex = self._img.get_texture()
            pyglet.gl.glEnable(pyglet.gl.GL_TEXTURE_2D)
            pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_LINEAR)
            pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MIN_FILTER, pyglet.gl.GL_LINEAR)
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
            self.close()


    camera_window = CameraWindow(config, visualization_frame_queue, quit_flag, no_escape)
    pyglet.clock.schedule_interval(camera_window.update, 1/60.0)

    try:
        done_flag.value = False
        pyglet.app.run()
    except KeyboardInterrupt:
        # print('Pyglet caught sigint')
        camera_window.graceful_shutdown()
        done_flag.value = True
    except Exception as e:
        print("Exception cw!!!", e)



