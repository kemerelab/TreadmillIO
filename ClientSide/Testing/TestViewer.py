import matplotlib.pyplot as plt
import numpy as np
import time

def launch_viewer():
    plt.ion()
    #plt.show()
    fig, ax = plt.subplots()

    N = 100
    t = np.empty([N])*np.nan
    r = np.empty([N])*np.nan
    h, = ax.plot(t, r)

    for i in range(2*N):
        t[i%N] = i
        r[i%N] = i**2

        h.set_xdata(np.roll(t, -i%N - 1))
        h.set_ydata(np.roll(r, -i%N - 1))

        ax.relim()
        ax.autoscale_view()
        #plt.pause(0.001)
        #fig.canvas.draw_idle()
        fig.canvas.start_event_loop(0.0001)

if __name__ == "__main__":
    launch_viewer()