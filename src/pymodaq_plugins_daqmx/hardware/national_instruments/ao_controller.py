
from pymodaq_plugins_daqmx.hardware.national_instruments.daqmxni import (NIDAQmx, AOChannel, ClockSettings)


class AnalogOutputController:
    """Controller for static NI analog outputs."""

    def __init__(self):
        self.analog = NIDAQmx()
        self.axes: dict[str, AOChannel] = {}
        self.voltages: dict[str, float] = {}

    def configure_axis(self, axis: str, channel: str, vmin: float, vmax: float):
        self.axes[axis] = AOChannel(name=channel, value_min=vmin, value_max=vmax)
        self.voltages.setdefault(axis, 0.)
        self.analog.update_task(list(self.axes.values()), ClockSettings(Nsamples=1))

    def voltage(self, axis: str) -> float:
        return self.voltages[axis]

    def set_voltage(self, axis: str, voltage: float):
        self.voltages[axis] = float(voltage)
        names = list(self.axes)
        values = [self.voltages[ax] for ax in names]
        self.analog.task.write(values if len(values) > 1 else values[0], auto_start=True)

    def stop(self):
        pass

    def close(self):
        self.analog.close()
