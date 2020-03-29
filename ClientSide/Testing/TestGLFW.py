import glfw


def main():

    if not glfw.init():
        return

    monitors = glfw.get_monitors()
    print('Monitors')

    print(glfw.get_monitor_name(monitors[0]))
    print(glfw.get_monitor_name(monitors[1]))

    print(glfw.get_video_mode(monitors[0]))
    print(glfw.get_video_mode(monitors[1]))

    print(glfw.get_video_modes(monitors[0]))
    print(glfw.get_video_modes(monitors[1]))

    window = glfw.create_window(
        1024, 768, "Opengl GLFW Window", monitors[1], None)

    if not window:
        glfw.terminate()
        return

    glfw.make_context_current(window)

    while not glfw.window_should_close(window):
        glfw.poll_events()
        glfw.swap_buffers(window)

    glfw.terminate()


if __name__ == "__main__":
    main()
