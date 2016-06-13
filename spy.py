#!/usr/bin/python

import pyaudio
import sys
import os
import numpy as np
import time
import wave
from dejavu import Dejavu
import json
import serial
import curses
import atexit
import logging

CHUNK = 8192
CHANNELS = 1
RATE = 44100
FORMAT = pyaudio.paInt16
REC_SECONDS = 5
REC_END = int(RATE / CHUNK * REC_SECONDS)
DJV_CONFIG = 'dejavu.conf'
SERIAL = '/dev/ttyACM0'
INSTRUCTIONS = "f=flagging, m=matching, q=quit"

logger = logging.getLogger('radiospy_logger')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('/home/jwr/pydocs/radiospy/spy.log','a')
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

#ch = logging.StreamHandler()
#ch.setLevel(logging.DEBUG)
#ch.setFormatter(formatter)
#logger.addHandler(ch)

class RadioSpy(object):
  def __init__(self):
    logger.debug('RadioSpy::__init__')

    atexit.register(self.quit)

    self.modes = ['matching', 'flagging', 'fingerprinting', 'naming']
    self.mode = 'matching'
    self.rec_data = [[]]
    self.rec_cnt = 0
    self.muted = False
    self.new_name = ''
    self.scryx = None
    self.log_height = 0
    self.log_y = 0

    self.pa = pyaudio.PyAudio()

    self.stream = self.pa.open(
      format=FORMAT,
      channels=CHANNELS,
      rate=RATE,
      input=True,
      frames_per_buffer=CHUNK,
    )
    self.stream.stop_stream()

    self.djv = self.dejavu_init()
    
    self.wave_file = self.prepare_file('wire.wav', 'wb')

    self.stdscr = self.curses_init()

    self.teensy = self.teensy_init()

  def dejavu_init(self):
    try:
      with open(DJV_CONFIG) as f:
        config = json.load(f)
    except IOError as err:
      logger.debug("Cannot open Dejavu config: %s. Exiting" % (str(err)))
      sys.exit(1)
    return Dejavu(config)

  def curses_init(self):
    stdscr = curses.initscr()
    stdscr.nodelay(1)
    curses.noecho()
    curses.cbreak()
    scryx = stdscr.getmaxyx()
    if scryx[1] > len(INSTRUCTIONS):
      stdscr.addstr(scryx[0]-1, 0, INSTRUCTIONS, curses.A_REVERSE)
    self.scryx = scryx
    self.log_height = scryx[0] - 2
    return stdscr

  def curses_mode(self, mode):
    scr = self.stdscr
    scr.move(0,0)
    scr.clrtoeol()
    scr.addstr(0, 0, mode, curses.A_REVERSE)

  def curses_status(self, status):
    scr = self.stdscr
    self.log_y += 1
    if self.log_y > self.log_height:
      for i in range(1,self.log_height+1):
        scr.move(i,0)
        scr.clrtoeol()
      self.log_y = 1
    scr.move(self.log_y,0)
    scr.addstr(self.log_y, 0, status, curses.A_NORMAL)

  def teensy_init(self):
    try:
      teensy = serial.Serial(SERIAL, 9600)
      msg = 'teensy connected'
    except:
      msg = 'teensy NOT connected'
      teensy = None
    logger.debug(msg + ' on ' + SERIAL)      
    if self.scryx[1] > len(INSTRUCTIONS) + len(msg):
      self.stdscr.addstr(self.scryx[0]-1, self.scryx[1]-len(msg)-1, msg, curses.A_NORMAL)
    return teensy

  def prepare_file(self, fname, mode='wb'):
    logger.debug('prepare_file')
    wavefile = wave.open(fname, mode)
    wavefile.setnchannels(CHANNELS)
    wavefile.setsampwidth(self.pa.get_sample_size(FORMAT))
    wavefile.setframerate(RATE)
    return wavefile

  def start_flagging(self):
    logger.debug('start_flagging')
    self.curses_mode("Flagging mode, press s to stop recording")
    self.mode = 'flagging'
    self.wave_file = self.prepare_file('flag.wav', 'wb')
    self.stream.start_stream()

  def stop_flagging(self):
    logger.debug('stop_flagging')
    self.mode = None
    self.stream.stop_stream()
    self.wave_file.close()
  
  def start_fingerprinting(self):
    logger.debug('start_fingerprinting')
    self.mode = 'fingerprinting'
    self.curses_status("fingerprint new file? (press y or n)")

  def start_naming(self):
    logger.debug('start_naming')
    self.mode = 'naming'
    self.curses_status("name the recording: ")
    curses.echo()
    self.new_name = ''

  def fingerprint_file(self, name):
    self.curses_status("fingerprinting " + self.new_name)
    self.djv.fingerprint_file(name)
    os.remove(name)
    
  def start_matching(self):
    self.curses_mode("Matching...")
    self.match_count = 0
    self.mode = 'matching'
    self.stream.start_stream()

  def stop_matching(self):
    self.mode = None
    self.stream.stop_stream()

  def process_matches(self):
    self.stop_matching()

    matches = []
    matches.extend(self.djv.find_matches(self.rec_data[0], Fs=RATE))
    
    del self.rec_data[0][:]
    
    if len(matches) > 0:
      song = self.djv.align_matches(matches)
      if song and song['confidence'] > 5:
        out = song['song_name'] + ' ' + str(song['confidence'])
        logger.debug(out)
        self.curses_status(out)
        if self.teensy and not self.muted:
          self.muted = True
          self.teensy.write('0')
      else:
        logger.debug('no song')
        self.curses_status('no song')
        if self.teensy and self.muted:
          self.muted = False
          self.teensy.write('1')
    else:
      logger.debug('no matches')
      self.curses_status('no matches')
      if self.teensy and self.muted:
        self.muted = False
        self.teensy.write('1')

    self.start_matching()

  def match_data(self, data):
    nums = np.fromstring(data, np.int16)
    self.rec_data[0].extend(nums[0::1])
    self.match_count += 1
    if self.match_count >= REC_END:
      self.match_count = 0
      self.process_matches()

  def curses_loop(self):
    c = self.stdscr.getch()

    if c == -1:
      return

    if c == ord('q') and self.mode != 'naming':
      self.quit()

    if self.mode == 'matching':
      if c == ord('f'):
        self.stop_matching()
        self.start_flagging()

    elif self.mode == 'flagging':
      if c == ord('m'):
        self.stop_flagging()
        self.start_matching()
      elif c == ord('s'):
        self.stop_flagging()
        self.start_fingerprinting()

    elif self.mode == 'fingerprinting':
      if c == ord('y'):
        self.start_naming()
      elif c == ord('n'):
        self.start_matching()

    elif self.mode == 'naming':
      if c == curses.KEY_ENTER or c == 10 or c == 13:
        os.rename('flag.wav', self.new_name + '.wav')
        self.fingerprint_file(self.new_name + '.wav')
        curses.noecho()
        self.start_matching()
      else:
        self.new_name += chr(c)

    self.stdscr.refresh()

  def quit(self):
    self.stream.stop_stream()
    self.stream.close()
    self.pa.terminate()
    curses.nocbreak()
    curses.echo()
    curses.endwin()
    if os.path.isfile('flag.wav'):
      os.remove('flag.wav')
    sys.exit(0)

if __name__ == '__main__':
  rspy = RadioSpy()
  
  rspy.start_matching()

  while True:
    if rspy.stream.is_active():
      try:
        data = rspy.stream.read(CHUNK)
      except IOError as ex:
        logger.debug('IOError: ' + str(ex[1]) + ' ' + str(ex[0]))
        if ex[1] != rspy.pa.paInputOverflowed:
          raise
        data = '\x00' * CHUNK

      if rspy.mode == 'matching':
        rspy.match_data(data)

      elif rspy.mode == 'flagging':
        rspy.wave_file.writeframes(data)

    rspy.curses_loop()

  rspy.quit()