# NOTES
# 
# Should I use mp.Queue or mp.Pipe? Pipe seems to give more control,
# but if it becomes full, it can actually block send_bytes, which
# is problematic. Queue, on the other hand, allows you to check 
# for a full buffer and react accordingly, so it won't block on 
# the send end. (https://stackoverflow.com/a/44924898/8066298)
#
# Ideally, each Viewer (Sound, StateMachine, CurrentState) would run
# in a separate process. Then, multiple competing objects in CurrentState
# would be managed with multithreading (acquiring lock to update shared
# figure).
#
# Need to do more testing to ensure that this rarely, if ever, holds up
# the main behavior loop (taking more than 2 ms).


import multiprocessing as mp
import pickle
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from inspect import signature
import time
import networkx as nx

class FigIDs:
    StateViewer = 1
    SoundViewer = 2

class Viewer:

    def __init__(self):
        # Set params
        self.q = None
        self.running = False

    def __call__(self, conn):
        """Launch separate process to periodically update state graphic."""
        # Start updating
        plt.ion()
        #plt.show(block=False)
        self.start()
        self.refresh()
        self.running = True
        self.conn = conn
        #self.q = q
        while self.running:
            # Collect data in intervals
            data = None
            while self.conn.poll():
            #while not self.q.empty():
                # Get data
                data = pickle.loads(self.conn.recv_bytes())
                #data = pickle.loads(self.q.get(block=True))

                # Convert all data to dict for consistency
                if not isinstance(data, dict):
                    raise ValueError('Message type not understood.')
                if data.pop('priority', 1) < 1:
                    # Flush low-priority messages if buffer full
                    continue
                else:
                    break
            
            if data is not None:
                # Update figure
                self.update(data)

                # Refresh figure
                self.refresh()

    def refresh(self):
        # This can be tricky. See e.g. https://stackoverflow.com/a/45734500/8066298
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.canvas.draw_idle()
        #self.fig.canvas.flush_events()
        self.fig.canvas.start_event_loop(0.001)

    def start(self):
        pass

    def __del__(self):
        self.running = False

    def update(self, data):
        pass
        #if 'reset' in data.items():
        #    self.fig.clf()


class SoundStimulusViewer(Viewer):

    def __init__(self, stimuli, min_gain=-90.0, max_gain=90.0):
        Viewer.__init__(self)

        self.stimuli = stimuli # {'name': gain}
        self.min_gain = min_gain
        self.max_gain = max_gain

    def start(self):
        Viewer.start(self)

        self.fig, self.ax = plt.subplots()
        
        # Create image for each stimulus
        self.imgs = {}
        width = 0.3
        for i, (name, init_gain) in enumerate(self.stimuli.items()):
            extent = (i - width/2, i + width/2, self.min_gain, max(init_gain, self.min_gain+1))
            self.imgs[name] = self._set_image(init_gain, extent)
        self.ax.set_xticks(np.arange(len(self.stimuli)))
        self.ax.set_xticklabels([s for s, g in self.stimuli.items()])
        for tick in self.ax.get_xticklabels():
            tick.set_rotation(45)
        self.ax.set_aspect(len(self.stimuli)/(self.max_gain - self.min_gain))

    def _set_image(self, gain, extent):
        X = (np.linspace(gain, self.min_gain, 1000) - self.min_gain) # reverse order for images
        X = X[:, np.newaxis] / (self.max_gain - self.min_gain) # normalize
        return self.ax.imshow(X, 
                              extent=extent, 
                              vmin=0.0, 
                              vmax=1.0, 
                              cmap='coolwarm')

    def update(self, data):
        Viewer.update(self, data)

        for cmd, val in data.items():
            if cmd in self.stimuli:
                # Update gain
                print(cmd, val)
                self.stimuli[cmd] = val

                # Plot rolled buffers (this works even when partially empty)
                extent = self.imgs[cmd].get_extent()[:-1] + (max(val, self.min_gain+1),)
                self.imgs[cmd].remove()
                del self.imgs[cmd]
                self.imgs[cmd] = self._set_image(val, extent)
                self.ax.set_aspect(len(self.stimuli)/(self.max_gain - self.min_gain))


