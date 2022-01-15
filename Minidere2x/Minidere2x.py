# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                                                 #
#                                                                                                 #
#                                                                                                 #
#       +=================================================================================+       #
#       |                                 MIT License                                     |       #
#       +=================================================================================+       #
#       |    - Copyright (c) 2021-2022, Tremeschin                                        |       #
#       +=================================================================================+       #
#       |                                                                                 |       #
#       | Permission is hereby granted, free of charge, to any person obtaining a copy    |       #
#       | of this software and associated documentation files (the "Software"), to deal   |       #
#       | in the Software without restriction, including without limitation the rights    |       #
#       | to use, copy, modify, merge, publish, distribute, sublicense, and/or sell       |       #
#       | copies of the Software, and to permit persons to whom the Software is furnished |       #
#       | to do so, subject to the following conditions:                                  |       #
#       |                                                                                 |       #
#       | The above copyright notice and this permission notice shall be included in all  |       #
#       | copies or substantial portions of the Software.                                 |       #
#       |                                                                                 |       #
#       +=================================================================================+       #
#       |                                                                                 |       #
#       | THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR      |       #
#       | IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,        |       #
#       | FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE     |       #
#       | AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER          |       #
#       | LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,   |       #
#       | OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE   |       #
#       | SOFTWARE.                                                                       |       #
#       |                                                                                 |       #
#       +=================================================================================+       #
#                                                                                                 #
#                                                                                                 #
#                                                                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import sys as System

System.dont_write_bytecode = True

import io
import itertools as Itertools
import math as Math
import multiprocessing as Multiprocessing
import socket
import subprocess as Subprocess
from copy import deepcopy as DeepCopy
from math import inf as Infinity
from pathlib import Path
from subprocess import PIPE
from threading import Thread
from time import sleep as Sleep
from time import time as Now

import numpy as NumPy
import zmq as ZeroMQ
from halo import Halo
from imageio_ffmpeg import get_ffmpeg_exe as ImageIOGetFFmpegBinary
from loguru import logger as Loguru
from PIL import Image
from waifu2x_ncnn_vulkan_python import Waifu2x as W2X

# Set up logging
Loguru.remove()
LogFormat = (
    "[<green>{elapsed.seconds:4}s</green>]─"
    "[<level>{level:7}</level>]"
    "<level> ⏵ {message}</level>"
)
Loguru.add(System.stdout, colorize=True, format=LogFormat, level="TRACE")

LogInfo     = Loguru.info
LogWarn     = Loguru.warning
LogError    = Loguru.error
LogDebug    = Loguru.debug
LogTrace    = Loguru.trace
LogSuccess  = Loguru.success
LogCritical = Loguru.critical

from Yatch import *

R = YatchRestrictions
Yatch.YourProjectInfo = "> Minidere2x also made by Tremeschin!! Thanks to akai-katto for original Dandere2x idea and implementation."

