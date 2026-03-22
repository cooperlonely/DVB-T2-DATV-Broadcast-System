# DVB-T2-DATV-Broadcast-System

R6WAX Vibe Coding Project for those, who want, but can't.

# 

1 - download dvbt2\_encoder.py, conf.cfg, start.bat, ffmpeg, folders with modulator presets \& saved schemes, dvbt2rate.exe, radioconda.rar, encoder\_presets, multiplex\_playlists into any folder.

# 

2 - extract radioconda.rar to the root of the script folder.

# 

3 - run DVBT2\_DATV shortcut or Start.bat

# 

4 - go to setup page and change ip of your pluto, or select your type of SDR.

# 

5 - enjoy.

# 

6 - for use most popular \& cheap DVB-T2 tuners from any worldwide market with support 1.7MHZ bandwidth, select custom firmware for your cpu/tuner(hardware of tuner you have) combination from here https://gitverse.ru/McMCC/net\_upgrade\_firmwares , first time u must flash it via UART or via SPI programmer, next time u can update FW via USB.

# 

7 - u can also use mygica t230 series usb T2 tuner with custom driver (TBS6910se-debug in CrazyScan2 folder) for windows and unlock hardware 1.7MHz, or use CrazyScan2 software by CrazyCat with support 1.7MHz and other tools for analyze DVB-T2 Beacons.


8 - with FFBatch\_AV\_Converter u can encode batch video in folder u will use to channel (media\_source) to one format (vcodec, acodec, aspect ratio, framerate(fps), pix\_fmt, resolution), it's important, because channel encoder using concat filter mux and all input files in channel playlist must have same codec formats and parameters.

