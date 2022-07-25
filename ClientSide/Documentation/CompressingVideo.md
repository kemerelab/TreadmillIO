# Notes on compressing videos

### Videos generated from GigE module
Videos generated from the GigE module are either going to be `.raw` or 
`.mjpeg` (an early bug had this as `.mjeg`) depending on whether the
`Compress` option is `Compress: False` or `Compress: True`. Furthermore, 
they will be either `Mode: Mono8` (mono, which is default) or 
`Mode: Bayer_RG8` (color) format. If they are color, the camera has 
been told to use a raw Bayer image format (the `Bayer_RG8` option),
but the video writer is writing frames that have already been converted
using OpenCV to `rgb24` format (in ffmpeg terms). You can use ffmpeg to
shrink the size of these videos even further.

**Note:** You need to know the video size, which should be found in your
`.yaml` configuration file.

# Compressing raw Mono8 videos
Assuming that original video is stored in `MouseCam.raw`, and was set up
with a video size of 1024x768 (`ResX: 1024` and `ResY: 768`), the 
following command will compress a raw `Mono8` video into a reasonable 
quality h264-compressed `.mp4`.

```
ffmpeg -f rawvideo -pix_fmt gray -video_size 1024x1000 -r 30 -i MouseCam.raw  -codec:v libx264 -vf format=gray -r 30 MouseCam.mp4
```

Sometimes in the dark, it can be helpful to boost the gamma of the
compressed video.

```
ffmpeg -f rawvideo -pix_fmt gray -video_size 1024x1000 -r 30 -i MouseCam.raw  -codec:v libx264 -vf format=gray,eq=gamma=1.5 -r 30 MouseCam.mp4
```

In testing, this compresses a 31 GB raw file to 4.1 MB. You can read up
on quality settings or use libx265 two pass encoding for even more gains.

# Compressing raw color videos
Things are pretty similar if the original video configured the camera as
`Bayer_RG8`. The only difference is that now we presumably want a final
video that is color. The default OpenCV format is equivalent to the
FFMPEG `bgr24` format, so the command becomes:

```
ffmpeg -f rawvideo -pix_fmt bgr24 -video_size 1024x768 -r 30 -i MouseCam.raw -codec:v libx264 -r 30 MouseCam.mp4
```

# Recompressing MJPEG videos
Again, things are similar if the original video was MJPEG compressed.
Now, the difference is that rather than the `rawvideo` input format,
we use `mjpeg`.

```
ffmpeg -f mjpeg -r 30 -i MouseCam.mjpeg -c:v libx264 -r 30  MouseCam.mp4
```

For a 20 MB mono mjpeg file, this compresses to a 400 KB mp4, and for a
108 MB color mjpeg file, this compresses to a 1.7 MB mp4.