class Minidere2x:
    def __init__(self):
        self.FFmpegBinary = ImageIOGetFFmpegBinary()
        self._BaseFFmpegCommand = [self.FFmpegBinary, "-hwaccel", "auto", "-hide_banner"]
        self.dtype = NumPy.uint8

    def _GetFreeTcpPort(self):
        TempSocket = socket.socket()
        TempSocket.bind(('', 0))
        Port = TempSocket.getsockname()[1]
        TempSocket.close()
        return Port

    def GetTotalFrames(self, FilePath) -> int:
        """Decodes the whole video with -vsync 1 (CRF) and voids the output, we read the total
        frames that were decoded and that hopefully will be a CRF-ed video frame count.
        Not the fastest, but safest? Highly depends on CPU and encoding of the input video.
        """
        FFmpegCommand = self._BaseFFmpegCommand + ["-vsync", "1", "-i", str(FilePath), "-f", "null", "-"]
        LogInfo(f"Finding Frame Count via null decoding (accurate), May take a while for longer videos..")
        LogTrace(f"Command: {FFmpegCommand}")
        with Halo(text="Waiting for command to finish..", spinner="dots"):
            Parse = Subprocess.run(FFmpegCommand, stdout=PIPE, stderr=PIPE)
        return int(Parse.stderr.decode("utf-8").split("frame=")[-1].split("fps=")[0].strip())

    def GetVideoResolution(self, FilePath) -> (int, int):
        """Read the first frame of the video, load the image in PIL and return the width, height.
        Should be safer than reading info from the container generally speaking.
        """
        FFmpegCommand = self._BaseFFmpegCommand + ["-i", str(FilePath), "-vframes", "1", "-f", "image2pipe", "-"]
        Parse = Subprocess.run(FFmpegCommand, stdout=PIPE, stderr=PIPE)
        Frame = Image.open(io.BytesIO(Parse.stdout), formats=["jpeg"])
        return (Frame.width, Frame.height)

    def _GetRawFrames(self, FilePath) -> NumPy.ndarray:
        """Pipes the raw frames to stdout, converts the bytes to NumPy arrays of RGB data.
        This is a generator so usage is (for Frame in self._GetRawFrames(Video))"""
        FFmpeg = Subprocess.Popen([
            self.FFmpegBinary, "-vsync", "1", "-loglevel", "panic",
            "-i", str(FilePath), "-c:v", "rawvideo", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "-an",  "-"
        ], stdout=Subprocess.PIPE)

        while True:
            if not (Raw := FFmpeg.stdout.read(self.Width * self.Height * 3)): break
            yield NumPy.frombuffer(Raw, dtype=self.dtype).reshape((self.Height, self.Width, -1))
    
    def _UpwardsClosestMultiple(self, Number, Divisor):
        """Given a Number and a Divison find the nearest number greater than Number
        such that Number/Division yields zero remainder"""
        for i in Itertools.count(Number):
            if i % Divisor == 0: return i

    def _ResidualCoordinates(self, SideLength):
        for Y in range(SideLength):
            for X in range(SideLength):
                yield NumPy.array([X, Y])

    def Upscale(self,
        InputPath          = Yarg(Path,  ...,       R.PathExists,             Identifiers=["--Input", "--input", "-i"],          Help="(Input/Output) Input Video for Processing, can be Single File or Folder of Videos.", List=True),
        OutPath            = Yarg(Path,  "auto",                              Identifiers=["--Output", "--output", "-o"],        Help="(Input/Output) Path of the Output Video(s). 'auto' will add a suffix to the file on the same directory where input source is with minimal information about settings. Giving a folder will keep original names under the Output Directory."),
        Overwrite          = Yarg(bool,  True,                                Identifiers=["--Overwrite", "--overwrite"],        Help="(Input/Output) If the Output File already exists, overwrite it automatically? Might lose data if finished upscaling and run twice."),
        Upscaler           = Yarg(str,   "Waifu2x", R.InList(["Waifu2x"]),    Identifiers=["--Upscaler", "--upscaler"],          Help="(Upscalers) Which upscaler to use? Each upscaler might have its own custom options."),
        Passes             = Yarg(int,   1,         R.Positive,               Identifiers=["--Passes", "--passes"],              Help="(Upscalers) How many times to pass the Residual Image to the Upscaler? Gets (4**N) times slower and yields (2**N) resolution (single dimension). Eg. passes=1 for 1080p yields 2160p video, passes=2 for 480p yields 1920p video."),
        Video2x            = Yarg(bool,  False,                               Identifiers=["--Video2x", "--video2x"],            Help="(Upscalers) Run in Video2x-like mode where every frame is upscaled on its entirety. Completely disables block matching. Very slow, highest quality available."),
        Parallel           = Yarg(int,   1,         R.Positive,               Identifiers=["--Parallel", "--parallel"],          Help="(Minidere2x) How many parallel video files will be processed independently? Memory usage scales linearly, Generally saturates at 2. Block matching will get slower as this is run on the Main Thread but should be faster than the Upscaler anyways."),
        Workers            = Yarg(int,   2,         R.Positive,               Identifiers=["--Workers", "--workers", "-W"],      Help="(Minidere2x) How many parallel processes of Python to do upscale-only with their own Upscaler running, per parallel process? VRAM increases linearly. Usually saturates GPU at N=2. Prefer higher number for very still input sources, maybe 3 or 4."),
        TooMany            = Yarg(float, 2,         R.InsideRange(0, 100),    Identifiers=["--TooMany", "--too_many"],           Help="(Block Matching) If the difference between ReferenceFrame and NewFrame is approximately greater than this percentage, upscale the full frame instead of building a Residual frame. This is for minimizing quality loss on too many blocks to upscale. A value of 0 is the same as Video2x mode."),
        BlockSize          = Yarg(int,   20,        R.Positive,               Identifiers=["--BlockSize", "--block_size"],       Help="(Block Matching) Internal Block Size. Usually 20 is good for everything, prefer 30 or 40 for 1080p content. Quality decreases with lower values. Speed increases somewhat exponentially both if too low or too high due CPU and GPU respectively."), 
        Bleed              = Yarg(int,   2,         R.Positive,               Identifiers=["--Bleed", "--bleed"],                Help="(Block Matching) Extra pixels we crop from the borders. Decreases performance"), 
        Scale              = Yarg(int,   2,         R.GreaterThanOrEqual(0),  Identifiers=["--Scale", "--scale", "-s"],          Help="(Upscaler: Any) Upscaler upscale ratio. Depends on the upscaler. Check nihui's repo on the one you're using for accurate info if ncnn Vulkan."),
        NCNN_GPUID         = Yarg(int,   0,         R.GreaterThanOrEqual(-1), Identifiers=["--GPUID", "--gpuid", "-g"],          Help="(Upscaler: Any ncnn Vulkan) GPU id to use, -1 is CPU."),
        NCNN_Denoise       = Yarg(int,   3,         R.GreaterThanOrEqual(-1), Identifiers=["--Denoise", "--denoise", "-n"],      Help="(Upscaler: Any ncnn Vulkan) Denoise of the upscaler. Depends on the upscaler, usually more means more 'plastic' images. Check nihui's repo on the one you're using for accurate info"),
        NCNN_TileSize      = Yarg(int,   200,       R.Positive,               Identifiers=["--TileSize", "--tile_size", "-t"],   Help="(Upscaler: Any ncnn Vulkan) Tile size of the upscaler. VRAM usage increases exponentially, approximately (1GB)(2**(TileSize/200)). Not really improvement past 200."),
        NCNN_TTA           = Yarg(bool,  False,                               Identifiers=["--TTA", "--tta", "-x"],              Help="(Upscaler: Any ncnn Vulkan) Enable TTA mode on nihui's *ncnn-vulkan. I don't know what it does but it's available. Significantly longer upscale speeds"),
        Waifu2xModel       = Yarg(int,   0,         R.InsideRange(0, 2),      Identifiers=["--Waifu2xModel", "--waifu2x_model"], Help="(Upscaler: Waifu2x) Model to use on Waifu2x. [0: Cunet] [1: Upconv Anime] [2: Upconv Photo]."),
        FFmpeg_vcodec      = Yarg(str,   "libx264",                           Identifiers=["-vcodec", "-v:c"],                   Help="(FFmpeg) Same functionality"),
        FFmpeg_acodec      = Yarg(str,   "copy",                              Identifiers=["-acodec", "-a:c"],                   Help="(FFmpeg) Same functionality"),
        FFmpeg_vf          = Yarg(str,                                        Identifiers=["-vf"],                               Help="(FFmpeg) Same functionality. This default one attempts to reduce blockiness", Default="deband=range=8:blur=false,pp7=qp=2:mode=medium", List=True),
        FFmpeg_preset      = Yarg(str,   "slow",                              Identifiers=["-preset"],                           Help="(FFmpeg) Same functionality."),
        FFmpeg_ExtraInput  = Yarg(str,   "",                                  Identifiers=["-ffinput"],                          Help="(FFmpeg) Extra settings on FFmpeg BEFORE input targets."),
        FFmpeg_ExtraOutput = Yarg(str,   "",                                  Identifiers=["-ffoutput"],                         Help="(FFmpeg) Extra settings on FFmpeg AFTER input targets."),
    ):
        self.UpscaleFactor = self.Scale**self.Passes

        if self.Video2x: LogWarn("Video2x Mode is Active, all Minidere2x commands technically ignored")

        # # Waifu2x
        if self.Upscaler == "Waifu2x":
            self.Waifu2xModel = {0: "models-cunet", 1: "models-upconv_7_anime_style_art_rgb", 2: "models-upconv_7_photo"}[self.Waifu2xModel]
            LogInfo(f"Model selected for Waifu2x is [{self.Waifu2xModel}]")

        Inputs = [File for File in self.InputPath.glob("*") ]

    def _Run(self):
        ...

def Main():
    M2X = Minidere2x()
    Yatch(Function=M2X.Upscale, CommandName="upscale")
    Yatch.Run()

if __name__ == "__main__":
    Main()
