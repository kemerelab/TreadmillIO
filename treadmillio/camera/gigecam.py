import sys, os, setproctitle, signal, time

import multiprocessing
import queue

def check_shm(shm_var):
    with shm_var.get_lock():
        value = shm_var.value
    return value

def set_shm(shm_var):
    with shm_var.get_lock():
        shm_var.value = True

# GLOBALS
all_queues = []
producer_finished_flags = {}
consumer_finished_flags = {}
all_processes = {}
num_cameras = 0
terminate_flag = multiprocessing.Value('b', False) # This is the global flag that is used to signal that the whole edice should collapse gracefully
control_c_counter = 0

def termination_handler(signal, frame):
    global control_c_counter
    control_c_counter = control_c_counter + 1

    # global terminate_flag
    # set_shm(terminate_flag)
    print("SIGINT triggered in primary handler. Try pressing CTRL-C a second time if things don't terminate.")

    # This bit of code is for the SECOND time we CTRL-C
    global all_processes
    if control_c_counter > 1:
        if all_processes:
            all_processes_keys = list(all_processes.keys())
            for procname in all_processes_keys:
                print('Testing aliveness of {}.'.format(procname))
                if not all_processes[procname].is_alive():
                    print('It was defunct!')
                    del all_processes[procname]
                    if procname in producer_finished_flags:
                        producer_finished_flags[procname].value = True
                    elif procname in consumer_finished_flags:
                        consumer_finished_flags[procname].value = True
                else:
                    print('Still alive')

    # Nobodies alive anymore
    if not all_processes:
        sys.exit()

    for flagname, flag in producer_finished_flags.items():
        print('Waiting on {}'.format(flagname))
        while not flag.value: # no lock!
            pass
        print('Finished waiting for {} to finish.'.format(flagname))

    for flagname, flag in consumer_finished_flags.items():
        print('Waiting on {}'.format(flagname))
        while not flag.value: # no lock!
            pass
        print('Finished waiting for {} to finish.'.format(flagname))

    time.sleep(0.1) # give a second for the queue background process (thread?) to finish loading data
    global all_queues
    while all_queues:
        for q in all_queues:
            print('draining queue', q)
            try:
                q.get_nowait()
            except queue.Empty:
                print('removing', q)
                all_queues.remove(q)

    for procname, proc in all_processes.items():
        print('Waiting for {} to join.'.format(procname))
        proc.join()

    print('All camera processes joined.')

    sys.exit()


try:
    from treadmillio.camera.videowriter import start_writer
    from treadmillio.camera.camerainterface import start_camera
    from treadmillio.camera.camerawindow import start_window
except ModuleNotFoundError:
    from videowriter import start_writer
    from camerainterface import start_camera
    from camerawindow import start_window


from multiprocessing.queues import Queue
class LabeledQueue(Queue):
    def __init__(self, frame_type='img', *args,**kwargs):
        ctx = multiprocessing.get_context()
        super(LabeledQueue, self).__init__(*args, **kwargs, ctx=ctx)
        self.frame_type = frame_type
        self._active = multiprocessing.sharedctypes.RawValue('b', True)

    def is_active(self):
        return self._active.value

    def pause(self):
        self._active.value = False

    def restart(self):
        self._active.value = True

def RunCameraInterface(config, no_escape=True):
    global num_cameras
    num_cameras = num_cameras + 1
    # Initialize queues used to communicate between processes
    # The frame_type determines whether the queues are filled with raw data, or debayered data
    videowriter_queue = LabeledQueue(frame_type='img') 
    viewer_queue = LabeledQueue(frame_type='img_nonblocking')

    do_record = config.get('RecordVideo', False)
    if do_record:
        frame_queues = [viewer_queue, videowriter_queue]
    else:
        print('NOT RECORDING!!!')
        frame_queues = [viewer_queue]

    # We'll draing when we terminate!
    global all_queues # needs to be global so that SIGINT can access
    all_queues.extend(frame_queues)
    signal.signal(signal.SIGINT, termination_handler)

    camera_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the camera acquisition process has terminated
    global producer_finished_flags
    producer_finished_flags['Camera{}'.format(num_cameras)] = camera_process_finished

    global terminate_flag
    camera_process = multiprocessing.Process(target=start_camera, 
        args=(config, frame_queues, terminate_flag, camera_process_finished))
    camera_process.daemon = True
    global all_processes
    all_processes['Camera{}'.format(num_cameras)] = camera_process
    camera_process.start()     # Launch the camera frame acquisition process


    global consumer_finished_flags

    if do_record:
        vwriter_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the video writing process has terminated
        consumer_finished_flags['Writer{}'.format(num_cameras)] = camera_process_finished
    
        vwriter_process = multiprocessing.Process(target=start_writer, args=(config, videowriter_queue, terminate_flag, vwriter_process_finished))
        vwriter_process.daemon = True
        all_processes['Writer{}'.format(num_cameras)] = vwriter_process
        vwriter_process.start()     # Launch the video writing process

    # Create the main pyglet window
    time.sleep(0.1)
    pyglet_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the camera acquisition process has terminated
    consumer_finished_flags['Pyglet{}'.format(num_cameras)] = pyglet_process_finished

    pyglet_process = multiprocessing.Process(target=start_window, args=(config, viewer_queue, terminate_flag, pyglet_process_finished, no_escape))
    pyglet_process.daemon = True

    all_processes['Pyglet{}'.format(num_cameras)] = camera_process
    pyglet_process.start()     # Launch the camera frame acquisition process

    return terminate_flag
    #### That's all folks!!!

def main():
    if len(sys.argv) > 1:
        camera = int(sys.argv[1])
    else:
        camera = 0
        print("Using camera ", camera)

    config = {
        'RecordVideo': True,
        'Mode': 'Bayer_RG8',
        'FilenameHeader': 'videodata',
        'Compress': False,
        'LogDirectory': os.getcwd(),
        'CameraIndex': camera,
        'ResX': 1024, 'ResY': 768, 'FrameRate': 30,
        'CameraParams': {
            'Power Line frequency': 2, # 60 Hz
            'Gain': 10
        }

    }

    multiprocessing.current_process().name = "python3 GigE Main"
    setproctitle.setproctitle(multiprocessing.current_process().name)

    RunCameraInterface(config)
    while True:
        time.sleep(0.1)


if __name__ == '__main__':
    main()
