import setproctitle, signal
import multiprocessing
import cProfile

import vimba


def print_feature(feature):
    try:
        value = feature.get()

    except (AttributeError, vimba.VimbaFeatureError):
        value = None

    print('/// Feature name   : {}'.format(feature.get_name()))
    print('/// Display name   : {}'.format(feature.get_display_name()))
    print('/// Tooltip        : {}'.format(feature.get_tooltip()))
    print('/// Description    : {}'.format(feature.get_description()))
    print('/// SFNC Namespace : {}'.format(feature.get_sfnc_namespace()))
    print('/// Unit           : {}'.format(feature.get_unit()))
    print('/// Value          : {}\n'.format(str(value)))


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

    class CameraInterface():
        def __init__(self, config, frame_queues, terminate_flag):
            self._terminate_flag = terminate_flag
            self._queues = frame_queues

            which_camera = config['CameraIndex']
            self.sy = config['ResY']
            self.sx = config['ResX']
            self.frame_rate = config['FrameRate']
            self._cam = None

            self.number_of_channels = 3 # TODO: Consider handling mono?

            logging.basicConfig(level=logging.CRITICAL)

            with vimba.Vimba.get_instance() as vim:
                cams = vim.get_all_cameras()
                print('Available cameras (*** selected):')
                print(type(cams))
                print(cams)

                print('Features of camera 0')
                self._cam = cams[0]

                with self._cam as cam:
                    frame_height = cam.get_feature_by_name('Height')
                    frame_height.set(self.sx)                    
                    frame_width = cam.get_feature_by_name('Width')
                    frame_width.set(self.sy)                    
                    frame_rate_enable = cam.get_feature_by_name('AcquisitionFrameRateEnable')
                    frame_rate_enable.set(True)
                    frame_rate = cam.get_feature_by_name('AcquisitionFrameRate')
                    frame_rate.set(self.frame_rate)                    

                    print('Print all features of camera \'{}\':'.format(cam.get_id()))
                    for feature in cam.get_all_features():
                        print_feature(feature)


            # for idx, dev in enumerate(dev_list):
            #     if idx == which_camera:
            #         print('*** ', dev) # Highlight the selected camera in the list
            #     else:
            #         print('    ', dev)

            # self._cap = uvc.Capture(dev_list[which_camera]["uid"])

            # self._cap.bandwidth_factor = 4

            # print('Available resolutions (*** selected):')
            # for mode in self._cap.avaible_modes:
            #     if mode == (self.sx, self.sy, self.frame_rate):
            #         print("\n*** {} ***".format(mode))
            #     else:
            #         print("{}".format(mode), end=" ")
            # self._cap.frame_mode = (self.sx, self.sy, self.frame_rate)

            # print("\nCamera Controls (*** set as specified in CameraParams)")
            # for c in self._cap.controls:
            #     if 'CameraParams' in config:
            #         if c.display_name in config['CameraParams']:
            #             c.value = config['CameraParams'][c.display_name]
            #             print("*** {}: {}".format(c.display_name, c.value))
            #         else:
            #             print("    {}: {}".format(c.display_name, c.value))

        def run(self):
            with vimba.Vimba.get_instance() as vim:
                with self._cam as cam:
                    for frame in cam.get_frame_generator(timeout_ms=2000):
                        if check_shm(self._terminate_flag):
                            break

                        for q in self._queues:
                            if not check_shm(self._terminate_flag):
                                if q.frame_type == 'img':
                                    q.put((frame.as_numpy_ndarray(), 0))
                                elif q.frame_type == 'jpeg':
                                    pass
                                    #q.put((frame.jpeg_raw, frame.timestamp))
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
