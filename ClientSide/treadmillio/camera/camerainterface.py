from multiprocessing.sharedctypes import Value
import setproctitle, signal
import multiprocessing
import cProfile
import queue
import numpy as np
import cv2


def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def simple_handler(signal, frame):
    # print('CameraInterface caught SIGINT. Passing it along as an exception.')
    raise(KeyboardInterrupt)

def start_camera(config, frame_queues, terminate_flag, done_flag):
    signal.signal(signal.SIGINT, simple_handler)
    multiprocessing.current_process().name = "python3 GigE Iface"
    setproctitle.setproctitle(multiprocessing.current_process().name)

    import gi
    gi.require_version ('Aravis', '0.8')
    from gi.repository import Aravis

    class CameraInterface():
        def __init__(self, config, frame_queues, terminate_flag):
            self._terminate_flag = terminate_flag
            self._queues = frame_queues

            # print('Available cameras (*** selected):')
            # which_camera = config['CameraIndex']

            # for idx, dev in enumerate(dev_list):
            #     if idx == which_camera:
            #         print('*** ', dev) # Highlight the selected camera in the list
            #     else:
            #         print('    ', dev)

            # dev_list = uvc.device_list()
            # self._cap = uvc.Capture(dev_list[which_camera]["uid"])

            try:
                self._camera = Aravis.Camera.new (None)
            except:
                print ("No camera found")
                exit ()


            # print('Available resolutions (*** selected):')
            # for mode in self._cap.avaible_modes:
            #     if mode == (self.sx, self.sy, self.frame_rate):
            #         print("\n*** {} ***".format(mode))
            #     else:
            #         print("{}".format(mode), end=" ")
            # self._cap.frame_mode = (self.sx, self.sy, self.frame_rate)

            self.sy = config['ResY']
            self.sx = config['ResX']
            self.offset_x = config.get('OffsetX',0)
            self.offset_y = config.get('OffsetY',0)

            self.frame_rate = config['FrameRate']

            self._camera.set_region (self.offset_x,self.offset_y,self.sx,self.sy)
            self._camera.set_frame_rate (self.frame_rate)
            self._camera.set_exposure_time(0.95/self.frame_rate * 1e6) # max out exposure by default
            
            self.mode = config.get('Mode', 'Mono8')
            if self.mode not in ['Mono8', 'YUV422', 'Bayer_RG8']:
                raise ValueError('Unsupported video mode.')

            if self.mode == 'Mono8':
                self._camera.set_pixel_format (Aravis.PIXEL_FORMAT_MONO_8)
                self._bytes_per_pixel = 1
            elif self.mode == 'YUV422':
                self._camera.set_pixel_format (Aravis.PIXEL_FORMAT_YUV_422_PACKED)
                self._bytes_per_pixel = 2
            elif self.mode == 'Bayer_RG8':
                self._camera.set_pixel_format (Aravis.PIXEL_FORMAT_BAYER_RG_8)
                self._bytes_per_pixel = 1
            else:
                raise ValueError('Unsupported video mode.')
            payload = self._camera.get_payload ()

            [x,y,width,height] = self._camera.get_region ()

            # Initialize two numpy buffers for deBayer'ing
            self._rgb_img = np.zeros((height, width,3))  # converted image data is RGB
            self._conversion_required = False
            for q in self._queues:
                if q.frame_type in ['img', 'img_nonblocking']:
                    self._conversion_required = True

            print ("Camera vendor : %s" %(self._camera.get_vendor_name ()))
            print ("Camera model  : %s" %(self._camera.get_model_name ()))
            print ("ROI           : %dx%d at %d,%d" %(width, height, x, y))
            print ("Payload       : %d" %(payload))
            print ("Pixel format  : %s" %(self._camera.get_pixel_format_as_string ()))
            # self.number_of_channels = 3 # TODO: Consider handling mono?

            # logging.basicConfig(level=logging.CRITICAL)

            # print("\nCamera Controls (*** set as specified in CameraParams)")
            # for c in self._cap.controls:
            #     if 'CameraParams' in config:
            #         if c.display_name in config['CameraParams']:
            #             c.value = config['CameraParams'][c.display_name]
            #             print("*** {}: {}".format(c.display_name, c.value))
            #         else:
            #             print("    {}: {}".format(c.display_name, c.value))

            # # HACK: In some older C920 models, the focus resets to an old value when
            # # capture is started. You first must set the focus value, then start
            # # capturing, and then reset the focus value again.
            # frame = self._cap.get_frame_timeout(2/self.frame_rate)
            # del frame
            # for c in self._cap.controls:
            #     if c.display_name in config.get('CameraParams', []) \
            #        and c.display_name == 'Absolute Focus':
            #         c.value = config['CameraParams'][c.display_name]

            self._stream = self._camera.create_stream (None, None)

            for i in range(0,10): # Is 10 enough?
                self._stream.push_buffer (Aravis.Buffer.new_allocate (payload))

        def debayer(self, img):
            if self.mode == 'Mono8': # no need!
                self._rgb_img = np.frombuffer(img, np.uint8).reshape(self.sy, self.sx,1) # this is a cast!
            elif self.mode == 'Bayer_RG8':
                img_np = np.frombuffer(img, np.uint8).reshape(self.sy, self.sx) # this is a cast
                self._rgb_img = cv2.cvtColor(img_np, cv2.COLOR_BayerBG2BGR)

        def run(self):
            print ("Start acquisition")
            self._camera.start_acquisition ()
            print ("Acquisition")
            while not check_shm(self._terminate_flag):
                image = self._stream.pop_buffer ()
                if image:
                    if self._conversion_required:
                        self.debayer(image.get_data())
                    for q in self._queues:
                        if not check_shm(self._terminate_flag):
                            if q.frame_type == 'raw':
                                q.put((image.get_data(), image.get_system_timestamp())) # ISSUE: system timestamps are CLOCK_REALTIME not CLOCK_MONOTONIC
                            elif q.frame_type == 'img':
                                q.put((self._rgb_img, image.get_system_timestamp()))
                            elif q.frame_type == 'img_nonblocking':
                              if q.is_active():
                                  # Unlike the video write process, we can afford
                                  # to drop frames for the visualization process.
                                  try:
                                    q.put((self._rgb_img, 
                                        image.get_system_timestamp()), block=False)
                                  except queue.Full:
                                      continue
                            elif q.frame_type == 'jpeg':
                                pass
                                # q.put((frame.jpeg_raw, frame.timestamp))
                            else:
                                raise(ValueError("Camera interface frame type not understood ({}).".format(q.frame_type)))
                    self._stream.push_buffer (image)

            print ("Stop acquisition")
            self._camera.stop_acquisition ()
            self._camera = None

        def close(self):
            if self._camera:
                self._camera.stop_acquisition ()


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
