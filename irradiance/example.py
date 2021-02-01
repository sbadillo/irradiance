from python_code import PVSystem
import pandas as pd

naive_times = pd.date_range(start='2015', end='2016', freq='1h')

print(naive_times[0], naive_times[-1], "Freq:", naive_times.freq)

# Instanciate a PV System
pv_Sonora = PVSystem(
    times=naive_times,
    latitude=30, 
    longitude=-110,
    surface_azimuth=180,
    surface_tilt=0
)

print(pv_Sonora)
pv_Sonora.get_solar_pos()