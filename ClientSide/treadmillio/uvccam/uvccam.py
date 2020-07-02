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

from treadmillio.webcam.videowriter import start_writer
from treadmillio.webcam.camerainterface import start_camera
from treadmillio.webcam.camerawindow import start_window

def RunCameraInterface(config, no_escape=True):
    global num_cameras
    num_cameras = num_cameras + 1
    # Initialize objects used to communicate between processes
    storage_frame_queue = multiprocessing.Queue() # This queue is filled by the camera acquisition process and emptied by the video writing process
    visualization_frame_queue = multiprocessing.Queue() # This queue is filled by the camera acquisition process and emptied by the (visualization) primary process

    do_record = config.get('RecordVideo', False)
    if do_record:
        frame_queues = [visualization_frame_queue, storage_frame_queue]
    else:
        print('NOT RECORDING!!!')
        frame_queues = [visualization_frame_queue]

    # We'll draing when we terminate!
    global all_queues
    all_queues.extend(frame_queues)
    signal.signal(signal.SIGINT, termination_handler)

    camera_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the camera acquisition process has terminated
    global producer_finished_flags
    producer_finished_flags['Camera{}'.format(num_cameras)] = camera_process_finished

    global terminate_flag
    camera_process = multiprocessing.Process(target=start_camera, args=(config, frame_queues, terminate_flag, camera_process_finished))
    camera_process.daemon = True
    global all_processes
    all_processes['Camera{}'.format(num_cameras)] = camera_process
    camera_process.start()     # Launch the camera frame acquisition process


    global consumer_finished_flags

    if do_record:
        vwriter_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the video writing process has terminated
        consumer_finished_flags['Writer{}'.format(num_cameras)] = camera_process_finished
    
        vwriter_process = multiprocessing.Process(target=start_writer, args=(config, storage_frame_queue, terminate_flag, vwriter_process_finished))
        vwriter_process.daemon = True
        all_processes['Writer{}'.format(num_cameras)] = vwriter_process
        vwriter_process.start()     # Launch the video writing process

    # Create the main pyglet window
    time.sleep(0.1)
    pyglet_process_finished = multiprocessing.RawValue('b', True) # This signals to the main process that the camera acquisition process has terminated
    consumer_finished_flags['Pyglet{}'.format(num_cameras)] = pyglet_process_finished

    pyglet_process = multiprocessing.Process(target=start_window, args=(config, visualization_frame_queue, terminate_flag, pyglet_process_finished, no_escape))
    pyglet_process.daemon = True

    all_processes['Pyglet{}'.format(num_cameras)] = camera_process
    pyglet_process.start()     # Launch the camera frame acquisition process

    print('Function exited')
    #### That's all folks!!!

def main():
    if len(sys.argv) > 1:
        camera = int(sys.argv[1])
    else:
        camera = 0
        print("Using camera ", camera)

    config = {
        'RecordVideo': True,
        'FilenameHeader': 'videodata',
        'LogDirectory': os.getcwd(),
        'CameraIndex': camera,
        'ResX': 640, 'ResY': 480, 'FrameRate': 30,
        'CameraParams': {
            'Power Line frequency': 2, # 60 Hz
            'Gain': 10
        }

    }

    RunCameraInterface(config)


if __name__ == '__main__':
    main()
