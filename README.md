# DVB-T2-DATV-Broadcast-System
this is app based on:
GNU Radio gr-dtv(modulator), 
FFmpeg (Encoder)
dvb2rate.c file from dr.mpeg Ron Economos https://github.com/drmpeg/dtv-utils/blob/master/dvbt2rate.c
compiled with deepseek instructions to dvbt2rate.exe (t2calculator)
DummyTS Generator - created with deepseek, based on c++ libs from DatvExpress G4GUO Charles Brain https://github.com/G4GUO/datvexpress_gui/tree/master/Sources
this is app created only for radioamateurs, enthusiasts, scientific experiments.
don't use it illegal, shield the room in which you conduct experiments!
if anyone can help me with export and build external exe app, like dvbt2rate.exe, where we can run SDR modulation T2 scheme with command prompt, and don't use very big resources from GNU Radio, I will be very grateful.
if u have any other idea to inplement to logic of this app, let me know or do it yourself and share with us.
I would like to express my deepest gratitude to Ron Economos for his invaluable contribution to my first steps in using 1.7MHz BW T2!

R6WAX Vibe Coding Project for those, who want, but can't.

![main_tab](https://github.com/user-attachments/assets/466bd3a5-5850-4876-b82f-e0c0ed65e661)

# 

1 - download dvbt2\_encoder.py, conf.cfg, start.bat, ffmpeg, folders with modulator presets \& saved schemes, dvbt2rate.exe, radioconda.rar, encoder\_presets, multiplex\_playlists into any folder.

# 

2 - extract radioconda.rar to the root of the script folder.

# 

3 - run Start.bat

# 

4 * go to settings tab and change ip of your pluto, or select your type of SDR. 
* select available on your PC video codec type.
![settings_tab](https://github.com/user-attachments/assets/2c78931d-c94e-41a9-bc30-c4b072e44af2)

#

* go to Multiplex tab and configure your channel list and select types of input source for each channel.
![Multiplex_tab](https://github.com/user-attachments/assets/d18a244a-1faf-43c8-ba61-1fdb6d3b9c1f)


"grab_window" u can use two methods for grabbing any opened window on your system: 
* 1 "gdigrab" - old ffmpeg method, but it's low framerate perfomance, can be used for windows, where no need high fps. 
* 2 "gfxcapture" (available from ffmpeg v.8.0), it's much better and can grab window with good fps.
u must select available audio device for "grab_window" source, and need setup your grabbing window app (like MPC HC Player, VLC Player, FRN Client, and etc.) to send audio with any virtual audio cable u have and select it for audio source.

* "URL_input" - can be used for internet radio (use radio checkbox, can be configured with background pic or color, all metadata values and parameters of text size and color send to ffmpeg stdin realtime via CParsed_drawtext_), IPTV link, just paste url and it's will work.

* "UDP_MPTS" - can be used for input from any udp multiplex stream, paste udp url and press Get info button, it's will check all available streams and u can select any u want to use for channel.

* "media_folder" - Browse and select folder with video files u want to broadcast, in selected folder may be one or several files u want, when you select folder, and start encoder, it's will create ch_playlist.txt file with all files included in selected folder and subfolders, use checkbox randomize, if need.
(important rule, u must prepair all files in folder to same codec formats, it's need for stable encoder concat demuxer operation, or u will have problem, when next file in playlist came to input with another parameters, demuxer will crash, your channel will destroy and restart all system).

* "input_devices" - select any available on your PC HW video and audio devices, like "OBS Virtual Camera" and "Virtual Audio Cable", for example. 

* Application have some protect logic for encoder processes, it's can be configured on Monitor tab.
it's may have other bugs and mistakes, because i'm not programmer and it's project creating and debugging non-stop from september 2025 and still upgrade and fix everyday, some features may work little incorrect, please, use it carefully, change any values with understanding and debug it.
![Monitor_tab](https://github.com/user-attachments/assets/a04b0afc-0152-435d-b65e-6cbde3a902c7)


* application support 10bit hevc, u can broadcast with HDR10. libx265 and hevc_nvenc codecs checked, intel QSV codec need to tune parameters for stable work. i don't have AMD GPU, and use standard parameters for codec, but u can setup all parameter u need in box with ffmpeg codec arguments on settings tab, change parameter and save encoder preset for use.

![GNU_T2_Calculator](https://github.com/user-attachments/assets/ccfc5624-654b-4f5b-b0a3-b1f94ce18c56)

![Overlay_tab](https://github.com/user-attachments/assets/32bfdcca-f33f-4be0-a86d-2cabf00c900b)

# 

5 - for use most popular \& cheap DVB-T2 tuners from any worldwide market with support 1.7MHZ bandwidth, select custom firmware for your cpu/tuner(hardware of tuner you have) combination from here (https://gitverse.ru/McMCC/net_upgrade_firmwares) , first time u must flash it via UART or via SPI programmer, next time u can update FW via USB.

# 

6 - u can also use mygica t230 series usb T2 tuner with custom driver (TBS6910se-debug in CrazyScan2 folder) for windows and unlock hardware 1.7MHz, or use CrazyScan2 software by CrazyCat with support 1.7MHz and other tools for analyze DVB-T2 Beacons.

![CrazyScan2](https://github.com/user-attachments/assets/15e5987c-a34d-4cfe-b2e8-54964707a754)

#

7 - with FFBatch\_AV\_Converter u can encode batch video in folder u will use to channel (media\_source) to one format (vcodec, acodec, aspect ratio, framerate(fps), pix\_fmt, resolution), it's important, because channel encoder using concat filter mux and all input files in channel playlist must have same codec formats and parameters.
![FFbatchconverter](https://github.com/user-attachments/assets/fc60ba45-36e8-44a4-bbd1-949eb986ff73)

