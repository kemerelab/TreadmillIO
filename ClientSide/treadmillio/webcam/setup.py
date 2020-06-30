import platform
import distutils.core
import Cython.Build
from distutils.extension import Extension  
import numpy

distutils.core.setup(
    ext_modules = Cython.Build.cythonize([
        Extension(
            name="uvc",
            sources=["uvc.pyx"],
            include_dirs=[numpy.get_include()],
            libraries=["rt", "uvc", "turbojpeg"])

    ])
)

