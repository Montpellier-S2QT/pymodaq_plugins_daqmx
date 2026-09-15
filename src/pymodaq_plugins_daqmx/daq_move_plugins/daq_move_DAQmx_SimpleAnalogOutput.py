import numpy as np
from time import perf_counter
from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, comon_parameters_fun, main  # common set of
# parameters for all actuators
from pymodaq.utils.daq_utils import ThreadCommand # object used to send info back to the main thread
from pymodaq.utils.parameter import Parameter
from pymodaq.control_modules.thread_commands import ThreadStatus
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq_plugins_daqmx.hardware.national_instruments.daqmx import DAQmx, AOChannel, \
    DAQ_analog_types

from PyDAQmx import DAQmx_Val_FiniteSamps

logger = set_logger(get_module_name(__file__))


class DAQ_Move_DAQmx_SimpleAnalogOutput(DAQ_Move_base):
    """Plugin to control a piezo scanner with a NI card. This modules requires a clock channel to handle the
    timing of the movement and display the position. Avoid using several scanners (ie several analog outputs)
    with a single clock, this creates conflicts in the use of the clock channel. For this purpose, use the module
    MultipleScannerControl.

    This object inherits all functionality to communicate with PyMoDAQ Module through inheritance via DAQ_Move_base
    It then implements the particular communication with the instrument

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library

    """
    _controller_units = 'V'
    is_multiaxes = False  
    axes_names = []
    _epsilon = 0.1

    params = [ {"title": "Output channel:", "name": "analog_channel",
                "type": "list", "limits": DAQmx.get_NIDAQ_channels(source_type="Analog_Output")},
                ] + comon_parameters_fun(is_multiaxes, axes_names)

    def ini_attributes(self):
        self.controller = None
        self.scanner_channel = None
        self.voltage_list = np.array([0.0])

    def get_actuator_value(self):
        """Get the current value from the hardware.

        Returns
        -------
        float: the last voltage applied
        """
        voltage = self.controller.get_last_write()
        return voltage

    def close(self):
        """ Terminate the communication protocol"""
        print("move_done received, closing task")
        self.controller.close()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "analog_channel":
            self.close()
            self.update_task()

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case).
            None if only one actuator by controller (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        self.controller = DAQmx()
        
        try:
            self.update_task()
            initialized = True
            info = "NI card based DC analog write."
            self.move_abs(0.01)  # to avoid bad initial positioning because
            # we can't read the actual value from the NI card.
        except Exception as e:
            initialized = False
            info = e
    
        return info, initialized

    def move_abs(self, value):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning 
        """
        value = self.check_bound(value)  # if user checked bounds, the defined bounds are applied here
        self.target_value = value
        value = self.set_position_with_scaling(value)  # apply scaling if the user specified one
        self.move_voltage(value)
        self.emit_status(ThreadCommand('Update_Status', ['Absolute movement.']))

    def move_rel(self, value):
        """ Move the actuator to the relative target actuator value defined by value

        Parameters
        ----------
        value: (float) value of the relative target positioning
        """
        value = self.check_bound(self.current_value + value) - self.current_value
        self.target_value = value + self.current_value
        target = self.set_position_with_scaling(self.target_value)
        self.move_voltage(target)
        self.emit_status(ThreadCommand('Update_Status', ['Relative movement.']))

    def move_home(self):
        """Do nothing"""
        self.emit_status(ThreadCommand('Update_Status', ['No home position implemented.']))

    def stop_motion(self):
      """Stop the actuator and emits move_done signal"""
      self.controller.locked = False
      self.controller.stop()
      self.emit_status(ThreadCommand('Update_Status', ['Motion stopped.']))

    def update_task(self):
        """ Set up the analog output task in the NI card."""
        min_voltage = self.settings.child("bounds", "min_bound").value()
        max_voltage = self.settings.child("bounds", "max_bound").value()
        self.voltage_channel = AOChannel(name=self.settings.child("analog_channel").value(),
                                         source="Analog_Output",
                                         analog_type=DAQ_analog_types.names()[0],
                                         value_min=min_voltage,
                                         value_max=max_voltage)

        self.controller.update_task(channels=[self.voltage_channel])

    def move_voltage(self, value):
        """ Changes output voltage to specified value """

        # prepare the tasks
        self.update_task()

        # Actually tells the NI card to send the voltage.
        self.controller.start()
        self.controller.writeAnalog(1, 1, np.array([value]))


    def check_target_reached(self):
        #override from DAQ_move_base to stop task and unlock controller after move is done
        logger.debug(f"epsilon value is {self.epsilon}")
        logger.debug(f"current_value value is {self._current_value}")
        logger.debug(f"target_value value is {self._target_value}")

        if not self._condition_to_reach_target():

            logger.debug(f'Check move_is_done: {self.move_is_done}')
            if self.move_is_done:
                self.emit_status(ThreadCommand(ThreadStatus.UPDATE_STATUS, 'Move has been stopped'))
                logger.info('Move has been stopped')
            self.current_value = self.get_actuator_value()
            self.emit_value(self._current_value)
            logger.debug(f'Current value: {self._current_value}')

            if perf_counter() - self.start_time >= self.settings['timeout']:
                self.poll_timer.stop()
                self.emit_status(ThreadCommand(ThreadStatus.RAISE_TIMEOUT))
                logger.info('Timeout activated')
        else:
            self.poll_timer.stop()
            self.current_value = self.get_actuator_value()
            logger.debug(f'Current value: {self._current_value}')
            self.controller.locked = False
            self.controller.stop()
            self.move_done(self._current_value)
            
    
if __name__ == '__main__':
    main(__file__)
