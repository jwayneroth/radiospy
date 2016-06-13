#!/usr/bin/python

import pyaudio
import sys
import os
import time

CHUNK = 16384#8192
WIDTH = 2
CHANNELS = 1 #2
RATE = 44100

p = pyaudio.PyAudio()

# Open input stream using default device:
stream_input = p.open(format=p.get_format_from_width(WIDTH),
                      channels=CHANNELS,
                      rate=RATE,
                      input=True,
                      frames_per_buffer=CHUNK
)

# Open out stream using default device:
stream_output = p.open(format=p.get_format_from_width(WIDTH),
                       channels=CHANNELS,
                       rate=RATE,
                       output=True,
                       frames_per_buffer=CHUNK
)

if __name__ == '__main__':

  while True:

    try:
      data = stream_input.read(CHUNK)
    except IOError as ex:
      if ex[1] != pyaudio.paInputOverflowed:
        raise
      data = '\x00' * CHUNK

    stream_output.write(data, CHUNK)
        
  stream_input.stop_stream()
  stream_output.stop_stream()
  stream_input.close()
  stream_output.close()
  p.terminate()