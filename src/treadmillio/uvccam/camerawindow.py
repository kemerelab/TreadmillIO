import setproctitle, signal
import multiprocessing
import queue
import numpy as np
import os

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
        # 1080p defaults
        MAX_BUFFER_MB = 500

        def __init__(self, config, frame_queue, quit_flag, no_escape=True):
            self._quit_flag = quit_flag # used to let this process signal everyone else to exit
            self._frame_queue = frame_queue

            self.name = config['FilenameHeader']
            self.verbose = config.get('Verbose', False)

            self.sy = config['ResY']
            self.sx = config['ResX']
            self.number_of_channels = 3 # TODO: Consider handling mono?

            # Determine maximum buffer size in frames
            bytes_per_frame = self.sy*self.sx*self.number_of_channels
            if 'BufferSizeFrames' in config:
                # User-specified size in frames
                self.buffer_size = config['BufferSizeFrames']
            elif 'BufferSizeMB' in config:
                # User-specified size in MB
                self.buffer_size = int(config['BufferSizeMB']*1.0e6/bytes_per_frame)
            elif config['ResY'] >= 1080:
                # If resolution is at least 1080p, then underlying pickler/unpickler
                # in self._frame_queue cannot keep up. Follow pattern of filling up
                # buffer and periodically draining queue.
                self.buffer_size = int(self.MAX_BUFFER_MB*1.0e6/bytes_per_frame)
            else:
                # Otherwise, drain queue every call to on_draw().
                self.buffer_size = 0
            if self.verbose:
                print('({}) Max buffer frames: {:2d}'.format(self.name, self.buffer_size))

            super().__init__(visible=True, resizable=True)
            #super().__init__(width=self.sx, height=self.sy, visible=True)

            # Set aesthetics
            self.set_caption(self.name)
            if 'Position' in config:
                assert len(config['Position']) == 2
                self.set_location(*config['Position'])         
            d = os.path.dirname(os.path.abspath(__file__))
            self.set_icon(pyglet.image.load(os.path.join(d, 'rnel.png')))

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
            if self._frame_queue.qsize() > self.buffer_size:
                self._frame_queue.pause()
                if self.verbose:
                    print('({}) Visualization queue full. Draining...'.format(self.name))
                while self._frame_queue.qsize() > 0:
                    try:
                        (img, timestamp) = self._frame_queue.get(block=True, timeout=0.1)
                    except queue.Empty:
                        continue
                self._frame_queue.restart()
                if self.verbose:
                    print('({}) Finished draining visualization queue.'.format(self.name))
                self._img.set_data('BGR', -self.sx * self.number_of_channels, img.tobytes())
            elif not self._frame_queue.empty():
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



