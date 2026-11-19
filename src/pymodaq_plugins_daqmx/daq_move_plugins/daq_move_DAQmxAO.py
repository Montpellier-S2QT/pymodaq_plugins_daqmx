import numpy as np

from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun, DataActuatorType,
                                                          DataActuator, main)
from pymodaq.utils.logger import set_logger, get_module_name

from pymodaq_plugins_daqmx.hardware.national_instruments.daqmxni import NIDAQmx, ChannelType
from pymodaq_plugins_daqmx.hardware.national_instruments.ao_controller import AnalogOutputController

logger = set_logger(get_module_name(__file__))

AO_CHANNELS = NIDAQmx.get_NIDAQ_channels(source_type=ChannelType.ANALOG_OUTPUT)


class DAQ_Move_DAQmxAO(DAQ_Move_base):
    """Static analog output of a NI device.

    """
    _controller_units = 'V'
    is_multiaxes = False
    _axis_names = ['Voltage']
    _epsilons = 0.001
    data_actuator_type = DataActuatorType.DataActuator
    params = [{'title': 'Output channel:', 'name': 'analog_channel', 'type': 'list', 'limits': AO_CHANNELS,
         'value': AO_CHANNELS[0] if AO_CHANNELS else ''},
              {'title': 'Minimum voltage (V):', 'name': 'voltage_min', 'type': 'float', 'value': -10.},
              {'title': 'Maximum voltage (V):', 'name': 'voltage_max', 'type': 'float', 'value': 10.},
    ] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilons)

    def ini_attributes(self):
        self.controller: AnalogOutputController = None

    @property
    def axis(self) -> str:
        return self.axis_name

    def configure_axis(self):
        self.controller.configure_axis(self.axis, self.settings['analog_channel'],
                                       self.settings['voltage_min'], self.settings['voltage_max'])

    def ini_stage(self, controller=None):

        if self.is_master:
            self.controller = AnalogOutputController()
        else:
            self.controller = controller

        self.configure_axis()

        # Initialize the output at 0 V
        self.controller.set_voltage(self.axis, 0.)

        return 'NI analog output ready', True

    def close(self):
        if self.is_master and self.controller is not None:
            self.controller.close()

    def commit_settings(self, param):
        if param.name() == 'analog_channel':
            self.configure_axis()

    def get_actuator_value(self) -> DataActuator:
        position = DataActuator(data=self.controller.voltage(self.axis),
                                units=self.axis_unit)
        return self.get_position_with_scaling(position)


    def move_abs(self, value: DataActuator):
        value = self.check_bound(value)
        self.target_value = value
        value = self.set_position_with_scaling(value)
        voltage = value.value(self.axis_unit)
        self.controller.set_voltage(self.axis, voltage)

    def move_rel(self, value: DataActuator):
        target = self.check_bound(self.current_value + value)
        self.target_value = target
        target = self.set_position_with_scaling(target)
        voltage = target.value(self.axis_unit)
        self.controller.set_voltage(self.axis, voltage)

    def move_home(self):
        self.move_abs(DataActuator(data=0., units=self.axis_unit))

    def stop_motion(self):
        self.controller.stop()


if __name__ == '__main__':
    main(__file__)
