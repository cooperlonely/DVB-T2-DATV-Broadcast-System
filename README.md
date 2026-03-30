# DVB-T2-DATV-Broadcast-System

R6WAX Vibe Coding Project for those, who want, but can't.

# 

1 - download dvbt2\_encoder.py, conf.cfg, start.bat, ffmpeg, folders with modulator presets \& saved schemes, dvbt2rate.exe, radioconda.rar, encoder\_presets, multiplex\_playlists into any folder.

# 

2 - extract radioconda.rar to the root of the script folder.

# 

3 - run Start.bat

# 

4 * go to settings tab and change ip of your pluto, or select your type of SDR. 
* select available on your PC video codec type. 
* go to Multiplex tab and configure your channel list and select types of inpit source for each
for the grab_window u can use 2 options for grabbing any opened window on your system: 
* 1 gdigrab - old ffmpeg method, but it's low framerate perfomance, can be used for window, where no need high fps. 
* 2 gfxcapture (available from ffmpeg v.8.0), it's much better and can grab window with good fps.
u must select available audio device for grab_window source, u can setup your grabbing window app (like MPC HC Player, VLC Player, FRN Client, and etc.) to send audio to any virtual audio cable u have and select it for audio source.

* URL_input - can be used for internet radio (use radio checkbox, can be configured with background pic or color, all metadata values and parameters of text size and color send to ffmpeg stdin realtime via CParsed_drawtext_), IPTV link, just paste url and it's will work.

* UDP_MPTS - can be used for input from any udp multiplex stream, paste udp url and press Get info button, it's will check all available streams and u can select any u want to use for channel.

* media_folder - Browse and select folder with video files u want to broadcast, on selected folder may be 1 file or many files u want, when you select folder, and start encoder, it's will create ch_playlist.txt file with all files included in selected folder and subfolders, use checkbox randomize, if need.
(important rule, u must prepair all files in folder to same codec formats, it's need for stable encoder concat demuxer operation, or u will have problem, when next file in playlist came to input with another parameters, demuxer will crash, your channel will destroy and restart all system).

* input_devices - select any available on your PC HW video and audio devices, like OBS Virtual Camera and Virtual Audio Cable, for example. 

* Application have some protect logic for encoder processes, it's can be configured on Monitor tab.
it's can have other bugs and mistakes, because i'm not programmer and it's project creating and debugging non-stop from september 2025 and still upgrade and fix everyday, some features can work little incorrect, please, use it carefully, change any values with understanding and debug it.

* application support 10bit hevc, u can broadcast with HDR10. libx265 and hevc_nvenc codecs checked, intel QSV codec need to tune parameters for stable work. i don't have AMD GPU, and use standard parameters for codec, but u can setup all parameter u need in box with ffmpeg codec arguments on settings tab, change parameter and save encoder preset for use.


# 

5 - for use most popular \& cheap DVB-T2 tuners from any worldwide market with support 1.7MHZ bandwidth, select custom firmware for your cpu/tuner(hardware of tuner you have) combination from here (https://gitverse.ru/McMCC/net_upgrade_firmwares) , first time u must flash it via UART or via SPI programmer, next time u can update FW via USB.

# 

6 - u can also use mygica t230 series usb T2 tuner with custom driver (TBS6910se-debug in CrazyScan2 folder) for windows and unlock hardware 1.7MHz, or use CrazyScan2 software by CrazyCat with support 1.7MHz and other tools for analyze DVB-T2 Beacons.

#

7 - with FFBatch\_AV\_Converter u can encode batch video in folder u will use to channel (media\_source) to one format (vcodec, acodec, aspect ratio, framerate(fps), pix\_fmt, resolution), it's important, because channel encoder using concat filter mux and all input files in channel playlist must have same codec formats and parameters.

