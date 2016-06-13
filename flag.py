#!/usr/bin/python

import sys
import os
import numpy as np
import pyaudio
import time
import wave
from dejavu import Dejavu
import json
import signal

CHUNK = 8192
WIDTH = 2
CHANNELS = 1
RATE = 44100
FORMAT = pyaudio.paInt16
DJV_CONFIG = 'dejavu.conf'

class Flagger(object):

    frames = []

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.data = []
        self.channels = 1
        self.chunksize = 8192
        self.format = pyaudio.paInt16
        self.samplerate = 44100
        self.recording = False
        self.wave_file = self.prepare_file('flag.wav', 'wb')
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.samplerate,
            input=True,
            frames_per_buffer=self.chunksize,
            stream_callback=self.get_callback()
        )
        self.stream.stop_stream()
        self.djv = self.dejavu_init()

    def dejavu_init(self):
        try:
          with open(DJV_CONFIG) as f:
            config = json.load(f)
        except IOError as err:
          logger.debug("Cannot open Dejavu config: %s. Exiting" % (str(err)))
          sys.exit(1)
        return Dejavu(config)

    def prepare_file(self, fname, mode='wb'):
        wavefile = wave.open(fname, mode)
        wavefile.setnchannels(self.channels)
        wavefile.setsampwidth(self.audio.get_sample_size(self.format))
        wavefile.setframerate(self.samplerate)
        return wavefile

    def start_recording(self):
        self.recording = True
        self.wave_file = self.prepare_file('flag.wav', 'wb')
        self.stream.start_stream()
        stop = raw_input('recording...\npress return to stop recording')
        self.stop_recording()

    def get_callback(self):
        def callback(in_data, frame_count, time_info, status):
            self.wave_file.writeframes(in_data)
            return in_data, pyaudio.paContinue
        return callback

    def stop_recording(self):
        self.stream.stop_stream()
        self.wave_file.close()
        
        do_fingerprint = raw_input('fingerprint new file? (enter y or n)')
        
        if do_fingerprint == 'y':
            name = self.rename_file()
            self.fingerprint_file(name)
            os.remove(name)

        self.wait_for_record()

    def wait_for_record(self):
        start = raw_input('press return to start recording')
        self.start_recording()

    def rename_file(self):
        new_name = raw_input('name file (exclude .wav) -->')
        os.rename('flag.wav', new_name + '.wav')
        return new_name + '.wav'

    def fingerprint_file(self, name):
        self.djv.fingerprint_file(name)

    def signal_handler(self, signal, frame):
        self.quit()

    def quit(self):
        print '\n'
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()
        if os.path.isfile('flag.wav'):
            os.remove('flag.wav')
        sys.exit(0)

if __name__ == '__main__':
    
    flagger = Flagger()

    signal.signal(signal.SIGINT, flagger.signal_handler)

    flagger.wait_for_record()

    flagger.quit()