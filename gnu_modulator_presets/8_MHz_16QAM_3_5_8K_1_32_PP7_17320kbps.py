#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: DVB-T2 8 MHz 16QAM 3/5
# Author: DVB-T2 Calculator
# GNU Radio version: 3.10.10.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import blocks
from gnuradio import digital
from gnuradio import dtv
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import iio

from gnuradio import zeromq
from xmlrpc.server import SimpleXMLRPCServer
import threading

class DVB_8_MHz_16QAM_3_5_8K_1_32_PP7_17320kbps(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "DVB-T2 Modulator", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("DVB-T2 Modulator")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "DVB_8_MHz_16QAM_3_5_8K_1_32_PP7_17320kbps")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)

        ##################################################
        # Variables
        ##################################################
    
        self.zmq_address = zmq_address = "tcp://127.0.0.1:8002"
        self.sample = sample = 9142857
        self.rf_gain = rf_gain = 6
        
        self.pluto_ip = pluto_ip = "ip:192.168.80.70"
        self.frequency = frequency = 425000000
        self.bandwidth = bandwidth = 9142857
        
        

        ##################################################
        # Blocks
        ##################################################

        self.xmlrpc_server_0 = SimpleXMLRPCServer(('localhost', 8001), allow_none=True)
        self.xmlrpc_server_0.register_instance(self)        
        self.xmlrpc_server_0_thread = threading.Thread(target=self.xmlrpc_server_0.serve_forever)
        self.xmlrpc_server_0_thread.daemon = True
        self.xmlrpc_server_0_thread.start()
        
        # ZMQ SUB source 
        self.zeromq_sub_source_0 = zeromq.sub_source(gr.sizeof_char, 1, zmq_address, 500, False, (-1), '', False )

        self.iio_pluto_sink_0_0 = iio.fmcomms2_sink_fc32(pluto_ip if pluto_ip else iio.get_pluto_uri(), [True, True], 32768, False)
        self.iio_pluto_sink_0_0.set_len_tag_key('')
        self.iio_pluto_sink_0_0.set_bandwidth(bandwidth)
        self.iio_pluto_sink_0_0.set_frequency(frequency)
        self.iio_pluto_sink_0_0.set_samplerate(sample)
        self.iio_pluto_sink_0_0.set_attenuation(0, rf_gain)
        self.iio_pluto_sink_0_0.set_filter_params('Auto', '', 0, 0)



        self.dtv_dvbt2_pilotgenerator_cc_0 = dtv.dvbt2_pilotgenerator_cc(
            dtv.CARRIERS_EXTENDED,
            dtv.FFTSIZE_8K,
            dtv.PILOT_PP7,
            dtv.GI_1_32,
            239,
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO,
            dtv.MISO_TX1,
            dtv.EQUALIZATION_OFF,
            dtv.BANDWIDTH_8_0_MHZ,
            8192
            )
        self.dtv_dvbt2_p1insertion_cc_0 = dtv.dvbt2_p1insertion_cc(
            dtv.CARRIERS_EXTENDED,
            dtv.FFTSIZE_8K,
            dtv.GI_1_32,
            239,
            dtv.PREAMBLE_T2_SISO,
            dtv.SHOWLEVELS_OFF,
            3.3
            )
        self.dtv_dvbt2_modulator_bc_0 = dtv.dvbt2_modulator_bc(dtv.FECFRAME_NORMAL, dtv.MOD_16QAM, dtv.ROTATION_ON)
        self.dtv_dvbt2_interleaver_bb_0 = dtv.dvbt2_interleaver_bb(dtv.FECFRAME_NORMAL, dtv.C3_5, dtv.MOD_16QAM)
        self.dtv_dvbt2_freqinterleaver_cc_0 = dtv.dvbt2_freqinterleaver_cc(
            dtv.CARRIERS_EXTENDED,
            dtv.FFTSIZE_8K,
            dtv.PILOT_PP7,
            dtv.GI_1_32,
            239,
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO
            )
        self.dtv_dvbt2_framemapper_cc_0 = dtv.dvbt2_framemapper_cc(
            dtv.FECFRAME_NORMAL,
            dtv.C3_5,
            dtv.MOD_16QAM,
            dtv.ROTATION_ON,
            100,
            3,
            dtv.CARRIERS_EXTENDED,
            dtv.FFTSIZE_8K,
            dtv.GI_1_32,
            dtv.L1_MOD_BPSK,
            dtv.PILOT_PP7,
            2,
            239,
            dtv.PAPR_OFF,
            dtv.VERSION_131,
            dtv.PREAMBLE_T2_SISO,
            dtv.INPUTMODE_NORMAL,
            dtv.RESERVED_OFF,
            dtv.L1_SCRAMBLED_OFF,
            dtv.INBAND_ON)
        self.dtv_dvbt2_cellinterleaver_cc_0 = dtv.dvbt2_cellinterleaver_cc(dtv.FECFRAME_NORMAL, dtv.MOD_16QAM, 100, 3)
        self.dtv_dvb_ldpc_bb_0 = dtv.dvb_ldpc_bb(
            dtv.STANDARD_DVBT2,
            dtv.FECFRAME_NORMAL,
            dtv.C3_5,
            dtv.MOD_OTHER)
        self.dtv_dvb_bch_bb_0 = dtv.dvb_bch_bb(
            dtv.STANDARD_DVBT2,
            dtv.FECFRAME_NORMAL,
            dtv.C3_5
            )
        self.dtv_dvb_bbscrambler_bb_0 = dtv.dvb_bbscrambler_bb(
            dtv.STANDARD_DVBT2,
            dtv.FECFRAME_NORMAL,
            dtv.C3_5
            )
        self.dtv_dvb_bbheader_bb_0 = dtv.dvb_bbheader_bb(
        dtv.STANDARD_DVBT2,
        dtv.FECFRAME_NORMAL,
        dtv.C3_5,
        dtv.RO_0_35,
        dtv.INPUTMODE_NORMAL,
        dtv.INBAND_ON,
        100,
        17320150)
        self.digital_ofdm_cyclic_prefixer_0 = digital.ofdm_cyclic_prefixer(
            8192,
            8192 + (8192 * 1) // 32,
            0,
            '')
        self.blocks_multiply_const_xx_0 = blocks.multiply_const_cc(0.3, 1)



        ##################################################
        # Connections
        ##################################################

        self.connect((self.blocks_multiply_const_xx_0, 0), (self.iio_pluto_sink_0_0, 0))
        self.connect((self.digital_ofdm_cyclic_prefixer_0, 0), (self.dtv_dvbt2_p1insertion_cc_0, 0))
        self.connect((self.dtv_dvb_bbheader_bb_0, 0), (self.dtv_dvb_bbscrambler_bb_0, 0))
        self.connect((self.dtv_dvb_bbscrambler_bb_0, 0), (self.dtv_dvb_bch_bb_0, 0))
        self.connect((self.dtv_dvb_bch_bb_0, 0), (self.dtv_dvb_ldpc_bb_0, 0))
        self.connect((self.dtv_dvb_ldpc_bb_0, 0), (self.dtv_dvbt2_interleaver_bb_0, 0))
        self.connect((self.dtv_dvbt2_cellinterleaver_cc_0, 0), (self.dtv_dvbt2_framemapper_cc_0, 0))
        self.connect((self.dtv_dvbt2_framemapper_cc_0, 0), (self.dtv_dvbt2_freqinterleaver_cc_0, 0))
        self.connect((self.dtv_dvbt2_freqinterleaver_cc_0, 0), (self.dtv_dvbt2_pilotgenerator_cc_0, 0))
        self.connect((self.dtv_dvbt2_interleaver_bb_0, 0), (self.dtv_dvbt2_modulator_bc_0, 0))
        self.connect((self.dtv_dvbt2_modulator_bc_0, 0), (self.dtv_dvbt2_cellinterleaver_cc_0, 0))
        self.connect((self.dtv_dvbt2_p1insertion_cc_0, 0), (self.blocks_multiply_const_xx_0, 0))
        self.connect((self.dtv_dvbt2_pilotgenerator_cc_0, 0), (self.digital_ofdm_cyclic_prefixer_0, 0))
        self.connect((self.zeromq_sub_source_0, 0), (self.dtv_dvb_bbheader_bb_0, 0))
    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "DVB_8_MHz_16QAM_3_5_8K_1_32_PP7_17320kbps")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()




    #   XML-RPC :

    def get_rf_gain(self):
        return self.rf_gain

    def set_rf_gain(self, rf_gain):
        self.rf_gain = rf_gain
        self.iio_pluto_sink_0_0.set_attenuation(0, self.rf_gain)

    def get_frequency(self):
        return self.frequency

    def set_frequency(self, frequency):
        self.frequency = frequency
        self.iio_pluto_sink_0_0.set_frequency(self.frequency)
    def stop_transmission(self):
        """Stop the modulator gracefully"""
        print("[INFO] Stop command received via XML-RPC")
        self.stop()
        self.wait()
        Qt.QApplication.quit()
        return "Stopped successfully"
    
    def quit_application(self):
        """Quit the application"""
        print("[INFO] Quit command received")
        self.stop()
        self.wait()
        Qt.QApplication.quit()
        return "Application quit"


def main(top_block_cls=DVB_8_MHz_16QAM_3_5_8K_1_32_PP7_17320kbps, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()

    tb.start()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
