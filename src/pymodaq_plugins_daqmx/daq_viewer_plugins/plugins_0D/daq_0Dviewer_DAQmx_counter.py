import numpy as np
from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.utils.data import DataWithAxes, DataToExport, DataSource
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.parameter import Parameter

#from pymodaq_plugins_daqmx.hardware.national_instruments.daqmx import DAQmx, \
#    Edge, ClockSettings, SemiPeriodCounter, ClockCounter,  TriggerSettings
from pymodaq_plugins_daqmx.hardware.national_instruments.daqmxni import DAQmx, \
    Edge, ClockSettings, SemiPeriodCounter, ClockCounter, Counter,  TriggerSettings, DAQ_NIDAQ_source, \
    niTask
from nidaqmx.constants import AcquisitionType, ReadRelativeTo, OverwriteMode, \
    CountDirection, FrequencyUnits, Level, TimeUnits

#from PyDAQmx import DAQmx_Val_ContSamps, DAQmx_Val_CurrReadPos, DAQmx_Val_DoNotOverwriteUnreadSamps
import time
# DAQmx_Val_DoNotInvertPolarity, DAQmxConnectTerms,
# DAQmx_Val_FiniteSamps, DAQmx_Val_CurrReadPos, \
# DAQmx_Val_DoNotOverwriteUnreadSamps

class DAQ_0DViewer_DAQmx_counter(DAQ_Viewer_base):
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

        read_data = self.controller["counter"].task.read(number_of_samples_per_channel=2)#1, counting_time=self.counting_time,

        try:
            # sum up and down time and convert to kcts/s
            data_pl = 1e-3*(np.array(read_data)[::2]+np.array(read_data)[1::2])/self.counting_time

            data_pl = np.reshape(data_pl, (len(data_pl)))
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

        self.clock_channel = ClockCounter(self.settings.child("clock_freq").value(),
                                          name=self.settings.child("clock_channel").value(),
                                          source=DAQ_NIDAQ_source.Counter)
        self.counter_channel = SemiPeriodCounter(value_max=2e7, name=self.settings.child("counter_channel").value(),
                                       source=DAQ_NIDAQ_source.Counter, edge=Edge.RISING)

        self.controller["clock"].update_task(channels=[self.clock_channel],
                                             clock_settings=ClockSettings(),
                                             trigger_settings=TriggerSettings())

        self.controller["clock"].task.timing.cfg_implicit_timing(AcquisitionType.CONTINUOUS, 1000)

        self.controller["counter"].update_task(channels=[self.counter_channel],
                                                      clock_settings=ClockSettings(),
                                                      trigger_settings=TriggerSettings())

        self.counter_channel.ni_channel.ci_semi_period_term = "/" + self.settings.child("clock_channel").value() + "InternalOutput"
        self.counter_channel.ni_channel.ci_ctr_timebase_src = self.settings.child("photon_channel").value()

        self.controller["counter"].task.timing.cfg_implicit_timing(AcquisitionType.CONTINUOUS, 1000)
        self.controller["counter"].task.in_stream.relative_to = ReadRelativeTo.CURRENT_READ_POSITION
        self.controller["counter"].task.in_stream.offset = 0
        self.controller["counter"].task.in_stream.overwrite = OverwriteMode.DO_NOT_OVERWRITE_UNREAD_SAMPLES


if __name__ == '__main__':
    main(__file__)
