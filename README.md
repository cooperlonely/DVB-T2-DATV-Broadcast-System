# DVB-T2-DATV-Broadcast-System
R6WAX Vibe Coding Project for those, who want, but can't.
#
1 - download dvbt2enc.py, conf.cfg, setup.bat, start.bat, ffmpeg, folders with modulator presets, dvbt2rate.exe into any folder.
#
2 - download gnu radio from repo and use standard path or copy path, if custom installation.
#
3 - run setup.bat - it's will find and add paths to conf.cfg (u can add custom path into conf.cfg).
#
4 - run start.bat - i'ts will run app with activated environment for radioconda resources
#
5 - go to setup page and change ip of your pluto, or select your type of SDR.
#
6 - enjoy.
#
7 - for use most popular & cheap DVB-T2 tuners from any worldwide market with support 1.7MHZ bandwidth, select custom firmware for your cpu/tuner(hardware of tuner you have) combination from here https://gitverse.ru/McMCC/net_upgrade_firmwares , first time u must flash it via UART or via SPI programmer, next time u can update FW via USB.
#
8 - u can also use mygica t230 series usb T2 tuner with custom driver (TBS6910se-debug in CraziScan2 folder) for windows for unlock hardware 1.7MHz, or use CrazyScan2 software by CrazyCat with support 1.7MHz and other tools for analyze DVB-T2 Beacons.
