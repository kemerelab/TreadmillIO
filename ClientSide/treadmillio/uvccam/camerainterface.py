import setproctitle, signal
import multiprocessing
import cProfile
import queue

def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def simple_handler(signal, frame):
    # print('CameraInterface caught SIGINT. Passing it along as an exception.')
    raise(KeyboardInterrupt)

def start_camera(config, frame_queues, terminate_flag, done_flag):
    signal.signal(signal.SIGINT, simple_handler)
    multiprocessing.current_process().name = "python3 USBCamera/uvc_acquisition"
    setproctitle.setproctitle(multiprocessing.current_process().name)

    import logging
    try:
        import treadmillio.uvccam.uvc as uvc
    except:
        import uvc as uvc

    class CameraInterface():
        def __init__(self, config, frame_queues, terminate_flag):
            self._terminate_flag = terminate_flag
            self._queues = frame_queues

            which_camera = config['CameraIndex']
            self.sy = config['ResY']
            self.sx = config['ResX']
            self.frame_rate = config['FrameRate']

            self.number_of_channels = 3 # TODO: Consider handling mono?

            logging.basicConfig(level=logging.CRITICAL)

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

            # HACK: In some older C920 models, the focus resets to an old value when
            # capture is started. You first must set the focus value, then start
            # capturing, and then reset the focus value again.
            frame = self._cap.get_frame_timeout(2/self.frame_rate)
            del frame
            for c in self._cap.controls:
                if c.display_name in config.get('CameraParams', []) \
                   and c.display_name == 'Absolute Focus':
                    c.value = config['CameraParams'][c.display_name]

        def run(self):
            while not check_shm(self._terminate_flag):
                frame = self._cap.get_frame_timeout(2/self.frame_rate)
                if frame:
                    for q in self._queues:
                        if not check_shm(self._terminate_flag):
                            if q.frame_type == 'img':
                                if q.is_active():
                                    # Unlike the video write process, we can afford
                                    # to drop frames for the visualization process.
                                    try:
                                        q.put((frame.img, frame.timestamp), block=False)
                                    except queue.Full:
                                        continue
                            elif q.frame_type == 'jpeg':
                                q.put((frame.jpeg_raw, frame.timestamp))
                            else:
                                raise(ValueError("Camera interface frame type not understood ({}).".format(q.frame_type)))

        def close(self):
            if self._cap:
                self._cap.close()


    try:
        camera = CameraInterface(config, frame_queues, terminate_flag)
        done_flag.value = False # not using a lock!
        # cProfile.runctx('camera.run()()', globals(), locals(), "results.prof") # useful for debugging
        camera.run()
        print('Ended run')
        camera.close()
        done_flag.value = True #
        print('Done in camera exit.')
    except (KeyboardInterrupt, SystemExit):
        terminate_flag.value = True
        camera.close()
        done_flag.value = True #
        print('Camera exited b/c of SIGINT')


    return