class StateMachineViewer(Viewer):

    def __init__(self, graph):
        Viewer.__init__(self)

        self.AGraph = graph
        self.NGraph = nx.nx_agraph.from_agraph(graph)

    def start(self):
        Viewer.start(self)

        # Create figure
        self.fig, self.ax = plt.subplots()
        self.ax.margins(x=0.25, y=0.25) # some padding for state labels

        # Color scheme
        plt.set_cmap('ocean') # putting this here avoids creating extra figure
        self.off_color = 0.50
        self.on_color = 0.15

        # Draw network (from nx.draw_networkx())
        self._pos = nx.drawing.kamada_kawai_layout(self.NGraph) # spring layout also okay
        self._c = self.off_color*np.ones([len(self.AGraph.nodes())]) # see set_array()
        self._idx = 0 # index of current state
        self._nodes = nx.draw_networkx_nodes(self.NGraph, 
                                             self._pos, 
                                             node_size=500,
                                             node_colors=self._c,
                                             ax=self.ax)
        self._nodes.set_clim([0.0, 1.0]) # set cmap limits for PathCollection object
        self._edges = nx.draw_networkx_edges(self.NGraph, 
                                             self._pos, 
                                             arrows=True, 
                                             ax=self.ax)
        self._labels = nx.draw_networkx_labels(self.NGraph, 
                                               self._pos,
                                               font_size=7,
                                               font_weight='bold',
                                               ax=self.ax)

    def update(self, data):
        Viewer.update(self, data)

        for state, _ in data.items():
            # Error checking
            if state not in self.AGraph.nodes(): # list of state names
                raise ValueError('State {} not in graph.'.format(state))

            # Get state index
            self._c[self._idx] = self.off_color
            self._idx = self.AGraph.nodes().index(state)
            self._c[self._idx] = self.on_color
            self._nodes.set_array(self._c) # passes floats for cmap colors


class StateViewer(Viewer):

    def __init__(self):
        """Base class for current state window."""
        Viewer.__init__(self)

    def start(self):
        Viewer.start(self)

        # Grab figure (or create if not yet exists)
        if FigIDs.StateViewer in plt.get_fignums():
            self.fig = plt.figure(FigIDs.StateViewer)
            self.ax = self.fig.axes[0]
        else:
            self.fig, self.ax = plt.subplots(num=FigIDs.StateViewer)
            self.ax.set_title('Current State')


class PatchViewer(StateViewer):

    def __init__(self):
        StateViewer.__init__(self)

        # Set data buffers
        self.N = 10000 # buffer size
        self.reset()

    def start(self):
        StateViewer.start(self)

        # Plot initial buffers
        self.h1, = self.ax.plot(self.t, self.r)

    def update(self, data):
        StateViewer.update(self, data)

        for cmd, val in data.items():
            if cmd.lower() == 'reward':
                # Update buffers
                self.t[self.p], self.r[self.p] = val

                # Plot rolled buffers (this works even when partially empty)
                self.h1.set_xdata(np.roll(self.t, -self.p-1))
                self.h1.set_ydata(np.roll(self.r, -self.p-1))

                # Update position
                self.p = (self.p + 1) % self.N

            elif cmd.lower() == 'reset':
                params = val
                self.reset()

    def reset(self):
        print('resetting')
        self.t = np.empty([self.N])
        self.t.fill(np.nan)
        self.r = np.empty([self.N])
        self.r.fill(np.nan)
        self.p = 0 # current buffer position


VIEWER_TYPES = {'SoundStimulus': SoundStimulusViewer,
                'PatchState': PatchViewer,
                'StateMachine': StateMachineViewer}

def launch_viewer(viewer_type, *args, **kwargs):
    try:
        v = VIEWER_TYPES[viewer_type](*args, **kwargs)
    except KeyError:
        raise NotImplementedError('Viewer {} not implemented.'.format(viewer_type))
    parent_conn, plt_conn = mp.Pipe()
    #q = mp.Queue()
    p_viewer = mp.Process(target=v, args=(plt_conn,), daemon=True)
    p_viewer.start()
    return parent_conn, p_viewer
    #return q, p_viewer