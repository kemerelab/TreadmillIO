import setproctitle, signal
import treadmillio.webcam.uvc as uvc
import logging

import multiprocessing

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

        print('Terminating camera in run()')
        if (self._cap):
            print('Trying to close camera')
            self._cap.close()
            self._cap = None

        print('Closed cap')
        if self._done_flag:
            print('Waiting on shm in run')
            set_shm(self._done_flag)
            self._done_flag = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if (self._cap):
            self._cap.close()

        if self._done_flag:
            print('Waiting on shm in exit')
            set_shm(self._done_flag)
        print('Camera exited')


def simple_handler(signal, frame):
    print('CameraInterface caught SIGINT. Passing it along as an exception.')
    raise(KeyboardInterrupt)

def start_camera(config, frame_queues, terminate_flag, done_flag):
    signal.signal(signal.SIGINT, simple_handler)

    multiprocessing.current_process().name = "Webcam/Camera"
    setproctitle.setproctitle(multiprocessing.current_process().name)
    with CameraInterface(config, frame_queues, terminate_flag, done_flag) as camera:
        unset_shm(done_flag) #  change our done state to False
        camera.run()
    return
