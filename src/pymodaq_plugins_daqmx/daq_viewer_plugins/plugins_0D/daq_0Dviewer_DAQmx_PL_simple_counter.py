import numpy as np
from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.utils.data import DataWithAxes, DataToExport, DataSource
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.parameter import Parameter

#from pymodaq_plugins_daqmx.hardware.national_instruments.daqmx import DAQmx, \
#    Edge, ClockSettings, SemiPeriodCounter, ClockCounter,  TriggerSettings
from pymodaq_plugins_daqmx.hardware.national_instruments.daqmxni import DAQmx, \
    Edge, ClockSettings, SemiPeriodCounter, ClockCounter,  TriggerSettings, DAQ_NIDAQ_source, \
    niTask
from nidaqmx.constants import AcquisitionType, ReadRelativeTo, OverwriteMode, \
    CountDirection, FrequencyUnits, Level, TimeUnits

#from PyDAQmx import DAQmx_Val_ContSamps, DAQmx_Val_CurrReadPos, DAQmx_Val_DoNotOverwriteUnreadSamps
import time
# DAQmx_Val_DoNotInvertPolarity, DAQmxConnectTerms,
# DAQmx_Val_FiniteSamps, DAQmx_Val_CurrReadPos, \
# DAQmx_Val_DoNotOverwriteUnreadSamps

class DAQ_0DViewer_DAQmx_PL_simple_counter(DAQ_Viewer_base):
    """
    Plugin for a 0D PL counter, based on a NI card.
    """
    params = comon_parameters+[
        {"title": "Counting channel:", "name": "counter_channel",
         "type": "list", "limits": DAQmx.get_NIDAQ_channels(source_type=DAQ_NIDAQ_source.Counter)},
        {"title": "Photon source:", "name": "photon_channel",
         "type": "list", "limits": DAQmx.getTriggeringSources()},
        {"title": "Clock frequency (Hz):", "name": "clock_freq",
         "type": "float", "value": 200., "default": 200., "min": 1},
        {'title': 'Clock channel:', 'name': 'clock_channel', 'type': 'list',
         'limits': DAQmx.get_NIDAQ_channels(source_type=DAQ_NIDAQ_source.Counter)}
        ]

    def ini_attributes(self):
        self.controller = None
        self.clock_channel = None
        self.counter_channel = None
        self.live = False  # True during a continuous grab
        self.counting_time = 0.1

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "clock_freq":
            self.counting_time = 1/param.value()

            # Changing the acquisition setting of the NI card
            self.update_tasks()
            self.controller["clock"].start()
            self.controller["counter"].start()

        else:
            self.stop()
            self.update_tasks()

    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.controller = {"clock": DAQmx(), "counter": DAQmx()}
        try:
            self.update_tasks()
            initialized = True
            info = "NI card based PL counter"
            self.counting_time = 1 / self.settings.child("clock_freq").value()
        except Exception as e:
            print(e)
            initialized = False
            info = "Error"
            
        self.dte_signal_temp.emit(DataToExport(name='PL',
                                               data=[DataWithAxes(name='PL', data=[np.array([0])],
                                               source=DataSource['raw'],
                                               dim='Data0D', labels=['PL (kcts/s)'])]))
        
        return info, initialized
    
    def close(self):
        """Terminate the communication protocol"""
        self.controller["clock"].close()
        self.controller["counter"].close()
        
    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging not relevant here.
        kwargs: dict
            others optionals arguments
        """
        update = True  # to decide if we do the initial set up or not

        if 'live' in kwargs:
            if kwargs['live'] == self.live and self.live:
                update = False  # we are already live
            self.live = kwargs['live']
            
        if update:
            self.update_tasks()
            self.controller["clock"].start()
            self.controller["counter"].start()
        read_data = self.controller["counter"].task.read(number_of_samples_per_channel=2)#number_of_samples_per_channel=1000

        data_pl = 1e-3 * (np.array(read_data)[::2] + np.array(read_data)[1::2]) / self.counting_time
        self.emit_status(ThreadCommand('Update_Status', ['Data Output: ' + str(data_pl)]))
        try:

            self.dte_signal.emit(DataToExport(name='PL',
                                              data=[DataWithAxes(name='PL', data=[data_pl],
                                                                 source=DataSource['raw'],
                                                                 dim='Data0D', labels=['PL (kcts/s)'])]))
        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', ["Exception caught: {}".format(e)]))
    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        self.close()
        # Allows the connection to be re-openned when the acquisition starts again
        self.live = False
        self.emit_status(ThreadCommand('Update_Status', ['Acquisition stopped.']))
        return ''

    def update_tasks(self):
        """Set up the counting tasks in the NI card."""

        if self.controller["counter"]._task is not None:
            if isinstance(self.controller["counter"]._task, niTask):
                self.controller["counter"]._task.close()
            self._task = None
        if self.controller["clock"]._task is not None:
            if isinstance(self.controller["clock"]._task, niTask):
                self.controller["clock"]._task.close()
            self._task = None



        self.controller["counter"]._task = niTask()
        channel = self.controller["counter"].task.ci_channels.add_ci_semi_period_chan(
            self.settings.child("counter_channel").value(),
            units=TimeUnits.TICKS
        )

        self.controller["clock"]._task = niTask()
        clock_channel = self.controller["clock"].task.co_channels.add_co_pulse_chan_freq(
            counter=self.settings.child("clock_channel").value(),
            units=FrequencyUnits.HZ,
            idle_state=Level.LOW,
            initial_delay=0,
            freq=self.settings.child("clock_freq").value(),
            duty_cycle=0.5,

        )

        self.controller["clock"].task.timing.cfg_implicit_timing(AcquisitionType.CONTINUOUS, 1000)

        channel.ci_semi_period_term = "/" + clock_channel.name + "InternalOutput"
        channel.ci_ctr_timebase_src = self.settings.child("photon_channel").value()

        self.controller["counter"].task.timing.cfg_implicit_timing(AcquisitionType.CONTINUOUS, 1000)
        self.controller["counter"].task.in_stream.relative_to = ReadRelativeTo.CURRENT_READ_POSITION
        self.controller["counter"].task.in_stream.offset = 0
        self.controller["counter"].task.in_stream.overwrite = OverwriteMode.DO_NOT_OVERWRITE_UNREAD_SAMPLES

if __name__ == '__main__':
    main(__file__)
